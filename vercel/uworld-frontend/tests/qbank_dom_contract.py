import pathlib
import unittest

FRONTEND_DIR = pathlib.Path(__file__).resolve().parents[1]
QBANK_HTML = (FRONTEND_DIR / "qbank.html").read_text()
CREATETEST_HTML = (FRONTEND_DIR / "createtest.html").read_text()
INDEX_HTML = (FRONTEND_DIR / "index.html").read_text()
DASHBOARD_HTML = (FRONTEND_DIR / "dashboard.html").read_text()
PERFORMANCE_HTML = (FRONTEND_DIR / "performance.html").read_text()
SETTINGS_HTML = (FRONTEND_DIR / "settings.html").read_text()


class QbankDomContractTests(unittest.TestCase):
    def test_visible_branding_is_fuusmle(self):
        branded_pages = [
            INDEX_HTML,
            DASHBOARD_HTML,
            CREATETEST_HTML,
            QBANK_HTML,
            PERFORMANCE_HTML,
            SETTINGS_HTML,
        ]
        for html in branded_pages:
            self.assertIn("FUuSMLE", html)
        for html in branded_pages:
            self.assertNotIn("UWorld Clone", html)
            self.assertNotIn("UWorld Login", html)
            self.assertNotIn("UWorld Logo", html)
            self.assertNotIn("text=UWorld", html)
            self.assertNotIn(">UWorld<", html)
            self.assertNotIn('alt="U"', html)

    def test_frontend_uses_persisted_auth_token_not_anon_token(self):
        self.assertIn("function getAuthToken()", CREATETEST_HTML)
        self.assertIn("localStorage.getItem('uworldToken')", CREATETEST_HTML)
        self.assertIn("Authorization': 'Bearer '+getAuthToken()", CREATETEST_HTML)
        self.assertNotIn("Bearer anon-token", CREATETEST_HTML)

        self.assertIn("function getAuthToken()", QBANK_HTML)
        self.assertIn("Authorization': 'Bearer '+getAuthToken()", QBANK_HTML)
        self.assertNotIn("Bearer anon-token", QBANK_HTML)

        # Dashboard and Performance previously used a hardcoded anon-token and
        # ignored the logged-in user; they must now use the persisted token.
        for html in (DASHBOARD_HTML, PERFORMANCE_HTML):
            self.assertNotIn("Bearer anon-token", html)
            self.assertIn("function getAuthToken()", html)
            self.assertIn("localStorage.getItem('uworldToken')", html)
            self.assertIn("getAuthToken()", html)

    def test_removed_dead_features_are_gone(self):
        # Flashcards and Notes were non-functional stubs and have been removed.
        self.assertFalse((FRONTEND_DIR / "flashcards.html").exists())
        self.assertFalse((FRONTEND_DIR / "notes.html").exists())
        for html in (DASHBOARD_HTML, CREATETEST_HTML, PERFORMANCE_HTML):
            self.assertNotIn("flashcards.html", html)
            self.assertNotIn("notes.html", html)
            self.assertNotIn("/flashcards", html)
            self.assertNotIn("/notes", html)

    def test_logout_clears_persisted_session(self):
        # Logout must clear the token and redirect, not merely reload the page,
        # and must revoke the server-side session via /api/logout.
        for html in (DASHBOARD_HTML, PERFORMANCE_HTML, CREATETEST_HTML):
            self.assertIn("removeItem('uworldToken')", html)
            self.assertIn("index.html", html)
            self.assertIn("/api/logout", html)

    def test_stats_pages_handle_expired_session(self):
        # A 401 from the stats endpoint must force re-authentication, not render stale state.
        for html in (DASHBOARD_HTML, PERFORMANCE_HTML):
            self.assertIn("401", html)
            self.assertIn("handleExpiredSession", html)

    def test_settings_page_account_basics(self):
        # Settings page exists with profile (name) and password forms wired to the account API.
        self.assertIn('id="profileForm"', SETTINGS_HTML)
        self.assertIn('id="passwordForm"', SETTINGS_HTML)
        self.assertIn("/api/account/profile", SETTINGS_HTML)
        self.assertIn("/api/account/password", SETTINGS_HTML)
        self.assertIn("function getAuthToken()", SETTINGS_HTML)
        self.assertNotIn("Bearer anon-token", SETTINGS_HTML)
        self.assertIn("/api/logout", SETTINGS_HTML)
        # Settings is reachable from the main navigation.
        for html in (DASHBOARD_HTML, CREATETEST_HTML, PERFORMANCE_HTML):
            self.assertIn("settings", html.lower())

    def test_index_has_login_and_register_flow(self):
        index_html = INDEX_HTML
        self.assertIn('id="loginForm"', index_html)
        self.assertIn('id="registerForm"', index_html)
        self.assertIn("/api/auth/login", index_html)
        self.assertIn("/api/register", index_html)
        self.assertIn("localStorage.setItem('uworldToken'", index_html)
        self.assertNotIn("x-vercel-protection-bypass", index_html)
        self.assertNotIn("aiQnOHn", index_html)

    def test_qbank_score_counter_updates_are_null_safe(self):
        self.assertIn("function updateScoreCounters()", QBANK_HTML)
        self.assertIn("if(correctEl)correctEl.textContent=cc;", QBANK_HTML)
        self.assertIn("if(wrongEl)wrongEl.textContent=wc;", QBANK_HTML)
        self.assertNotIn("document.getElementById('correctCount').textContent=cc", QBANK_HTML)
        self.assertNotIn("document.getElementById('wrongCount').textContent=wc", QBANK_HTML)

    def test_qbank_renders_all_image_urls(self):
        self.assertIn("var imageUrls=(q.imageUrls&&q.imageUrls.length?q.imageUrls:(q.image_url?[q.image_url]:[]));", QBANK_HTML)
        self.assertIn("imageUrls.map", QBANK_HTML)

    def test_qbank_renders_structured_nbme_tables(self):
        self.assertIn("function renderQuestionText(q)", QBANK_HTML)
        self.assertIn("function renderTable(t)", QBANK_HTML)
        self.assertIn("function renderOptionTable(t)", QBANK_HTML)
        self.assertIn("q.option_table", QBANK_HTML)
        self.assertIn("nbme-option-table", QBANK_HTML)

    def test_create_test_nbme_button_starts_global_function(self):
        self.assertIn('id="generateNBME120Btn"', CREATETEST_HTML)
        self.assertIn('onclick="startNBME120()"', CREATETEST_HTML)
        self.assertIn("window.startNBME120 = function()", CREATETEST_HTML)
        self.assertIn("/api/qbank/generate-nbme120", CREATETEST_HTML)
        self.assertIn("block=1&mode=timed&time=30", CREATETEST_HTML)

    def test_create_test_free120_button_starts_global_function(self):
        self.assertIn('id="generateFree120Btn"', CREATETEST_HTML)
        self.assertIn('onclick="startFree120()"', CREATETEST_HTML)
        self.assertIn("window.startFree120 = function()", CREATETEST_HTML)
        self.assertIn("/api/qbank/generate-free120", CREATETEST_HTML)
        self.assertIn("Step 1 Sample Exam", CREATETEST_HTML)
        self.assertIn("exam=free120", CREATETEST_HTML)

    def test_nbme_final_results_fetch_full_120_row_review(self):
        self.assertIn("async function showExamReview()", QBANK_HTML)
        self.assertIn("/api/qbank/test/'+ts+'/review", QBANK_HTML)
        self.assertIn("reviewRows.length", QBANK_HTML)
        self.assertIn("NBME 120 Review", QBANK_HTML)
        self.assertIn("Sample Exam Review", QBANK_HTML)
        self.assertIn("function isCorrectValue(value)", QBANK_HTML)

    def test_exam_review_renders_per_item_solutions(self):
        # End-of-exam review must show each item's correct answer and explanation, not just a score table.
        self.assertIn("function renderSolutionCard(row,i)", QBANK_HTML)
        self.assertIn("renderSolutionCard(row,i)", QBANK_HTML)
        self.assertIn("rev-exp", QBANK_HTML)
        self.assertIn(">Explanation<", QBANK_HTML)
        self.assertIn("row.explanation", QBANK_HTML)
        self.assertIn("Correct answer", QBANK_HTML)
        self.assertIn("Your answer", QBANK_HTML)

    def test_qbank_uses_nbme_fred_portal_chrome(self):
        # Test portal must present the NBME FRED-style interface and drop Free/2021 wording.
        self.assertIn("fred-top", QBANK_HTML)
        self.assertIn("fred-bottom", QBANK_HTML)
        self.assertIn("Lab Values", QBANK_HTML)
        self.assertIn("End Block", QBANK_HTML)
        self.assertIn("Block Time Remaining", QBANK_HTML)
        self.assertNotIn("Free 120", QBANK_HTML)
        self.assertNotIn("2021", QBANK_HTML)
        for html in (CREATETEST_HTML, DASHBOARD_HTML):
            self.assertNotIn("2021", html)
            self.assertNotIn("Free 120 Practice Exam", html)

    def test_suspend_pauses_block_instead_of_ending(self):
        # Suspend must pause/resume without scoring; only End Block ends the block.
        self.assertIn('onclick="suspendBlock()"', QBANK_HTML)
        self.assertIn("function suspendBlock()", QBANK_HTML)
        self.assertIn("function resumeBlock()", QBANK_HTML)
        self.assertIn("function startTimer()", QBANK_HTML)
        self.assertIn("suspendOverlay", QBANK_HTML)
        # The Suspend button must NOT be wired to endSession (that's End Block only).
        self.assertNotIn('onclick="endSession()"><i class="fas fa-pause"></i> Suspend', QBANK_HTML)
        # Paused break time must be excluded from per-item time, and resume must not
        # restart the timer after the block is complete.
        self.assertIn("suspendStart=Date.now()", QBANK_HTML)
        self.assertIn("st+=(Date.now()-suspendStart)", QBANK_HTML)
        self.assertIn("completeState').style.display==='none'", QBANK_HTML)

    def test_history_page_lists_prior_exams_and_links_to_review(self):
        # The History/Results page must exist, use the persisted token, hit the
        # history API, and link each prior exam into direct review mode.
        history_html = (FRONTEND_DIR / "history.html").read_text()
        self.assertIn("function getAuthToken()", history_html)
        self.assertNotIn("Bearer anon-token", history_html)
        self.assertIn("/api/qbank/history", history_html)
        self.assertIn("handleExpiredSession", history_html)
        self.assertIn("401", history_html)
        # Each row deep-links into the existing review viewer.
        self.assertIn("qbank.html?session=", history_html)
        self.assertIn("&review=1", history_html)
        # Reachable from the main navigation.
        for html in (DASHBOARD_HTML, CREATETEST_HTML, PERFORMANCE_HTML, SETTINGS_HTML):
            self.assertIn("history", html.lower())

    def test_history_route_is_registered(self):
        vercel_json = (FRONTEND_DIR / "vercel.json").read_text()
        self.assertIn('"/history"', vercel_json)
        self.assertIn("/history.html", vercel_json)

    def test_qbank_supports_direct_review_mode_for_past_exams(self):
        # review=1 must short-circuit init into the solutions view without
        # starting the timer/block flow.
        self.assertIn("p.get('review')==='1'", QBANK_HTML)
        self.assertIn("enterReviewMode()", QBANK_HTML)
        self.assertIn("function enterReviewMode()", QBANK_HTML)
        self.assertIn("showExamReview()", QBANK_HTML)


if __name__ == "__main__":
    unittest.main()
