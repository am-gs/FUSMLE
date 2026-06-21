import json
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

API_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(API_DIR))

from database import create_test_session
from index import app


class ApiContractTests(unittest.TestCase):
    def auth_headers(self):
        client = app.test_client()
        import uuid

        email = f"contract-{uuid.uuid4().hex}@example.com"
        response = client.post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "Contract User"},
        )
        if response.status_code == 409:
            response = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        self.assertIn(response.status_code, (200, 201))
        token = response.get_json()["token"]
        self.assertNotEqual(token, "anon-token")
        return {"Authorization": f"Bearer {token}"}

    def test_auth_register_login_and_session_use_real_user_tokens(self):
        client = app.test_client()
        import uuid

        email = f"auth-{uuid.uuid4().hex}@example.com"
        register = client.post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "Auth Contract"},
        )
        self.assertIn(register.status_code, (201, 409))

        login = client.post(
            "/api/auth/login", json={"email": email, "password": "TestPass123!"}
        )
        self.assertEqual(login.status_code, 200)
        payload = login.get_json()
        self.assertNotEqual(payload["token"], "anon-token")
        self.assertEqual(payload["user"]["email"], email)

        session = client.get(
            "/api/session", headers={"Authorization": f"Bearer {payload['token']}"}
        )
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.get_json()["user"]["email"], email)

        self.assertEqual(app.test_client().get("/api/session").status_code, 401)

    def test_cookie_session_survives_stale_authorization_header(self):
        client = app.test_client()
        import uuid

        email = f"cookie-fallback-{uuid.uuid4().hex}@example.com"
        register = client.post(
            "/api/register",
            json={
                "email": email,
                "password": "TestPass123!",
                "name": "Cookie Fallback",
            },
        )
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = register.get_json()["token"]

        client.set_cookie("token", token)
        session = client.get(
            "/api/session", headers={"Authorization": "Bearer stale-token"}
        )
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.get_json()["user"]["email"], email)

    def test_logout_revokes_session_server_side(self):
        client = app.test_client()
        import uuid

        email = f"logout-{uuid.uuid4().hex}@example.com"
        register = client.post(
            "/api/register",
            json={
                "email": email,
                "password": "TestPass123!",
                "name": "Logout Contract",
            },
        )
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = register.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Session is valid before logout (header + cookie both work).
        self.assertEqual(client.get("/api/session", headers=headers).status_code, 200)

        logout = client.post("/api/logout", headers=headers)
        self.assertEqual(logout.status_code, 200)

        # After logout the same token must be rejected via header and via cookie.
        self.assertEqual(
            app.test_client().get("/api/session", headers=headers).status_code, 401
        )
        cookie_client = app.test_client()
        cookie_client.set_cookie("token", token)
        self.assertEqual(cookie_client.get("/api/session").status_code, 401)

    def test_account_profile_and_password_updates(self):
        client = app.test_client()
        import uuid

        email = f"account-{uuid.uuid4().hex}@example.com"
        reg = client.post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "Old Name"},
        )
        self.assertIn(reg.status_code, (201, 409))
        if reg.status_code == 409:
            reg = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = reg.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Update display name
        upd = client.post(
            "/api/account/profile", json={"name": "New Name"}, headers=headers
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.get_json()["user"]["name"], "New Name")
        self.assertEqual(
            client.get("/api/session", headers=headers).get_json()["user"]["name"],
            "New Name",
        )

        # Empty name rejected; auth required (fresh client has no session cookie)
        self.assertEqual(
            client.post(
                "/api/account/profile", json={"name": "  "}, headers=headers
            ).status_code,
            400,
        )
        self.assertEqual(
            app.test_client()
            .post("/api/account/profile", json={"name": "x"})
            .status_code,
            401,
        )

        # Wrong current password rejected
        self.assertEqual(
            client.post(
                "/api/account/password",
                json={"currentPassword": "wrong", "newPassword": "Brandnew123!"},
                headers=headers,
            ).status_code,
            401,
        )
        # Too-short new password rejected
        self.assertEqual(
            client.post(
                "/api/account/password",
                json={"currentPassword": "TestPass123!", "newPassword": "short"},
                headers=headers,
            ).status_code,
            400,
        )
        # Valid change succeeds and the new password works for login; old one fails
        ok = client.post(
            "/api/account/password",
            json={"currentPassword": "TestPass123!", "newPassword": "Brandnew123!"},
            headers=headers,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(
            client.post(
                "/api/auth/login", json={"email": email, "password": "Brandnew123!"}
            ).status_code,
            200,
        )
        self.assertEqual(
            client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            ).status_code,
            401,
        )

    def test_password_change_revokes_other_sessions_but_keeps_current(self):
        import uuid

        email = f"pwsess-{uuid.uuid4().hex}@example.com"
        reg = app.test_client().post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "PW Sess"},
        )
        self.assertIn(reg.status_code, (201, 409))
        token_a = reg.get_json()["token"]
        # Second independent session for the same account.
        login_b = app.test_client().post(
            "/api/auth/login", json={"email": email, "password": "TestPass123!"}
        )
        token_b = login_b.get_json()["token"]
        self.assertNotEqual(token_a, token_b)

        # Both sessions valid before the change (use header-only clients to avoid cookie carryover).
        self.assertEqual(
            app.test_client()
            .get("/api/session", headers={"Authorization": f"Bearer {token_a}"})
            .status_code,
            200,
        )
        self.assertEqual(
            app.test_client()
            .get("/api/session", headers={"Authorization": f"Bearer {token_b}"})
            .status_code,
            200,
        )

        # Change password using session A.
        change = app.test_client().post(
            "/api/account/password",
            json={"currentPassword": "TestPass123!", "newPassword": "Rotated123!"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(change.status_code, 200)

        # Current session (A) survives; the other session (B) is revoked.
        self.assertEqual(
            app.test_client()
            .get("/api/session", headers={"Authorization": f"Bearer {token_a}"})
            .status_code,
            200,
        )
        self.assertEqual(
            app.test_client()
            .get("/api/session", headers={"Authorization": f"Bearer {token_b}"})
            .status_code,
            401,
        )

    def test_post_routes_reject_missing_json_without_500(self):
        client = app.test_client()
        self.assertEqual(client.post("/api/forgot-password").status_code, 400)
        self.assertEqual(client.post("/api/qbank/generate-test").status_code, 401)
        response = client.post("/api/qbank/test/999/submit")
        self.assertEqual(response.status_code, 401)

    def test_submit_requires_question_to_belong_to_session(self):
        client = app.test_client()
        headers = self.auth_headers()
        first = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        ).get_json()
        second = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 5}, headers=headers
        ).get_json()
        foreign_question_id = next(
            qid for qid in second["questionIds"] if qid not in first["questionIds"]
        )
        response = client.post(
            f"/api/qbank/test/{first['testSessionId']}/submit",
            json={"questionId": foreign_question_id, "selectedOption": 1},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Question does not belong to this test session",
        )

    def test_unsafe_question_is_blocked_from_delivery_and_scoring(self):
        client = app.test_client()
        import uuid

        email = f"unsafe-{uuid.uuid4().hex}@example.com"
        register = client.post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "Unsafe Row"},
        )
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = register.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = register.get_json()["user"]["id"]

        unsafe_qid = "nbme28_q0026"
        session_id = create_test_session(
            user_id=user_id,
            mode="test2",
            question_ids=[unsafe_qid],
            total_questions=1,
            block_info=[],
        )

        question_response = client.get(
            f"/api/qbank/test/{session_id}/question/0", headers=headers
        )
        self.assertEqual(question_response.status_code, 409)
        self.assertEqual(question_response.get_json()["questionId"], unsafe_qid)

        submit_response = client.post(
            f"/api/qbank/test/{session_id}/submit",
            json={"questionId": unsafe_qid, "selectedOption": 1},
            headers=headers,
        )
        self.assertEqual(submit_response.status_code, 409)
        self.assertEqual(submit_response.get_json()["questionId"], unsafe_qid)

        review_response = client.get(
            f"/api/qbank/test/{session_id}/review", headers=headers
        )
        self.assertEqual(review_response.status_code, 409)
        self.assertEqual(review_response.get_json()["questionId"], unsafe_qid)

    def test_qbank_browse_hides_unsafe_rows_by_default(self):
        client = app.test_client()
        hidden = client.get("/api/qbank/browse?q=nbme28_q0026&limit=5")
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.get_json()["items"], [])

        visible = client.get(
            "/api/qbank/browse?q=nbme28_q0026&include_unsafe=1&limit=5"
        )
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(
            [item["id"] for item in visible.get_json()["items"]], ["nbme28_q0026"]
        )

    def test_nbme_endpoint_session_order_and_boundary_questions(self):
        client = app.test_client()
        headers = self.auth_headers()
        response = client.post("/api/qbank/generate-nbme120", json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        block_ids = [qid for block in payload["blocks"] for qid in block["questionIds"]]
        self.assertEqual(payload["questionIds"], block_ids)
        self.assertEqual(len(payload["blocks"]), 6)
        self.assertEqual(
            [len(block["questionIds"]) for block in payload["blocks"]], [20] * 6
        )

        sid = payload["testSessionId"]
        for idx in [0, 19, 20, 39, 40, 59, 100, 119]:
            question_response = client.get(
                f"/api/qbank/test/{sid}/question/{idx}", headers=headers
            )
            self.assertEqual(question_response.status_code, 200)
            question = question_response.get_json()["question"]
            self.assertEqual(question["id"], payload["questionIds"][idx])

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertEqual(state_payload["questionIds"], payload["questionIds"])
        self.assertEqual(
            [block["questionIds"] for block in state_payload["blocks"]],
            [block["questionIds"] for block in payload["blocks"]],
        )

    def test_test2_endpoint_uses_frozen_120_manifest_order(self):
        client = app.test_client()
        headers = self.auth_headers()
        response = client.post("/api/qbank/generate-test2", json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        block_ids = [qid for block in payload["blocks"] for qid in block["questionIds"]]
        self.assertEqual(payload["questionIds"], block_ids)
        self.assertEqual(payload["format"], "test2")
        self.assertEqual(payload["manifestSlug"], "june2026_nbme120_candidate")
        self.assertEqual(payload["totalQuestions"], 120)
        self.assertEqual(len(payload["blocks"]), 6)
        self.assertEqual(
            [len(block["questionIds"]) for block in payload["blocks"]], [20] * 6
        )
        self.assertEqual(payload["sourceProxyForm"], "NBME 120")
        self.assertEqual(len(payload["sourceForms"]), 5)

        sid = payload["testSessionId"]
        for idx in [0, 19, 20, 39, 40, 59, 100, 119]:
            question_response = client.get(
                f"/api/qbank/test/{sid}/question/{idx}", headers=headers
            )
            self.assertEqual(question_response.status_code, 200)
            question = question_response.get_json()["question"]
            self.assertEqual(question["id"], payload["questionIds"][idx])

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertEqual(state_payload["questionIds"], payload["questionIds"])
        self.assertEqual(
            [block["questionIds"] for block in state_payload["blocks"]],
            [block["questionIds"] for block in payload["blocks"]],
        )

    def test_test1_endpoint_remains_a_compatible_alias(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post(
            "/api/qbank/generate-test1", json={}, headers=headers
        ).get_json()
        self.assertEqual(payload["format"], "test1")
        self.assertEqual(payload["totalQuestions"], 120)
        self.assertEqual(
            [len(block["questionIds"]) for block in payload["blocks"]], [20] * 6
        )

    def test_render_override_admin_endpoints_require_admin_auth(self):
        client = app.test_client()
        response = client.get("/api/admin/render-overrides")
        self.assertEqual(response.status_code, 403)

    def test_render_override_crud_and_runtime_application(self):
        client = app.test_client()
        headers = self.auth_headers()
        generated = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        )
        self.assertEqual(generated.status_code, 200)
        test_payload = generated.get_json()
        test_id = test_payload["testSessionId"]

        question_response = client.get(
            f"/api/qbank/test/{test_id}/question/0", headers=headers
        )
        self.assertEqual(question_response.status_code, 200)
        question = question_response.get_json()["question"]
        question_id = question["id"]

        override_payload = {
            "changes": {
                "text": "[LIVE OVERRIDE] " + question["text"],
                "imageUrls": ["/api/images_crop/live-override.webp"],
                "image_url": "/api/images_crop/live-override.webp",
                "tables": [
                    {"title": "Patched table", "headers": ["A"], "rows": [["1"]]}
                ],
                "option_table": {"headers": ["Col 1"], "rows": [["Value"]]},
            },
            "reason": "Live render audit patch",
            "active": True,
        }

        with patch.dict(
            os.environ,
            {"RENDER_OVERRIDE_ADMIN_TOKEN": "test-render-token"},
            clear=False,
        ):
            admin_headers = {"X-Render-Admin-Token": "test-render-token"}

            put_response = client.put(
                f"/api/admin/render-overrides/{question_id}",
                json=override_payload,
                headers=admin_headers,
            )
            self.assertEqual(put_response.status_code, 200)
            stored = put_response.get_json()
            self.assertEqual(stored["question_id"], question_id)
            self.assertEqual(stored["reason"], "Live render audit patch")
            self.assertTrue(stored["active"])
            self.assertEqual(
                stored["changes"]["imageUrls"], ["/api/images_crop/live-override.webp"]
            )

            get_response = client.get(
                f"/api/admin/render-overrides/{question_id}", headers=admin_headers
            )
            self.assertEqual(get_response.status_code, 200)
            fetched = get_response.get_json()
            self.assertEqual(fetched["question_id"], question_id)
            self.assertEqual(fetched["changes"]["option_table"]["headers"], ["Col 1"])

            list_response = client.get(
                "/api/admin/render-overrides?active=1", headers=admin_headers
            )
            self.assertEqual(list_response.status_code, 200)
            listed_ids = [
                row["question_id"] for row in list_response.get_json()["overrides"]
            ]
            self.assertIn(question_id, listed_ids)

            overridden_question = client.get(
                f"/api/qbank/test/{test_id}/question/0", headers=headers
            )
            self.assertEqual(overridden_question.status_code, 200)
            overridden_payload = overridden_question.get_json()["question"]
            self.assertTrue(overridden_payload["text"].startswith("[LIVE OVERRIDE] "))
            self.assertEqual(
                overridden_payload["imageUrls"], ["/api/images_crop/live-override.webp"]
            )
            self.assertEqual(
                overridden_payload["rendering_flag"]["reason"],
                "Live render audit patch",
            )
            self.assertEqual(overridden_payload["option_table"]["headers"], ["Col 1"])

            review_response = client.get(
                f"/api/qbank/test/{test_id}/review", headers=headers
            )
            self.assertEqual(review_response.status_code, 200)
            review_rows = review_response.get_json()["rows"]
            self.assertEqual(len(review_rows), 1)
            self.assertEqual(
                review_rows[0]["imageUrls"], ["/api/images_crop/live-override.webp"]
            )
            self.assertEqual(
                review_rows[0]["renderingFlag"]["reason"], "Live render audit patch"
            )
            self.assertEqual(review_rows[0]["optionTable"]["headers"], ["Col 1"])

            delete_response = client.delete(
                f"/api/admin/render-overrides/{question_id}", headers=admin_headers
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.get_json()["questionId"], question_id)

            missing_response = client.get(
                f"/api/admin/render-overrides/{question_id}", headers=admin_headers
            )
            self.assertEqual(missing_response.status_code, 404)

    def test_telemetry_admin_endpoints_require_admin_auth(self):
        client = app.test_client()
        response = client.get("/api/admin/telemetry")
        self.assertEqual(response.status_code, 403)

    def test_telemetry_event_round_trip_and_admin_listing(self):
        client = app.test_client()
        headers = self.auth_headers()
        generated = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        )
        self.assertEqual(generated.status_code, 200)
        test_id = generated.get_json()["testSessionId"]

        question_response = client.get(
            f"/api/qbank/test/{test_id}/question/0", headers=headers
        )
        self.assertEqual(question_response.status_code, 200)
        question = question_response.get_json()["question"]

        telemetry_response = client.post(
            f"/api/qbank/test/{test_id}/telemetry",
            json={
                "eventType": "question_loaded",
                "questionId": question["id"],
                "questionIndex": 0,
                "block": 1,
                "payload": {"mode": "timed", "expectedImages": 0},
            },
            headers=headers,
        )
        self.assertEqual(telemetry_response.status_code, 200)
        event = telemetry_response.get_json()["event"]
        self.assertEqual(event["test_session_id"], test_id)
        self.assertEqual(event["event_type"], "question_loaded")
        self.assertEqual(event["question_id"], question["id"])
        self.assertEqual(event["question_index"], 0)
        self.assertEqual(event["block"], 1)
        self.assertEqual(event["payload"]["mode"], "timed")

        with patch.dict(
            os.environ,
            {"RENDER_OVERRIDE_ADMIN_TOKEN": "test-render-token"},
            clear=False,
        ):
            admin_headers = {"X-Render-Admin-Token": "test-render-token"}
            session_events = client.get(
                f"/api/admin/telemetry/{test_id}", headers=admin_headers
            )
            self.assertEqual(session_events.status_code, 200)
            listed = session_events.get_json()["events"]
            self.assertGreaterEqual(len(listed), 1)
            self.assertEqual(listed[0]["event_type"], "question_loaded")
            self.assertEqual(listed[0]["question_id"], question["id"])

            filtered = client.get(
                f"/api/admin/telemetry?testSessionId={test_id}&eventType=question_loaded&limit=10",
                headers=admin_headers,
            )
            self.assertEqual(filtered.status_code, 200)
            filtered_events = filtered.get_json()["events"]
            self.assertGreaterEqual(len(filtered_events), 1)
            self.assertTrue(
                all(row["event_type"] == "question_loaded" for row in filtered_events)
            )

    def test_history_hides_in_progress_score_for_partial_exam(self):
        client = app.test_client()
        headers = self.auth_headers()
        generated = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 5}, headers=headers
        )
        self.assertEqual(generated.status_code, 200)
        test_id = generated.get_json()["testSessionId"]

        question_response = client.get(
            f"/api/qbank/test/{test_id}/question/0", headers=headers
        )
        self.assertEqual(question_response.status_code, 200)
        question_id = question_response.get_json()["question"]["id"]

        submit_response = client.post(
            f"/api/qbank/test/{test_id}/submit",
            json={"questionId": question_id, "selectedOption": 1, "timeSpent": 12},
            headers=headers,
        )
        self.assertEqual(submit_response.status_code, 200)

        history_response = client.get("/api/qbank/history", headers=headers)
        self.assertEqual(history_response.status_code, 200)
        sessions = history_response.get_json()["sessions"]
        matching = [row for row in sessions if row["id"] == test_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["answered"], 1)
        self.assertFalse(matching[0]["completed"])
        self.assertIsNone(matching[0]["score"])

    def test_nidhi_monitor_requires_admin_or_cron_auth(self):
        client = app.test_client()
        self.assertEqual(client.get("/api/admin/monitor/nidhi").status_code, 403)
        self.assertEqual(client.get("/api/admin/monitor/nidhi/run").status_code, 403)

    def test_nidhi_monitor_reports_active_named_exam_issues(self):
        client = app.test_client()
        email = "nidhitiyyagura@gmail.com"
        register = client.post(
            "/api/register",
            json={"email": email, "password": "TestPass123!", "name": "Nidhi"},
        )
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = register.get_json()["token"]
        user_headers = {"Authorization": f"Bearer {token}"}

        generated = client.post(
            "/api/qbank/generate-test3", json={}, headers=user_headers
        )
        self.assertEqual(generated.status_code, 200)
        test_id = generated.get_json()["testSessionId"]

        question_response = client.get(
            f"/api/qbank/test/{test_id}/question/0", headers=user_headers
        )
        self.assertEqual(question_response.status_code, 200)
        question = question_response.get_json()["question"]

        telemetry_response = client.post(
            f"/api/qbank/test/{test_id}/telemetry",
            json={
                "eventType": "image_error",
                "questionId": question["id"],
                "questionIndex": 0,
                "block": 1,
                "payload": {"imageUrl": "/api/images_crop/bad.webp"},
            },
            headers=user_headers,
        )
        self.assertEqual(telemetry_response.status_code, 200)

        with patch.dict(
            os.environ,
            {
                "RENDER_OVERRIDE_ADMIN_TOKEN": "test-render-token",
                "CRON_SECRET": "test-cron-secret",
                "NIDHI_MONITOR_EMAIL": email,
            },
            clear=False,
        ):
            admin_headers = {"X-Render-Admin-Token": "test-render-token"}
            monitor_response = client.get(
                "/api/admin/monitor/nidhi", headers=admin_headers
            )
            self.assertEqual(monitor_response.status_code, 200)
            payload = monitor_response.get_json()
            self.assertTrue(payload["found"])
            self.assertTrue(payload["actionNeeded"])
            self.assertGreaterEqual(len(payload["activeSessions"]), 1)
            self.assertTrue(
                all(session["mode"] == "test3" for session in payload["activeSessions"])
            )
            matching = [
                session
                for session in payload["activeSessions"]
                if session["sessionId"] == test_id
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["issueCount"], 1)
            self.assertEqual(
                matching[0]["latestIssue"]["event_type"],
                "image_error",
            )
            self.assertIsNotNone(payload["latestSession"])
            self.assertEqual(payload["latestSession"]["mode"], "test3")

            cron_headers = {"Authorization": "Bearer test-cron-secret"}
            cron_response = client.get(
                "/api/admin/monitor/nidhi/run", headers=cron_headers
            )
            self.assertEqual(cron_response.status_code, 200)
            self.assertTrue(cron_response.get_json()["ok"])
            self.assertEqual(cron_response.get_json()["monitorIdentity"], "vercel-cron")

    def test_telemetry_rejects_invalid_event_type_and_payload_shape(self):
        client = app.test_client()
        headers = self.auth_headers()
        generated = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        )
        self.assertEqual(generated.status_code, 200)
        test_id = generated.get_json()["testSessionId"]

        bad_event = client.post(
            f"/api/qbank/test/{test_id}/telemetry",
            json={"eventType": "totally_fake_event", "payload": {}},
            headers=headers,
        )
        self.assertEqual(bad_event.status_code, 400)
        self.assertIn("Unsupported telemetry event type", bad_event.get_json()["error"])

        bad_payload = client.post(
            f"/api/qbank/test/{test_id}/telemetry",
            json={"eventType": "heartbeat", "payload": ["not", "an", "object"]},
            headers=headers,
        )
        self.assertEqual(bad_payload.status_code, 400)
        self.assertIn("payload must be an object", bad_payload.get_json()["error"])

        bad_index = client.post(
            f"/api/qbank/test/{test_id}/telemetry",
            json={
                "eventType": "heartbeat",
                "questionIndex": "oops",
                "payload": {},
            },
            headers=headers,
        )
        self.assertEqual(bad_index.status_code, 400)
        self.assertIn("questionIndex must be an integer", bad_index.get_json()["error"])

    def test_render_override_rejects_invalid_fields_and_can_suppress_images(self):
        client = app.test_client()
        headers = self.auth_headers()
        generated = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        )
        self.assertEqual(generated.status_code, 200)
        test_id = generated.get_json()["testSessionId"]
        question = client.get(f"/api/qbank/test/{test_id}/question/0", headers=headers)
        self.assertEqual(question.status_code, 200)
        question_id = question.get_json()["question"]["id"]

        with patch.dict(
            os.environ,
            {"RENDER_OVERRIDE_ADMIN_TOKEN": "test-render-token"},
            clear=False,
        ):
            admin_headers = {"X-Render-Admin-Token": "test-render-token"}
            invalid_response = client.put(
                f"/api/admin/render-overrides/{question_id}",
                json={"changes": {"bogus": "x"}, "reason": "bad"},
                headers=admin_headers,
            )
            self.assertEqual(invalid_response.status_code, 400)
            self.assertIn(
                "Unsupported override field", invalid_response.get_json()["error"]
            )

            suppress_response = client.put(
                f"/api/admin/render-overrides/{question_id}",
                json={
                    "changes": {
                        "image_url": "/api/images_crop/would-have-been-used.webp",
                        "imageUrls": ["/api/images_crop/would-have-been-used.webp"],
                        "suppressImages": True,
                    },
                    "reason": "Temporary suppression",
                    "active": True,
                },
                headers=admin_headers,
            )
            self.assertEqual(suppress_response.status_code, 200)

            overridden_question = client.get(
                f"/api/qbank/test/{test_id}/question/0", headers=headers
            )
            self.assertEqual(overridden_question.status_code, 200)
            payload = overridden_question.get_json()["question"]
            self.assertEqual(payload["image_url"], "")
            self.assertEqual(payload["imageUrls"], [])
            self.assertEqual(payload["image_assets"], [])
            self.assertEqual(
                payload["rendering_flag"]["reason"], "Temporary suppression"
            )

            delete_response = client.delete(
                f"/api/admin/render-overrides/{question_id}", headers=admin_headers
            )
            self.assertEqual(delete_response.status_code, 200)

    def test_test3_endpoint_uses_frozen_personalized_manifest_and_surfaces_surrogate_metadata(
        self,
    ):
        client = app.test_client()
        headers = self.auth_headers()
        response = client.post("/api/qbank/generate-test3", json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        block_ids = [qid for block in payload["blocks"] for qid in block["questionIds"]]
        self.assertEqual(payload["questionIds"], block_ids)
        self.assertEqual(payload["format"], "test3")
        self.assertEqual(payload["manifestSlug"], "test3_nidhi_v1")
        self.assertEqual(payload["manifestVersion"], 1)
        self.assertEqual(payload["mode"], "surrogate")
        self.assertTrue(payload["strictModeWouldFail"])
        self.assertIn("session24_nbme120_simulation", payload["unresolvedSourceLabels"])
        self.assertEqual(
            payload["selectionBasis"], "personalized_blueprint_reconstruction"
        )
        self.assertEqual(payload["totalQuestions"], 120)
        self.assertEqual(len(payload["blocks"]), 6)
        self.assertEqual(
            [len(block["questionIds"]) for block in payload["blocks"]], [20] * 6
        )
        self.assertEqual(payload["summary"]["totalQuestions"], 120)
        self.assertEqual(payload["summary"]["uniqueQuestions"], 120)

        sid = payload["testSessionId"]
        for idx in [0, 19, 20, 39, 40, 59, 100, 119]:
            question_response = client.get(
                f"/api/qbank/test/{sid}/question/{idx}", headers=headers
            )
            self.assertEqual(question_response.status_code, 200)
            question = question_response.get_json()["question"]
            self.assertEqual(question["id"], payload["questionIds"][idx])

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertEqual(state_payload["questionIds"], payload["questionIds"])
        self.assertEqual(
            [block["questionIds"] for block in state_payload["blocks"]],
            [block["questionIds"] for block in payload["blocks"]],
        )

    def test_nidhi_test3_input_artifacts_exist_and_record_known_uncertainty(self):
        inventory_path = (
            ROOT / "artifacts" / "research" / "nidhi_test3_taken_exam_inventory.json"
        )
        exclusion_path = (
            ROOT / "artifacts" / "research" / "nidhi_test3_exclusion_set.json"
        )
        weakness_path = (
            ROOT / "artifacts" / "research" / "nidhi_test3_weakness_profile.json"
        )

        self.assertTrue(inventory_path.exists())
        self.assertTrue(exclusion_path.exists())
        self.assertTrue(weakness_path.exists())

        inventory = json.loads(inventory_path.read_text())
        exclusion = json.loads(exclusion_path.read_text())
        weakness = json.loads(weakness_path.read_text())

        alias_entry = next(
            item for item in inventory["examSets"] if item["slug"] == "test1"
        )
        session24_entry = next(
            item
            for item in inventory["examSets"]
            if item["slug"] == "session24_nbme120_simulation"
        )
        official_entry = next(
            item for item in inventory["examSets"] if item["slug"] == "nbme120_official"
        )

        self.assertEqual(alias_entry["aliasOf"], "test2")
        self.assertEqual(alias_entry["concreteQuestionIds"], [])
        self.assertEqual(session24_entry["status"], "unresolved_label_only")
        self.assertEqual(official_entry["questionCount"], 119)
        self.assertTrue(exclusion["strictModeWouldFail"])
        self.assertEqual(weakness["sourceSessions"], ["session45:test2"])
        self.assertTrue(weakness["weakQuestionIds"])

    def test_nidhi_test3_manifest_artifacts_exist_and_have_expected_shape(self):
        manifest_path = ROOT / "artifacts" / "manifests" / "test3_nidhi_v1.json"
        coverage_path = (
            ROOT / "artifacts" / "manifests" / "test3_nidhi_v1.coverage_report.json"
        )
        explanations_path = (
            ROOT / "artifacts" / "manifests" / "test3_nidhi_v1.explanations.json"
        )
        eval_json_path = ROOT / "artifacts" / "evals" / "test3_nidhi_v1.json"
        eval_md_path = ROOT / "artifacts" / "evals" / "test3_nidhi_v1.md"
        export_path = ROOT / "artifacts" / "exports" / "test3_exam.json"

        self.assertTrue(manifest_path.exists())
        self.assertTrue(coverage_path.exists())
        self.assertTrue(explanations_path.exists())
        self.assertTrue(eval_json_path.exists())
        self.assertTrue(eval_md_path.exists())
        self.assertTrue(export_path.exists())

        manifest = json.loads(manifest_path.read_text())
        coverage = json.loads(coverage_path.read_text())
        export_payload = json.loads(export_path.read_text())

        self.assertEqual(manifest["exam_slug"], "test3_nidhi_v1")
        self.assertEqual(manifest["block_sizes"], [20, 20, 20, 20, 20, 20])
        self.assertEqual(manifest["total_questions"], 120)
        self.assertEqual(len(manifest["blocks"]), 6)
        self.assertEqual(
            [len(block["questionIds"]) for block in manifest["blocks"]], [20] * 6
        )

        all_ids = [qid for block in manifest["blocks"] for qid in block["questionIds"]]
        self.assertEqual(len(all_ids), 120)
        self.assertEqual(len(set(all_ids)), 120)
        self.assertEqual(coverage["integrity"]["conceptFingerprintFallbackCount"], 0)
        self.assertEqual(coverage["integrity"]["excludedQuestionIdOverlap"], [])

        self.assertEqual(export_payload["exam"]["slug"], "test3")
        self.assertEqual(export_payload["exam"]["manifestSlug"], "test3_nidhi_v1")
        self.assertEqual(export_payload["exam"]["blockSizes"], [20, 20, 20, 20, 20, 20])
        self.assertEqual(export_payload["summary"]["totalQuestions"], 120)

    def test_test2_has_no_suppressed_media_or_taken_form_items(self):
        # After the Plan B parity repair, Test 2 should carry no known-bad media
        # (nothing suppressed) and no items from the already-taken official form.
        from test2_render_flags import TEST2_RENDER_FLAGS

        self.assertEqual(TEST2_RENDER_FLAGS, {})
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post(
            "/api/qbank/generate-test2", json={}, headers=headers
        ).get_json()
        sid = payload["testSessionId"]
        for qid in payload["questionIds"]:
            self.assertFalse(
                str(qid).startswith("nbme120_q"),
                f"Test 2 leaked an official-sample item: {qid}",
            )
        for idx in (1, 21, 41):
            question = client.get(
                f"/api/qbank/test/{sid}/question/{idx}", headers=headers
            ).get_json()["question"]
            self.assertIsNone(question["rendering_flag"])

    def test_nbme120_review_attaches_enhanced_explanation(self):
        from index import get_enhanced_explanation

        enhanced = get_enhanced_explanation("nbme120_q001")
        self.assertIsNotNone(enhanced)
        self.assertTrue(enhanced["sections"])
        kinds = {section["kind"] for section in enhanced["sections"]}
        self.assertIn("clues", kinds)
        # Non-sample questions get no enhanced payload.
        self.assertIsNone(get_enhanced_explanation("form30_page-174"))
        # Labeled-figure answer-letter conflict is surfaced, not silently overridden.
        conflict = get_enhanced_explanation("nbme120_q043")
        self.assertTrue(conflict["answerLetterConflict"])

    def test_openevidence_report_present_for_all_test2_questions(self):
        from index import get_openevidence_report

        report = get_openevidence_report("nbme28_q0121")
        self.assertIsNotNone(report)
        self.assertTrue(report["narrativeHtml"].strip())
        self.assertIn("difficulty", report["metrics"])
        # Unknown qid yields nothing.
        self.assertIsNone(get_openevidence_report("does_not_exist_q999"))

    def test_test2_review_attaches_oe_report_and_performance_badges(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post(
            "/api/qbank/generate-test2", json={}, headers=headers
        ).get_json()
        sid = payload["testSessionId"]
        qids = payload["questionIds"]
        # Answer first three items so the review has graded rows + a badge per row.
        for qid in qids[:3]:
            client.post(
                f"/api/qbank/test/{sid}/submit",
                json={"questionId": qid, "selectedOption": 1, "timeSpent": 30},
                headers=headers,
            )
        review = client.get(f"/api/qbank/test/{sid}/review", headers=headers).get_json()
        rows = review["rows"]
        self.assertEqual(len(rows), 120)
        # Every test2 row carries an OpenEvidence report with metrics.
        with_oe = [r for r in rows if r.get("oeReport")]
        self.assertEqual(len(with_oe), 120)
        self.assertTrue(with_oe[0]["oeReport"]["narrativeHtml"].strip())
        # Graded rows carry a performance badge; ungraded ones do not.
        graded = [r for r in rows if r.get("isCorrect") is not None]
        self.assertTrue(graded and all(r.get("performanceBadge") for r in graded))
        ungraded = [r for r in rows if r.get("isCorrect") is None]
        self.assertTrue(all(r.get("performanceBadge") is None for r in ungraded))
        # Summary exposes celebration + badge aggregates.
        self.assertIn("celebrations", review["summary"])
        self.assertIn("badgeCounts", review["summary"])

    def test_answer_submission_is_persisted_in_test_state(self):
        client = app.test_client()
        headers = self.auth_headers()
        session_payload = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers
        ).get_json()
        sid = session_payload["testSessionId"]
        qid = session_payload["questionIds"][0]

        submit = client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": qid, "selectedOption": 1, "timeSpent": 12},
            headers=headers,
        )
        self.assertEqual(submit.status_code, 200)

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        answers = state_payload["answers"]
        self.assertTrue(state_payload["completed"])
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["question_id"], qid)
        self.assertEqual(answers[0]["selected_option"], 1)

    def test_qbank_submit_accepts_valid_cookie_when_header_token_is_stale(self):
        client = app.test_client()
        import uuid

        email = f"submit-fallback-{uuid.uuid4().hex}@example.com"
        register = client.post(
            "/api/register",
            json={
                "email": email,
                "password": "TestPass123!",
                "name": "Submit Fallback",
            },
        )
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post(
                "/api/auth/login", json={"email": email, "password": "TestPass123!"}
            )
        token = register.get_json()["token"]
        good_headers = {"Authorization": f"Bearer {token}"}

        session_payload = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 1}, headers=good_headers
        ).get_json()
        sid = session_payload["testSessionId"]
        qid = session_payload["questionIds"][0]

        client.set_cookie("token", token)
        stale_headers = {"Authorization": "Bearer stale-token"}
        submit = client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": qid, "selectedOption": 1, "timeSpent": 12},
            headers=stale_headers,
        )
        self.assertEqual(submit.status_code, 200)

    def test_answering_last_question_first_does_not_complete_session(self):
        client = app.test_client()
        headers = self.auth_headers()
        session_payload = client.post(
            "/api/qbank/generate-test", json={"totalQuestions": 2}, headers=headers
        ).get_json()
        sid = session_payload["testSessionId"]
        last_qid = session_payload["questionIds"][-1]

        submit = client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": last_qid, "selectedOption": 1},
            headers=headers,
        )
        self.assertEqual(submit.status_code, 200)

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertFalse(state_payload["completed"])
        self.assertEqual(len(state_payload["answers"]), 1)

    def test_nbme_review_returns_one_row_per_question_after_generation(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post(
            "/api/qbank/generate-nbme120", json={}, headers=headers
        ).get_json()

        review = client.get(
            f"/api/qbank/test/{payload['testSessionId']}/review", headers=headers
        )
        self.assertEqual(review.status_code, 200)
        review_payload = review.get_json()
        self.assertEqual(review_payload["totalQuestions"], 120)
        self.assertEqual(len(review_payload["rows"]), 120)
        self.assertEqual(
            [row["questionId"] for row in review_payload["rows"]],
            payload["questionIds"],
        )
        self.assertEqual(review_payload["rows"][0]["block"], 1)
        self.assertEqual(review_payload["rows"][19]["block"], 1)
        self.assertEqual(review_payload["rows"][20]["block"], 2)
        self.assertIn("correctAnswer", review_payload["rows"][0])
        self.assertIn("explanation", review_payload["rows"][0])
        self.assertIn("summary", review_payload)
        self.assertIn("conversationalHeadline", review_payload["summary"])

    def test_curated_image_endpoint_serves_webp_and_stale_asset_404(self):
        client = app.test_client()
        manifest = json.loads((API_DIR / "image_manifest.json").read_text())
        first_asset = next(asset for assets in manifest.values() for asset in assets)
        response = client.get(first_asset["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/webp")
        self.assertEqual(
            response.headers["Cache-Control"], "public, max-age=31536000, immutable"
        )

        stale_response = client.get(
            "/api/images_crop/__contract_nonexistent_asset__.webp"
        )
        self.assertEqual(stale_response.status_code, 404)

    def test_review_includes_solution_content(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-free120", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]
        # Answer the first item so it is scored.
        q0 = client.get(
            f"/api/qbank/test/{sid}/question/0", headers=headers
        ).get_json()["question"]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=headers,
        )
        review = client.get(f"/api/qbank/test/{sid}/review", headers=headers).get_json()
        rows = review["rows"]
        self.assertEqual(len(rows), 119)
        first = rows[0]
        # The review payload must carry everything needed to render full solutions.
        for key in (
            "text",
            "options",
            "correctAnswer",
            "explanation",
            "selectedOption",
            "timeSpent",
            "explanationSummary",
            "coachingNote",
        ):
            self.assertIn(key, first)
        self.assertTrue(first["text"], "review row is missing question stem text")
        self.assertTrue(
            first["explanation"].strip(), "review row is missing explanation/solution"
        )
        self.assertEqual(first["selectedOption"], 1)
        self.assertIn("summary", review)
        self.assertGreaterEqual(review["summary"]["answered"], 1)
        self.assertIn("strongSystems", review["summary"])

    def test_test2_review_returns_120_rows_with_block_metadata(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-test2", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]
        q0 = client.get(
            f"/api/qbank/test/{sid}/question/0", headers=headers
        ).get_json()["question"]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=headers,
        )
        review = client.get(f"/api/qbank/test/{sid}/review", headers=headers).get_json()
        rows = review["rows"]
        self.assertEqual(len(rows), 120)
        self.assertEqual(rows[0]["block"], 1)
        self.assertEqual(rows[19]["block"], 1)
        self.assertEqual(rows[20]["block"], 2)
        self.assertEqual(rows[119]["block"], 6)
        self.assertEqual(rows[119]["blockQuestion"], 20)

    def test_test3_review_returns_120_rows_with_block_metadata_and_label(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-test3", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]
        q0 = client.get(
            f"/api/qbank/test/{sid}/question/0", headers=headers
        ).get_json()["question"]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=headers,
        )
        review = client.get(f"/api/qbank/test/{sid}/review", headers=headers).get_json()
        rows = review["rows"]
        self.assertEqual(len(rows), 120)
        self.assertEqual(rows[0]["block"], 1)
        self.assertEqual(rows[19]["block"], 1)
        self.assertEqual(rows[20]["block"], 2)
        self.assertEqual(rows[119]["block"], 6)
        self.assertEqual(rows[119]["blockQuestion"], 20)
        self.assertIn("Test 3 review", review["summary"]["conversationalHeadline"])

    def test_history_requires_auth(self):
        client = app.test_client()
        self.assertEqual(client.get("/api/qbank/history").status_code, 401)

    def test_history_only_lists_taken_exams_for_current_user(self):
        client = app.test_client()
        headers = self.auth_headers()

        # A freshly generated session with no answers must NOT appear in history.
        gen = client.post(
            "/api/qbank/generate-free120", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]
        empty = client.get("/api/qbank/history", headers=headers).get_json()
        self.assertNotIn(sid, [s["id"] for s in empty["sessions"]])

        # After answering an item, the session surfaces with scored metadata.
        q0 = client.get(
            f"/api/qbank/test/{sid}/question/0", headers=headers
        ).get_json()["question"]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=headers,
        )
        history = client.get("/api/qbank/history", headers=headers).get_json()
        match = next((s for s in history["sessions"] if s["id"] == sid), None)
        self.assertIsNotNone(match, "answered session should appear in history")
        for key in (
            "id",
            "mode",
            "label",
            "answered",
            "correct",
            "score",
            "completed",
            "createdAt",
        ):
            self.assertIn(key, match)
        self.assertEqual(match["mode"], "free120")
        self.assertEqual(match["label"], "Step 1 Sample Exam")
        self.assertEqual(match["answered"], 1)

        # IDs returned by history must work with the review endpoint.
        review = client.get(f"/api/qbank/test/{match['id']}/review", headers=headers)
        self.assertEqual(review.status_code, 200)

    def test_history_exposes_resume_target_for_incomplete_block_exam(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-test2", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]

        for qid in gen["questionIds"][:40]:
            submit = client.post(
                f"/api/qbank/test/{sid}/submit",
                json={"questionId": qid, "selectedOption": 1, "timeSpent": 5},
                headers=headers,
            )
            self.assertEqual(submit.status_code, 200)

        history = client.get("/api/qbank/history", headers=headers).get_json()
        match = next((s for s in history["sessions"] if s["id"] == sid), None)
        self.assertIsNotNone(match)
        self.assertFalse(match["completed"])
        self.assertEqual(match["mode"], "test2")
        self.assertEqual(match["label"], "Test 2")
        self.assertEqual(match["resumeBlock"], 3)
        self.assertEqual(match["nextQuestionIndex"], 40)
        self.assertIn("block=3", match["resumeUrl"])
        self.assertIn("question=40", match["resumeUrl"])
        self.assertIn("exam=test2", match["resumeUrl"])
        self.assertEqual(match["resumeLabel"], "Resume Block 3")

    def test_test3_history_exposes_resume_target_for_incomplete_block_exam(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-test3", json={}, headers=headers
        ).get_json()
        sid = gen["testSessionId"]

        for qid in gen["questionIds"][:40]:
            submit = client.post(
                f"/api/qbank/test/{sid}/submit",
                json={"questionId": qid, "selectedOption": 1, "timeSpent": 5},
                headers=headers,
            )
            self.assertEqual(submit.status_code, 200)

        history = client.get("/api/qbank/history", headers=headers).get_json()
        match = next((s for s in history["sessions"] if s["id"] == sid), None)
        self.assertIsNotNone(match)
        self.assertFalse(match["completed"])
        self.assertEqual(match["mode"], "test3")
        self.assertEqual(match["label"], "Test 3")
        self.assertEqual(match["resumeBlock"], 3)
        self.assertEqual(match["nextQuestionIndex"], 40)
        self.assertIn("block=3", match["resumeUrl"])
        self.assertIn("question=40", match["resumeUrl"])
        self.assertIn("exam=test3", match["resumeUrl"])
        self.assertEqual(match["resumeLabel"], "Resume Block 3")

    def test_history_is_scoped_to_the_requesting_user(self):
        client = app.test_client()
        owner = self.auth_headers()
        gen = client.post(
            "/api/qbank/generate-free120", json={}, headers=owner
        ).get_json()
        sid = gen["testSessionId"]
        q0 = client.get(f"/api/qbank/test/{sid}/question/0", headers=owner).get_json()[
            "question"
        ]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=owner,
        )
        # A different user must not see the owner's session.
        other = self.auth_headers()
        other_history = client.get("/api/qbank/history", headers=other).get_json()
        self.assertNotIn(sid, [s["id"] for s in other_history["sessions"]])


if __name__ == "__main__":
    unittest.main()
