"""Unit tests for database helpers, the SQLite CRUD path, and the Supabase branch.

The API contract suite exercises database.py only through the SQLite-backed
Flask app. These tests cover the small pure helpers plus the Supabase code
paths (by toggling ``USE_SUPABASE`` and stubbing ``_supabase_request``), which
are otherwise never executed.
"""
import datetime
import os
import pathlib
import sys
import tempfile
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

import database


class EnvHelperTests(unittest.TestCase):
    def test_strips_matching_surrounding_quotes(self):
        os.environ["_DB_TEST_QUOTED"] = '"hello"'
        os.environ["_DB_TEST_SQUOTED"] = "'world'"
        try:
            self.assertEqual(database._env("_DB_TEST_QUOTED"), "hello")
            self.assertEqual(database._env("_DB_TEST_SQUOTED"), "world")
        finally:
            del os.environ["_DB_TEST_QUOTED"]
            del os.environ["_DB_TEST_SQUOTED"]

    def test_strips_whitespace_and_uses_default(self):
        os.environ["_DB_TEST_WS"] = "  spaced  "
        try:
            self.assertEqual(database._env("_DB_TEST_WS"), "spaced")
        finally:
            del os.environ["_DB_TEST_WS"]
        self.assertEqual(database._env("_DB_TEST_MISSING", "fallback"), "fallback")

    def test_mismatched_quotes_are_left_intact(self):
        os.environ["_DB_TEST_MISMATCH"] = '"oops'
        try:
            self.assertEqual(database._env("_DB_TEST_MISMATCH"), '"oops')
        finally:
            del os.environ["_DB_TEST_MISMATCH"]


class SmallHelperTests(unittest.TestCase):
    def test_iso_passes_through_strings(self):
        self.assertEqual(database._iso("2024-01-01T00:00:00Z"), "2024-01-01T00:00:00Z")

    def test_iso_formats_datetime_with_z_suffix(self):
        dt = datetime.datetime(2024, 1, 2, 3, 4, 5)
        self.assertEqual(database._iso(dt), "2024-01-02T03:04:05Z")

    def test_eq_url_encodes_value(self):
        self.assertEqual(database._eq("a b&c"), "eq.a%20b%26c")

    def test_supabase_headers_carry_key_and_bearer(self):
        original = database.SUPABASE_KEY
        try:
            database.SUPABASE_KEY = "secret-key"
            headers = database._supabase_headers()
            self.assertEqual(headers["apikey"], "secret-key")
            self.assertEqual(headers["Authorization"], "Bearer secret-key")
            self.assertEqual(headers["Content-Type"], "application/json")
        finally:
            database.SUPABASE_KEY = original

    def test_normalize_user(self):
        self.assertIsNone(database._normalize_user(None))
        self.assertEqual(database._normalize_user({"id": 1}), {"id": 1})

    def test_using_ephemeral_database_reflects_config(self):
        saved_use, saved_path = database.USE_SUPABASE, database.DB_PATH
        try:
            database.USE_SUPABASE = False
            database.DB_PATH = "/tmp/uworld.db"
            self.assertTrue(database.using_ephemeral_database())
            database.DB_PATH = "/var/lib/uworld.db"
            self.assertFalse(database.using_ephemeral_database())
            database.DB_PATH = "/tmp/uworld.db"
            database.USE_SUPABASE = True
            self.assertFalse(database.using_ephemeral_database())
        finally:
            database.USE_SUPABASE, database.DB_PATH = saved_use, saved_path


