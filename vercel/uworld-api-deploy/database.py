import datetime
import json
import os
import sqlite3
import uuid
from urllib import parse
from urllib import request as urlrequest

MAX_TELEMETRY_EVENTS_PER_SESSION = 500

try:
    import psycopg
except ImportError:  # optional outside persistent Postgres environments
    psycopg = None


def _env(name, default=""):
    value = os.environ.get(name, default)
    if isinstance(value, str):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
    return value


DB_PATH = _env("SQLITE_DATABASE_PATH") or _env("DATABASE_URL", "/tmp/uworld.db")
SUPABASE_URL = _env("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_ANON_KEY", "")
POSTGRES_URL = _env("POSTGRES_URL_NON_POOLING") or _env("POSTGRES_URL", "")
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
    if method == "POST":
        req.add_header("Prefer", "resolution=merge-duplicates")
        if select:
            req.add_header("Prefer", "return=representation")
    elif method == "PATCH" and select:
        req.add_header("Prefer", "return=representation")
    with urlrequest.urlopen(req, timeout=15) as response:
        data = response.read().decode("utf-8")
        return json.loads(data) if data else None


def _eq(value):
    return "eq." + parse.quote(str(value), safe="")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_postgres_schema():
    if not POSTGRES_URL or psycopg is None:
        return
    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_progress (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    question_id TEXT NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    time_spent INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    system TEXT,
                    answered_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_sessions (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    mode TEXT NOT NULL,
                    question_ids JSONB NOT NULL,
                    total_questions INTEGER NOT NULL,
                    current_question INTEGER DEFAULT 0,
                    score INTEGER,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    block_info JSONB
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_answers (
                    id BIGSERIAL PRIMARY KEY,
                    test_session_id BIGINT NOT NULL REFERENCES test_sessions (id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    question_id TEXT NOT NULL,
                    selected_option INTEGER NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    time_spent INTEGER NOT NULL DEFAULT 0,
                    answered_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(test_session_id, question_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS render_overrides (
                    question_id TEXT PRIMARY KEY,
                    changes JSONB NOT NULL,
                    reason TEXT,
                    updated_by TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role"
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO service_role"
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO service_role"
            )
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_telemetry_events (
                    id BIGSERIAL PRIMARY KEY,
                    test_session_id BIGINT NOT NULL REFERENCES test_sessions (id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    question_id TEXT,
                    question_index INTEGER,
                    block INTEGER,
                    event_type TEXT NOT NULL,
                    payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cursor.execute("NOTIFY pgrst, 'reload schema'")
        conn.commit()


def init_db():
    if USE_SUPABASE:
        init_postgres_schema()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS render_overrides (
            question_id TEXT PRIMARY KEY,
            changes TEXT NOT NULL,
            reason TEXT,
            updated_by TEXT,
            active BOOLEAN DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_telemetry_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question_id TEXT,
            question_index INTEGER,
            block INTEGER,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        session["block_info"] = (
            json.dumps(session.get("block_info"))
            if session.get("block_info") is not None
            else None
        )
    return session


def create_user(email, password_hash, name=""):
    if USE_SUPABASE:
        rows = _supabase_request(
            "POST",
            "users",
            {"email": email, "password_hash": password_hash, "name": name},
        )
        return rows[0]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
        (email, password_hash, name),
    )
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
        _supabase_request(
            "PATCH", "users", {"name": name}, query=f"id={_eq(user_id)}", select=False
        )
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
    conn.commit()
    conn.close()


def update_user_password(user_id, password_hash):
    if USE_SUPABASE:
        _supabase_request(
            "PATCH",
            "users",
            {"password_hash": password_hash},
            query=f"id={_eq(user_id)}",
            select=False,
        )
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
    )
    conn.commit()
    conn.close()


def create_session(user_id, session_id=None, expires_days=7):
    session_id = session_id or str(uuid.uuid4())
    expires_at = _utc_now() + datetime.timedelta(days=expires_days)
    if USE_SUPABASE:
        _supabase_request(
            "POST",
            "sessions",
            {"id": session_id, "user_id": user_id, "expires_at": _iso(expires_at)},
            select=False,
        )
        return session_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
        (session_id, user_id, expires_at),
    )
    conn.commit()
    conn.close()
    return session_id


def validate_session(session_id):
    if USE_SUPABASE:
        now = parse.quote(_iso(_utc_now()), safe="")
        rows = _supabase_request(
            "GET", "sessions", query=f"id={_eq(session_id)}&expires_at=gt.{now}&limit=1"
        )
        return dict(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM sessions WHERE id = ? AND expires_at > ?",
        (session_id, _utc_now()),
    )
    session = cursor.fetchone()
    conn.close()
    return dict(session) if session else None


def delete_session(session_id):
    if not session_id:
        return
    if USE_SUPABASE:
        _supabase_request(
            "DELETE", "sessions", query=f"id={_eq(session_id)}", select=False
        )
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
        cursor.execute(
            "DELETE FROM sessions WHERE user_id = ? AND id != ?",
            (user_id, keep_session_id),
        )
    else:
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_user_progress(user_id):
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET",
            "user_progress",
            query=f"user_id={_eq(user_id)}&order=answered_at.desc",
        )
        return rows or []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM user_progress WHERE user_id = ? ORDER BY answered_at DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_user_progress(
    user_id, question_id, is_correct, time_spent, subject, system=None
):
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
        (
            user_id,
            str(question_id),
            bool(is_correct),
            int(time_spent or 0),
            subject,
            system,
        ),
    )
    progress_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return progress_id


def record_test_answer(
    test_session_id, user_id, question_id, selected_option, is_correct, time_spent
):
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
        (
            test_session_id,
            user_id,
            str(question_id),
            int(selected_option),
            bool(is_correct),
            int(time_spent or 0),
        ),
    )
    conn.commit()
    conn.close()


def get_test_answers(test_session_id):
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET",
            "test_answers",
            query=f"test_session_id={_eq(test_session_id)}&order=answered_at.asc",
        )
        return rows or []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM test_answers WHERE test_session_id = ? ORDER BY answered_at ASC",
        (test_session_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_test_session(user_id, mode, question_ids, total_questions, block_info=None):
    if USE_SUPABASE:
        rows = _supabase_request(
            "POST",
            "test_sessions",
            {
                "user_id": user_id,
                "mode": mode,
                "question_ids": question_ids,
                "total_questions": int(total_questions),
                "block_info": block_info,
            },
        )
        return rows[0]["id"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO test_sessions (user_id, mode, question_ids, total_questions, block_info) VALUES (?, ?, ?, ?, ?)",
        (
            user_id,
            mode,
            json.dumps(question_ids),
            int(total_questions),
            json.dumps(block_info) if block_info else None,
        ),
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_test_session(session_id):
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET", "test_sessions", query=f"id={_eq(session_id)}&limit=1"
        )
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
        _supabase_request(
            "PATCH",
            "test_sessions",
            updates,
            query=f"id={_eq(session_id)}",
            select=False,
        )
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


def _normalize_render_override(row):
    if not row:
        return None
    override = dict(row)
    if USE_SUPABASE:
        override["changes"] = override.get("changes") or {}
    else:
        try:
            override["changes"] = json.loads(override.get("changes") or "{}")
        except (TypeError, ValueError):
            override["changes"] = {}
    return override


def get_render_override(question_id):
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET", "render_overrides", query=f"question_id={_eq(question_id)}&limit=1"
        )
        return _normalize_render_override(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM render_overrides WHERE question_id = ? LIMIT 1",
        (str(question_id),),
    )
    row = cursor.fetchone()
    conn.close()
    return _normalize_render_override(row)


def list_render_overrides(active_only=False):
    if USE_SUPABASE:
        query = "order=updated_at.desc"
        if active_only:
            query = f"active=eq.true&{query}"
        rows = _supabase_request("GET", "render_overrides", query=query) or []
        return [_normalize_render_override(row) for row in rows]
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM render_overrides"
    params = ()
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY datetime(updated_at) DESC, question_id ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [_normalize_render_override(row) for row in rows]


def upsert_render_override(question_id, changes, reason="", updated_by="", active=True):
    row = {
        "question_id": str(question_id),
        "changes": changes,
        "reason": reason or "",
        "updated_by": updated_by or "",
        "active": bool(active),
        "updated_at": _iso(_utc_now()),
    }
    if USE_SUPABASE:
        rows = _supabase_request(
            "POST",
            "render_overrides",
            row,
            query="on_conflict=question_id",
        )
        return (
            _normalize_render_override(rows[0])
            if rows
            else get_render_override(question_id)
        )
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO render_overrides (question_id, changes, reason, updated_by, active, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(question_id) DO UPDATE SET
            changes = excluded.changes,
            reason = excluded.reason,
            updated_by = excluded.updated_by,
            active = excluded.active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            str(question_id),
            json.dumps(changes),
            reason or "",
            updated_by or "",
            1 if active else 0,
        ),
    )
    conn.commit()
    conn.close()
    return get_render_override(question_id)


