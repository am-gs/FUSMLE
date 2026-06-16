import datetime
import json
import os
import sqlite3
import uuid
from urllib import parse, request as urlrequest

DB_PATH = os.environ.get("SQLITE_DATABASE_PATH", os.environ.get("DATABASE_URL", "/tmp/uworld.db"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)


def using_ephemeral_database():
    return not USE_SUPABASE and DB_PATH.startswith("/tmp/")


def _utc_now():
    return datetime.datetime.utcnow().replace(microsecond=0)


def _iso(dt):
    if isinstance(dt, str):
        return dt
    return dt.isoformat() + "Z"


def _supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _supabase_request(method, table, body=None, query="", select=True):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += f"?{query}"
    req = urlrequest.Request(url, headers=_supabase_headers(), method=method)
    if body is not None:
        req.data = json.dumps(body).encode("utf-8")
    if method in ("POST", "PATCH") and select:
        req.add_header("Prefer", "return=representation")
    elif method == "POST":
        req.add_header("Prefer", "resolution=merge-duplicates")
    with urlrequest.urlopen(req, timeout=15) as response:
        data = response.read().decode("utf-8")
        return json.loads(data) if data else None


def _eq(value):
    return "eq." + parse.quote(str(value), safe="")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if USE_SUPABASE:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            is_correct BOOLEAN NOT NULL,
            time_spent INTEGER NOT NULL,
            subject TEXT NOT NULL,
            system TEXT,
            answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            question_ids TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            current_question INTEGER DEFAULT 0,
            score INTEGER,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            block_info TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            selected_option INTEGER NOT NULL,
            is_correct BOOLEAN NOT NULL,
            time_spent INTEGER NOT NULL DEFAULT 0,
            answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(test_session_id, question_id),
            FOREIGN KEY (test_session_id) REFERENCES test_sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE test_sessions ADD COLUMN block_info TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def _normalize_user(row):
    if not row:
        return None
    return dict(row)


def _normalize_test_session(row):
    if not row:
        return None
    session = dict(row)
    if USE_SUPABASE:
        session["question_ids"] = json.dumps(session.get("question_ids") or [])
        session["block_info"] = json.dumps(session.get("block_info")) if session.get("block_info") is not None else None
    return session


def create_user(email, password_hash, name=""):
    if USE_SUPABASE:
        rows = _supabase_request("POST", "users", {"email": email, "password_hash": password_hash, "name": name})
        return rows[0]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)", (email, password_hash, name))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_user_by_email(email):
    if USE_SUPABASE:
        rows = _supabase_request("GET", "users", query=f"email={_eq(email)}&limit=1")
        return _normalize_user(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return _normalize_user(user)


def get_user_by_id(user_id):
    if USE_SUPABASE:
        rows = _supabase_request("GET", "users", query=f"id={_eq(user_id)}&limit=1")
        return _normalize_user(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return _normalize_user(user)


def update_user_name(user_id, name):
    if USE_SUPABASE:
        _supabase_request("PATCH", "users", {"name": name}, query=f"id={_eq(user_id)}", select=False)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
    conn.commit()
    conn.close()


def update_user_password(user_id, password_hash):
    if USE_SUPABASE:
        _supabase_request("PATCH", "users", {"password_hash": password_hash}, query=f"id={_eq(user_id)}", select=False)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
    conn.commit()
    conn.close()


def create_session(user_id, session_id=None, expires_days=7):
    session_id = session_id or str(uuid.uuid4())
    expires_at = _utc_now() + datetime.timedelta(days=expires_days)
    if USE_SUPABASE:
        _supabase_request("POST", "sessions", {"id": session_id, "user_id": user_id, "expires_at": _iso(expires_at)}, select=False)
        return session_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)", (session_id, user_id, expires_at))
    conn.commit()
    conn.close()
    return session_id


def validate_session(session_id):
    if USE_SUPABASE:
        now = parse.quote(_iso(_utc_now()), safe="")
        rows = _supabase_request("GET", "sessions", query=f"id={_eq(session_id)}&expires_at=gt.{now}&limit=1")
        return dict(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ? AND expires_at > ?", (session_id, _utc_now()))
    session = cursor.fetchone()
    conn.close()
    return dict(session) if session else None


def delete_session(session_id):
    if not session_id:
        return
    if USE_SUPABASE:
        _supabase_request("DELETE", "sessions", query=f"id={_eq(session_id)}", select=False)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def delete_user_sessions(user_id, keep_session_id=None):
    """Revoke all sessions for a user, optionally keeping one (e.g. the current one)."""
    if USE_SUPABASE:
        query = f"user_id={_eq(user_id)}"
        if keep_session_id:
            query += f"&id=neq.{parse.quote(str(keep_session_id), safe='')}"
        _supabase_request("DELETE", "sessions", query=query, select=False)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    if keep_session_id:
        cursor.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, keep_session_id))
    else:
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_user_progress(user_id):
    if USE_SUPABASE:
        rows = _supabase_request("GET", "user_progress", query=f"user_id={_eq(user_id)}&order=answered_at.desc")
        return rows or []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_progress WHERE user_id = ? ORDER BY answered_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_user_progress(user_id, question_id, is_correct, time_spent, subject, system=None):
    row = {
        "user_id": user_id,
        "question_id": str(question_id),
        "is_correct": bool(is_correct),
        "time_spent": int(time_spent or 0),
        "subject": subject,
        "system": system,
    }
    if USE_SUPABASE:
        rows = _supabase_request("POST", "user_progress", row)
        return rows[0]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_progress (user_id, question_id, is_correct, time_spent, subject, system) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, str(question_id), bool(is_correct), int(time_spent or 0), subject, system),
    )
    progress_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return progress_id