class NormalizeTestSessionTests(unittest.TestCase):
    def test_returns_none_for_falsy_row(self):
        self.assertIsNone(database._normalize_test_session(None))

    def test_sqlite_row_passes_through_untouched(self):
        saved = database.USE_SUPABASE
        try:
            database.USE_SUPABASE = False
            row = {"id": 1, "question_ids": '["a"]', "block_info": None}
            self.assertEqual(database._normalize_test_session(row), row)
        finally:
            database.USE_SUPABASE = saved

    def test_supabase_row_serializes_json_columns(self):
        saved = database.USE_SUPABASE
        try:
            database.USE_SUPABASE = True
            row = {"id": 1, "question_ids": ["a", "b"], "block_info": {"blocks": 2}}
            normalized = database._normalize_test_session(row)
            self.assertEqual(normalized["question_ids"], '["a", "b"]')
            self.assertEqual(normalized["block_info"], '{"blocks": 2}')
        finally:
            database.USE_SUPABASE = saved

    def test_supabase_row_keeps_null_block_info_as_none(self):
        saved = database.USE_SUPABASE
        try:
            database.USE_SUPABASE = True
            normalized = database._normalize_test_session({"question_ids": None, "block_info": None})
            self.assertEqual(normalized["question_ids"], "[]")
            self.assertIsNone(normalized["block_info"])
        finally:
            database.USE_SUPABASE = saved


class _RecordingSupabase:
    """Callable stub that records calls and returns queued responses."""

    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])

    def __call__(self, method, table, body=None, query="", select=True):
        self.calls.append(
            {"method": method, "table": table, "body": body, "query": query, "select": select}
        )
        return self._responses.pop(0) if self._responses else None