def delete_render_override(question_id):
    if USE_SUPABASE:
        _supabase_request(
            "DELETE",
            "render_overrides",
            query=f"question_id={_eq(question_id)}",
            select=False,
        )
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM render_overrides WHERE question_id = ?", (str(question_id),)
    )
    conn.commit()
    conn.close()


def _normalize_telemetry_event(row):
    if not row:
        return None
    event = dict(row)
    if USE_SUPABASE:
        event["payload"] = event.get("payload") or {}
    else:
        try:
            event["payload"] = json.loads(event.get("payload") or "{}")
        except (TypeError, ValueError):
            event["payload"] = {}
    return event


def create_telemetry_event(
    test_session_id,
    user_id,
    event_type,
    payload=None,
    question_id=None,
    question_index=None,
    block=None,
):
    row = {
        "test_session_id": int(test_session_id),
        "user_id": int(user_id),
        "question_id": str(question_id) if question_id is not None else None,
        "question_index": int(question_index) if question_index is not None else None,
        "block": int(block) if block is not None else None,
        "event_type": str(event_type),
        "payload": payload or {},
    }
    if USE_SUPABASE:
        rows = _supabase_request("POST", "session_telemetry_events", row)
        return _normalize_telemetry_event(rows[0]) if rows else None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO session_telemetry_events (
            test_session_id, user_id, question_id, question_index, block, event_type, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(test_session_id),
            int(user_id),
            str(question_id) if question_id is not None else None,
            int(question_index) if question_index is not None else None,
            int(block) if block is not None else None,
            str(event_type),
            json.dumps(payload or {}),
        ),
    )
    event_id = cursor.lastrowid
    cursor.execute(
        """
        DELETE FROM session_telemetry_events
        WHERE test_session_id = ? AND id NOT IN (
            SELECT id FROM session_telemetry_events
            WHERE test_session_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (int(test_session_id), int(test_session_id), MAX_TELEMETRY_EVENTS_PER_SESSION),
    )
    conn.commit()
    cursor.execute(
        "SELECT * FROM session_telemetry_events WHERE id = ? LIMIT 1", (event_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return _normalize_telemetry_event(row)


def list_telemetry_events(test_session_id=None, event_type=None, limit=100):
    limit = max(1, min(int(limit or 100), 500))
    if USE_SUPABASE:
        query = f"order=created_at.desc&limit={limit}"
        if test_session_id is not None:
            query = f"test_session_id={_eq(test_session_id)}&{query}"
        if event_type:
            query = f"event_type={_eq(event_type)}&{query}"
        rows = _supabase_request("GET", "session_telemetry_events", query=query) or []
        return [_normalize_telemetry_event(row) for row in rows]
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM session_telemetry_events"
    clauses = []
    params = []
    if test_session_id is not None:
        clauses.append("test_session_id = ?")
        params.append(int(test_session_id))
    if event_type:
        clauses.append("event_type = ?")
        params.append(str(event_type))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [_normalize_telemetry_event(row) for row in rows]