def record_test_answer(test_session_id, user_id, question_id, selected_option, is_correct, time_spent):
    row = {
        "test_session_id": test_session_id,
        "user_id": user_id,
        "question_id": str(question_id),
        "selected_option": int(selected_option),
        "is_correct": bool(is_correct),
        "time_spent": int(time_spent or 0),
    }
    if USE_SUPABASE:
        _supabase_request(
            "POST",
            "test_answers",
            row,
            query="on_conflict=test_session_id,question_id",
            select=False,
        )
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO test_answers (test_session_id, user_id, question_id, selected_option, is_correct, time_spent)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(test_session_id, question_id) DO UPDATE SET
            selected_option = excluded.selected_option,
            is_correct = excluded.is_correct,
            time_spent = excluded.time_spent,
            answered_at = CURRENT_TIMESTAMP
        """,
        (test_session_id, user_id, str(question_id), int(selected_option), bool(is_correct), int(time_spent or 0)),
    )
    conn.commit()
    conn.close()


def get_test_answers(test_session_id):
    if USE_SUPABASE:
        rows = _supabase_request("GET", "test_answers", query=f"test_session_id={_eq(test_session_id)}&order=answered_at.asc")
        return rows or []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM test_answers WHERE test_session_id = ? ORDER BY answered_at ASC", (test_session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_test_session(user_id, mode, question_ids, total_questions, block_info=None):
    if USE_SUPABASE:
        rows = _supabase_request("POST", "test_sessions", {
            "user_id": user_id,
            "mode": mode,
            "question_ids": question_ids,
            "total_questions": int(total_questions),
            "block_info": block_info,
        })
        return rows[0]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO test_sessions (user_id, mode, question_ids, total_questions, block_info) VALUES (?, ?, ?, ?, ?)",
        (user_id, mode, json.dumps(question_ids), int(total_questions), json.dumps(block_info) if block_info else None),
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_test_session(session_id):
    if USE_SUPABASE:
        rows = _supabase_request("GET", "test_sessions", query=f"id={_eq(session_id)}&limit=1")
        return _normalize_test_session(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM test_sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    conn.close()
    return _normalize_test_session(session)


def get_user_test_sessions(user_id):
    """Return all test sessions for a user, newest first."""
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET",
            "test_sessions",
            query=f"user_id={_eq(user_id)}&order=created_at.desc,id.desc",
        )
        return [_normalize_test_session(row) for row in (rows or [])]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM test_sessions WHERE user_id = ? ORDER BY datetime(created_at) DESC, id DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [_normalize_test_session(row) for row in rows]


def update_test_session(session_id, current_question=None, score=None, completed=False):
    updates = {}
    if current_question is not None:
        updates["current_question"] = int(current_question)
    if score is not None:
        updates["score"] = int(score)
    if completed:
        updates["completed"] = True
        updates["completed_at"] = _iso(_utc_now())
    if not updates:
        return
    if USE_SUPABASE:
        _supabase_request("PATCH", "test_sessions", updates, query=f"id={_eq(session_id)}", select=False)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    parts = []
    params = []
    for key, value in updates.items():
        parts.append(f"{key} = ?")
        params.append(value)
    params.append(session_id)
    cursor.execute(f"UPDATE test_sessions SET {', '.join(parts)} WHERE id = ?", params)
    conn.commit()
    conn.close()