class SupabaseBranchTests(unittest.TestCase):
    """Drive the ``USE_SUPABASE`` code paths without any real HTTP."""

    def setUp(self):
        self._saved_use = database.USE_SUPABASE
        self._saved_req = database._supabase_request
        database.USE_SUPABASE = True

    def tearDown(self):
        database.USE_SUPABASE = self._saved_use
        database._supabase_request = self._saved_req

    def _stub(self, responses=None):
        stub = _RecordingSupabase(responses)
        database._supabase_request = stub
        return stub

    def test_create_user_posts_and_returns_id(self):
        stub = self._stub([[{"id": 7}]])
        self.assertEqual(database.create_user("a@b.com", "hash", "Name"), 7)
        call = stub.calls[0]
        self.assertEqual((call["method"], call["table"]), ("POST", "users"))
        self.assertEqual(call["body"], {"email": "a@b.com", "password_hash": "hash", "name": "Name"})

    def test_get_user_by_email_returns_first_row_or_none(self):
        stub = self._stub([[{"id": 1, "email": "a@b.com"}], []])
        self.assertEqual(database.get_user_by_email("a@b.com")["id"], 1)
        self.assertIsNone(database.get_user_by_email("missing@b.com"))
        self.assertIn("email=eq.a%40b.com", stub.calls[0]["query"])

    def test_get_user_by_id_returns_first_row_or_none(self):
        self._stub([[{"id": 3}], []])
        self.assertEqual(database.get_user_by_id(3)["id"], 3)
        self.assertIsNone(database.get_user_by_id(99))

    def test_update_user_name_and_password_patch(self):
        stub = self._stub([None, None])
        database.update_user_name(5, "New")
        database.update_user_password(5, "newhash")
        self.assertEqual(stub.calls[0]["method"], "PATCH")
        self.assertEqual(stub.calls[0]["body"], {"name": "New"})
        self.assertEqual(stub.calls[1]["body"], {"password_hash": "newhash"})

    def test_create_session_generates_id_and_posts(self):
        stub = self._stub([None])
        sid = database.create_session(5, expires_days=3)
        self.assertTrue(sid)
        body = stub.calls[0]["body"]
        self.assertEqual(body["user_id"], 5)
        self.assertEqual(body["id"], sid)
        self.assertTrue(body["expires_at"].endswith("Z"))

    def test_validate_session_returns_row_or_none(self):
        self._stub([[{"id": "sess"}], []])
        self.assertEqual(database.validate_session("sess")["id"], "sess")
        self.assertIsNone(database.validate_session("expired"))

    def test_delete_session_noops_on_empty_id(self):
        stub = self._stub()
        database.delete_session("")
        self.assertEqual(stub.calls, [])
        database.delete_session("real")
        self.assertEqual(stub.calls[0]["method"], "DELETE")

    def test_delete_user_sessions_keeps_current_when_requested(self):
        stub = self._stub([None, None])
        database.delete_user_sessions(5)
        self.assertEqual(stub.calls[0]["query"], "user_id=eq.5")
        database.delete_user_sessions(5, keep_session_id="keep-me")
        self.assertIn("id=neq.keep-me", stub.calls[1]["query"])

    def test_progress_read_and_write(self):
        stub = self._stub([[{"id": 1}], [{"id": 9}]])
        self.assertEqual(database.get_user_progress(5), [{"id": 1}])
        pid = database.update_user_progress(5, "q1", True, 12, "Path", "GI")
        self.assertEqual(pid, 9)
        body = stub.calls[1]["body"]
        self.assertEqual(body["question_id"], "q1")
        self.assertIs(body["is_correct"], True)
        self.assertEqual(body["system"], "GI")

    def test_get_user_progress_defaults_to_empty_list(self):
        self._stub([None])
        self.assertEqual(database.get_user_progress(5), [])

    def test_record_test_answer_uses_on_conflict(self):
        stub = self._stub([None])
        database.record_test_answer(1, 5, "q1", 2, True, 30)
        call = stub.calls[0]
        self.assertEqual(call["table"], "test_answers")
        self.assertIn("on_conflict=test_session_id,question_id", call["query"])
        self.assertEqual(call["body"]["selected_option"], 2)

    def test_get_test_answers_defaults_to_empty_list(self):
        self._stub([None])
        self.assertEqual(database.get_test_answers(1), [])

    def test_create_test_session_returns_id(self):
        stub = self._stub([[{"id": 55}]])
        sid = database.create_test_session(5, "nbme120", ["q1", "q2"], 2, block_info={"b": 1})
        self.assertEqual(sid, 55)
        self.assertEqual(stub.calls[0]["body"]["question_ids"], ["q1", "q2"])

    def test_get_test_session_normalizes_json(self):
        self._stub([[{"id": 1, "question_ids": ["q1"], "block_info": {"b": 1}}], []])
        session = database.get_test_session(1)
        self.assertEqual(session["question_ids"], '["q1"]')
        self.assertEqual(session["block_info"], '{"b": 1}')
        self.assertIsNone(database.get_test_session(999))

    def test_get_user_test_sessions_normalizes_each_row(self):
        self._stub([[{"id": 1, "question_ids": ["q1"], "block_info": None}]])
        rows = database.get_user_test_sessions(5)
        self.assertEqual(rows[0]["question_ids"], '["q1"]')

    def test_update_test_session_builds_patch_and_noops_when_empty(self):
        stub = self._stub([None])
        database.update_test_session(1, current_question=5, score=80, completed=True)
        body = stub.calls[0]["body"]
        self.assertEqual(body["current_question"], 5)
        self.assertEqual(body["score"], 80)
        self.assertIs(body["completed"], True)
        self.assertIn("completed_at", body)
        # No fields to update -> no request issued.
        database.update_test_session(1)
        self.assertEqual(len(stub.calls), 1)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SupabaseRequestTests(unittest.TestCase):
    """Exercise the low-level ``_supabase_request`` HTTP builder with a fake urlopen."""

    def setUp(self):
        self._saved_open = database.urlrequest.urlopen
        self._saved_url = database.SUPABASE_URL
        self._saved_key = database.SUPABASE_KEY
        database.SUPABASE_URL = "https://proj.supabase.co"
        database.SUPABASE_KEY = "svc-key"
        self.captured = {}

        def fake_urlopen(req, timeout=None):
            self.captured["url"] = req.full_url
            self.captured["method"] = req.get_method()
            self.captured["data"] = req.data
            self.captured["headers"] = dict(req.header_items())
            return _FakeResponse(self._payload)

        database.urlrequest.urlopen = fake_urlopen

    def tearDown(self):
        database.urlrequest.urlopen = self._saved_open
        database.SUPABASE_URL = self._saved_url
        database.SUPABASE_KEY = self._saved_key

    def test_get_parses_json_body_and_builds_query_url(self):
        self._payload = b'[{"id": 1}]'
        result = database._supabase_request("GET", "users", query="id=eq.1&limit=1")
        self.assertEqual(result, [{"id": 1}])
        self.assertEqual(
            self.captured["url"], "https://proj.supabase.co/rest/v1/users?id=eq.1&limit=1"
        )
        self.assertEqual(self.captured["method"], "GET")

    def test_post_serializes_body_and_sets_representation_header(self):
        self._payload = b'[{"id": 9}]'
        result = database._supabase_request("POST", "users", body={"email": "a@b.com"})
        self.assertEqual(result, [{"id": 9}])
        self.assertEqual(self.captured["data"], b'{"email": "a@b.com"}')
        # Header keys are capitalized by urllib; match case-insensitively.
        headers = {k.lower(): v for k, v in self.captured["headers"].items()}
        self.assertEqual(headers.get("prefer"), "return=representation")

    def test_post_without_select_uses_merge_duplicates_header(self):
        self._payload = b""
        database._supabase_request("POST", "sessions", body={"id": "s"}, select=False)
        headers = {k.lower(): v for k, v in self.captured["headers"].items()}
        self.assertEqual(headers.get("prefer"), "resolution=merge-duplicates")

    def test_empty_response_body_returns_none(self):
        self._payload = b""
        self.assertIsNone(
            database._supabase_request("DELETE", "sessions", query="id=eq.x", select=False)
        )


