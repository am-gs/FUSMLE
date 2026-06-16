import json
import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from index import app


class ApiContractTests(unittest.TestCase):
    def auth_headers(self):
        client = app.test_client()
        import uuid
        email = f"contract-{uuid.uuid4().hex}@example.com"
        response = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Contract User"})
        if response.status_code == 409:
            response = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        self.assertIn(response.status_code, (200, 201))
        token = response.get_json()["token"]
        self.assertNotEqual(token, "anon-token")
        return {"Authorization": f"Bearer {token}"}

    def test_auth_register_login_and_session_use_real_user_tokens(self):
        client = app.test_client()
        import uuid
        email = f"auth-{uuid.uuid4().hex}@example.com"
        register = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Auth Contract"})
        self.assertIn(register.status_code, (201, 409))

        login = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        self.assertEqual(login.status_code, 200)
        payload = login.get_json()
        self.assertNotEqual(payload["token"], "anon-token")
        self.assertEqual(payload["user"]["email"], email)

        session = client.get("/api/session", headers={"Authorization": f"Bearer {payload['token']}"})
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.get_json()["user"]["email"], email)

        self.assertEqual(app.test_client().get("/api/session").status_code, 401)

    def test_cookie_session_survives_stale_authorization_header(self):
        client = app.test_client()
        import uuid
        email = f"cookie-fallback-{uuid.uuid4().hex}@example.com"
        register = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Cookie Fallback"})
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        token = register.get_json()["token"]

        client.set_cookie("token", token)
        session = client.get("/api/session", headers={"Authorization": "Bearer stale-token"})
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.get_json()["user"]["email"], email)

    def test_logout_revokes_session_server_side(self):
        client = app.test_client()
        import uuid
        email = f"logout-{uuid.uuid4().hex}@example.com"
        register = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Logout Contract"})
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        token = register.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Session is valid before logout (header + cookie both work).
        self.assertEqual(client.get("/api/session", headers=headers).status_code, 200)

        logout = client.post("/api/logout", headers=headers)
        self.assertEqual(logout.status_code, 200)

        # After logout the same token must be rejected via header and via cookie.
        self.assertEqual(app.test_client().get("/api/session", headers=headers).status_code, 401)
        cookie_client = app.test_client()
        cookie_client.set_cookie("token", token)
        self.assertEqual(cookie_client.get("/api/session").status_code, 401)

    def test_account_profile_and_password_updates(self):
        client = app.test_client()
        import uuid
        email = f"account-{uuid.uuid4().hex}@example.com"
        reg = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Old Name"})
        self.assertIn(reg.status_code, (201, 409))
        if reg.status_code == 409:
            reg = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        token = reg.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Update display name
        upd = client.post("/api/account/profile", json={"name": "New Name"}, headers=headers)
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.get_json()["user"]["name"], "New Name")
        self.assertEqual(client.get("/api/session", headers=headers).get_json()["user"]["name"], "New Name")

        # Empty name rejected; auth required (fresh client has no session cookie)
        self.assertEqual(client.post("/api/account/profile", json={"name": "  "}, headers=headers).status_code, 400)
        self.assertEqual(app.test_client().post("/api/account/profile", json={"name": "x"}).status_code, 401)

        # Wrong current password rejected
        self.assertEqual(
            client.post("/api/account/password", json={"currentPassword": "wrong", "newPassword": "Brandnew123!"}, headers=headers).status_code,
            401,
        )
        # Too-short new password rejected
        self.assertEqual(
            client.post("/api/account/password", json={"currentPassword": "TestPass123!", "newPassword": "short"}, headers=headers).status_code,
            400,
        )
        # Valid change succeeds and the new password works for login; old one fails
        ok = client.post("/api/account/password", json={"currentPassword": "TestPass123!", "newPassword": "Brandnew123!"}, headers=headers)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": "Brandnew123!"}).status_code, 200)
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"}).status_code, 401)

    def test_password_change_revokes_other_sessions_but_keeps_current(self):
        import uuid
        email = f"pwsess-{uuid.uuid4().hex}@example.com"
        reg = app.test_client().post("/api/register", json={"email": email, "password": "TestPass123!", "name": "PW Sess"})
        self.assertIn(reg.status_code, (201, 409))
        token_a = reg.get_json()["token"]
        # Second independent session for the same account.
        login_b = app.test_client().post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        token_b = login_b.get_json()["token"]
        self.assertNotEqual(token_a, token_b)

        # Both sessions valid before the change (use header-only clients to avoid cookie carryover).
        self.assertEqual(app.test_client().get("/api/session", headers={"Authorization": f"Bearer {token_a}"}).status_code, 200)
        self.assertEqual(app.test_client().get("/api/session", headers={"Authorization": f"Bearer {token_b}"}).status_code, 200)

        # Change password using session A.
        change = app.test_client().post(
            "/api/account/password",
            json={"currentPassword": "TestPass123!", "newPassword": "Rotated123!"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(change.status_code, 200)

        # Current session (A) survives; the other session (B) is revoked.
        self.assertEqual(app.test_client().get("/api/session", headers={"Authorization": f"Bearer {token_a}"}).status_code, 200)
        self.assertEqual(app.test_client().get("/api/session", headers={"Authorization": f"Bearer {token_b}"}).status_code, 401)

    def test_post_routes_reject_missing_json_without_500(self):
        client = app.test_client()
        self.assertEqual(client.post("/api/forgot-password").status_code, 400)
        self.assertEqual(client.post("/api/qbank/generate-test").status_code, 401)
        response = client.post("/api/qbank/test/999/submit")
        self.assertEqual(response.status_code, 401)

    def test_submit_requires_question_to_belong_to_session(self):
        client = app.test_client()
        headers = self.auth_headers()
        first = client.post("/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers).get_json()
        second = client.post("/api/qbank/generate-test", json={"totalQuestions": 5}, headers=headers).get_json()
        foreign_question_id = next(qid for qid in second["questionIds"] if qid not in first["questionIds"])
        response = client.post(
            f"/api/qbank/test/{first['testSessionId']}/submit",
            json={"questionId": foreign_question_id, "selectedOption": 1},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Question does not belong to this test session")

    def test_nbme_endpoint_session_order_and_boundary_questions(self):
        client = app.test_client()
        headers = self.auth_headers()
        response = client.post("/api/qbank/generate-nbme120", json={}, headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        block_ids = [qid for block in payload["blocks"] for qid in block["questionIds"]]
        self.assertEqual(payload["questionIds"], block_ids)
        self.assertEqual(len(payload["blocks"]), 6)
        self.assertEqual([len(block["questionIds"]) for block in payload["blocks"]], [20] * 6)

        sid = payload["testSessionId"]
        for idx in [0, 19, 20, 39, 40, 59, 100, 119]:
            question_response = client.get(f"/api/qbank/test/{sid}/question/{idx}", headers=headers)
            self.assertEqual(question_response.status_code, 200)
            question = question_response.get_json()["question"]
            self.assertEqual(question["id"], payload["questionIds"][idx])

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertEqual(state_payload["questionIds"], payload["questionIds"])
        self.assertEqual([block["questionIds"] for block in state_payload["blocks"]], [block["questionIds"] for block in payload["blocks"]])

    def test_answer_submission_is_persisted_in_test_state(self):
        client = app.test_client()
        headers = self.auth_headers()
        session_payload = client.post("/api/qbank/generate-test", json={"totalQuestions": 1}, headers=headers).get_json()
        sid = session_payload["testSessionId"]
        qid = session_payload["questionIds"][0]

        submit = client.post(f"/api/qbank/test/{sid}/submit", json={"questionId": qid, "selectedOption": 1, "timeSpent": 12}, headers=headers)
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
        register = client.post("/api/register", json={"email": email, "password": "TestPass123!", "name": "Submit Fallback"})
        self.assertIn(register.status_code, (201, 409))
        if register.status_code == 409:
            register = client.post("/api/auth/login", json={"email": email, "password": "TestPass123!"})
        token = register.get_json()["token"]
        good_headers = {"Authorization": f"Bearer {token}"}

        session_payload = client.post("/api/qbank/generate-test", json={"totalQuestions": 1}, headers=good_headers).get_json()
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
        session_payload = client.post("/api/qbank/generate-test", json={"totalQuestions": 2}, headers=headers).get_json()
        sid = session_payload["testSessionId"]
        last_qid = session_payload["questionIds"][-1]

        submit = client.post(f"/api/qbank/test/{sid}/submit", json={"questionId": last_qid, "selectedOption": 1}, headers=headers)
        self.assertEqual(submit.status_code, 200)

        state = client.get(f"/api/qbank/test/{sid}/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        state_payload = state.get_json()
        self.assertFalse(state_payload["completed"])
        self.assertEqual(len(state_payload["answers"]), 1)

    def test_nbme_review_returns_one_row_per_question_after_generation(self):
        client = app.test_client()
        headers = self.auth_headers()
        payload = client.post("/api/qbank/generate-nbme120", json={}, headers=headers).get_json()

        review = client.get(f"/api/qbank/test/{payload['testSessionId']}/review", headers=headers)
        self.assertEqual(review.status_code, 200)
        review_payload = review.get_json()
        self.assertEqual(review_payload["totalQuestions"], 120)
        self.assertEqual(len(review_payload["rows"]), 120)
        self.assertEqual([row["questionId"] for row in review_payload["rows"]], payload["questionIds"])
        self.assertEqual(review_payload["rows"][0]["block"], 1)
        self.assertEqual(review_payload["rows"][19]["block"], 1)
        self.assertEqual(review_payload["rows"][20]["block"], 2)
        self.assertIn("correctAnswer", review_payload["rows"][0])
        self.assertIn("explanation", review_payload["rows"][0])

    def test_curated_image_endpoint_serves_webp_and_stale_asset_404(self):
        client = app.test_client()
        manifest = json.loads((API_DIR / "image_manifest.json").read_text())
        first_asset = next(asset for assets in manifest.values() for asset in assets)
        response = client.get(first_asset["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/webp")
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")

        stale_response = client.get("/api/images_crop/__contract_nonexistent_asset__.webp")
        self.assertEqual(stale_response.status_code, 404)

    def test_review_includes_solution_content(self):
        client = app.test_client()
        headers = self.auth_headers()
        gen = client.post("/api/qbank/generate-free120", json={}, headers=headers).get_json()
        sid = gen["testSessionId"]
        # Answer the first item so it is scored.
        q0 = client.get(f"/api/qbank/test/{sid}/question/0", headers=headers).get_json()["question"]
        client.post(f"/api/qbank/test/{sid}/submit", json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5}, headers=headers)
        review = client.get(f"/api/qbank/test/{sid}/review", headers=headers).get_json()
        rows = review["rows"]
        self.assertEqual(len(rows), 119)
        first = rows[0]
        # The review payload must carry everything needed to render full solutions.
        for key in ("text", "options", "correctAnswer", "explanation", "selectedOption"):
            self.assertIn(key, first)
        self.assertTrue(first["text"], "review row is missing question stem text")
        self.assertTrue(first["explanation"].strip(), "review row is missing explanation/solution")
        self.assertEqual(first["selectedOption"], 1)

    def test_history_requires_auth(self):
        client = app.test_client()
        self.assertEqual(client.get("/api/qbank/history").status_code, 401)

    def test_history_only_lists_taken_exams_for_current_user(self):
        client = app.test_client()
        headers = self.auth_headers()

        # A freshly generated session with no answers must NOT appear in history.
        gen = client.post("/api/qbank/generate-free120", json={}, headers=headers).get_json()
        sid = gen["testSessionId"]
        empty = client.get("/api/qbank/history", headers=headers).get_json()
        self.assertNotIn(sid, [s["id"] for s in empty["sessions"]])

        # After answering an item, the session surfaces with scored metadata.
        q0 = client.get(f"/api/qbank/test/{sid}/question/0", headers=headers).get_json()["question"]
        client.post(
            f"/api/qbank/test/{sid}/submit",
            json={"questionId": q0["id"], "selectedOption": 1, "timeSpent": 5},
            headers=headers,
        )
        history = client.get("/api/qbank/history", headers=headers).get_json()
        match = next((s for s in history["sessions"] if s["id"] == sid), None)
        self.assertIsNotNone(match, "answered session should appear in history")
        for key in ("id", "mode", "label", "answered", "correct", "score", "completed", "createdAt"):
            self.assertIn(key, match)
        self.assertEqual(match["mode"], "free120")
        self.assertEqual(match["label"], "Step 1 Sample Exam")
        self.assertEqual(match["answered"], 1)

        # IDs returned by history must work with the review endpoint.
        review = client.get(f"/api/qbank/test/{match['id']}/review", headers=headers)
        self.assertEqual(review.status_code, 200)

    def test_history_is_scoped_to_the_requesting_user(self):
        client = app.test_client()
        owner = self.auth_headers()
        gen = client.post("/api/qbank/generate-free120", json={}, headers=owner).get_json()
        sid = gen["testSessionId"]
        q0 = client.get(f"/api/qbank/test/{sid}/question/0", headers=owner).get_json()["question"]
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
