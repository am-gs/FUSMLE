# Hermes Next Actions

1. Read `FUSMLE/AGENTS.md` first.
2. Then read `docs/handoffs/2026-06-20-hermes-handoff-test3-monitoring.md`.
3. Do **not** touch Test 1 or Test 2 unless explicitly asked.
4. Focus only on `nidhitiyyagura@gmail.com` and `test3`.
5. Frontend live UX seam: `vercel/uworld-frontend/qbank.html`.
6. Global popup seam: `vercel/uworld-frontend/assets/js/audit-notice.js`.
7. Backend monitor seam: `vercel/uworld-api-deploy/index.py`.
8. Intervention seam: `vercel/uworld-api-deploy/render_overrides.py`.
9. Check live monitor first before changing code.
10. Prefer the smallest production-safe fix and re-verify live.

## First commands

```bash
launchctl print gui/$(id -u)/com.fusmle.nidhi-monitor
```

```bash
./.venv-test3/bin/python -m unittest \
  vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_requires_admin_or_cron_auth \
  vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_reports_active_named_exam_issues
```

```bash
vercel deploy --prod --yes --cwd vercel/uworld-api-deploy
```

```bash
vercel deploy --prod --yes --cwd vercel/uworld-frontend
```