class SqliteRoundTripTests(unittest.TestCase):
    """End-to-end CRUD against a throwaway SQLite file (no Supabase)."""

    def setUp(self):
        self._saved_use = database.USE_SUPABASE
        self._saved_path = database.DB_PATH
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        database.USE_SUPABASE = False
        database.DB_PATH = self._tmp.name
        database.init_db()

    def tearDown(self):
        database.USE_SUPABASE = self._saved_use
        database.DB_PATH = self._saved_path
        os.unlink(self._tmp.name)

    def test_full_user_session_and_test_lifecycle(self):
        uid = database.create_user("round@trip.com", "hash", "Round Trip")
        self.assertEqual(database.get_user_by_email("round@trip.com")["id"], uid)
        self.assertEqual(database.get_user_by_id(uid)["name"], "Round Trip")

        database.update_user_name(uid, "Renamed")
        database.update_user_password(uid, "newhash")
        refreshed = database.get_user_by_id(uid)
        self.assertEqual(refreshed["name"], "Renamed")
        self.assertEqual(refreshed["password_hash"], "newhash")

        # Sessions: create two, validate, then revoke all but one.
        sid1 = database.create_session(uid)
        sid2 = database.create_session(uid)
        self.assertIsNotNone(database.validate_session(sid1))
        database.delete_user_sessions(uid, keep_session_id=sid2)
        self.assertIsNone(database.validate_session(sid1))
        self.assertIsNotNone(database.validate_session(sid2))
        database.delete_session(sid2)
        self.assertIsNone(database.validate_session(sid2))

        # Revoking every session (no keep id) clears them all.
        sid3 = database.create_session(uid)
        database.delete_user_sessions(uid)
        self.assertIsNone(database.validate_session(sid3))

        # Progress rows are stored and read newest-first.
        database.update_user_progress(uid, "q1", True, 10, "Path", "GI")
        progress = database.get_user_progress(uid)
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]["question_id"], "q1")

        # Test session + answers with upsert semantics.
        tsid = database.create_test_session(uid, "custom", ["q1", "q2"], 2, block_info={"b": 1})
        session = database.get_test_session(tsid)
        self.assertEqual(session["total_questions"], 2)
        database.record_test_answer(tsid, uid, "q1", 1, True, 5)
        database.record_test_answer(tsid, uid, "q1", 2, False, 9)  # same question -> upsert
        answers = database.get_test_answers(tsid)
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["selected_option"], 2)
        self.assertEqual(answers[0]["is_correct"], 0)

        database.update_test_session(tsid, current_question=1, score=1, completed=True)
        updated = database.get_test_session(tsid)
        self.assertEqual(updated["current_question"], 1)
        self.assertEqual(updated["score"], 1)
        self.assertTrue(updated["completed"])
        self.assertIn(tsid, [s["id"] for s in database.get_user_test_sessions(uid)])


if __name__ == "__main__":
    unittest.main()
