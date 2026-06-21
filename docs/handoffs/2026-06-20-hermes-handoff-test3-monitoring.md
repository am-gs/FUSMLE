# Hermes Handoff — Nidhi Test 3 Live Ops

## Mission Context

This repository is governed by `FUSMLE/AGENTS.md`.
Primary operating rule for this workstream: preserve deterministic named-exam behavior and prefer the smallest correct change.

Current priority is **Nidhi’s live `test3` experience** on production:
- disable all old Test 2 audit messaging
- monitor **only** Nidhi’s active `test3` session
- keep rapid-response seams available for render/image fixes
- preserve stable exam ordering and resume behavior

## Production State As Of 2026-06-20

### Frontend
Production app:
- `https://usmaili.vercel.app`

Live frontend status:
- old Test 2 audit popup is disabled globally
- old hardcoded `System Correction` / apology popup is removed from `qbank.html`
- Nidhi-only Test 3 encouragement messages are live in `qbank.html`

Relevant files:
- `vercel/uworld-frontend/assets/js/audit-notice.js`
- `vercel/uworld-frontend/qbank.html`
- `vercel/uworld-frontend/history.html`
- `vercel/uworld-frontend/createtest.html`

### Backend
Production API:
- `https://uworld-api-deploy.vercel.app`

Live backend status:
- monitor endpoints exist
- monitor scope is narrowed to Nidhi + `test3`
- render-override / telemetry seams are present for intervention workflows

Relevant files:
- `vercel/uworld-api-deploy/index.py`
- `vercel/uworld-api-deploy/tests/test_api_contract.py`
- `vercel/uworld-api-deploy/render_overrides.py`

## Verified Live Behavior

Confirmed after deployment:
- `https://usmaili.vercel.app/assets/js/audit-notice.js` is a no-op
- `https://usmaili.vercel.app/qbank.html` contains:
  - `encouragementPopup`
  - `TEST3_QUOTES`
  - `maybeShowTest3Encouragement`
- `https://usmaili.vercel.app/qbank.html` does **not** contain:
  - `System Correction`
  - `checkNidhiApology`

Live monitor snapshot verified:
- only one active monitored session
- mode returned: `test3`
- latest session mode: `test3`
- latest session id observed: `74`

## Monitoring Architecture

### Vercel-side monitor endpoints
Backend routes:
- `GET /api/admin/monitor/nidhi`
- `GET|POST /api/admin/monitor/nidhi/run`

Purpose:
- summarize Nidhi named-exam session health
- surface telemetry issue types:
  - `image_error`
  - `render_anomaly`
  - `submit_error`
  - `client_error`

Important:
- current production monitor should only surface `test3`

### Local real-time watcher
Because Vercel hobby cron does not support per-minute production cron, near-real-time monitoring is handled locally via `launchd`.

Source in repo:
- `scripts/monitor_nidhi_live.py`

Installed runtime paths on this Mac:
- launch agent: `/Users/nirav/Library/LaunchAgents/com.fusmle.nidhi-monitor.plist`
- runtime script: `/Users/nirav/Library/Application Support/FUSMLE/monitor_nidhi_live.py`
- output dir: `/Users/nirav/Library/Application Support/FUSMLE/monitor`
- stdout log: `/Users/nirav/Library/Logs/fusmle_nidhi_monitor.out.log`
- stderr log: `/Users/nirav/Library/Logs/fusmle_nidhi_monitor.err.log`

Behavior:
- runs every 60 seconds
- alert logic is restricted to `test3`
- `launchctl` previously showed healthy repeated runs with `last exit code = 0`

## Key Secrets / Auth Inputs

These are operationally relevant for Hermes if it needs to inspect live monitor state.

### CRON_SECRET
Used for authenticated access to `/api/admin/monitor/nidhi/run`:
- stored in Vercel production
- also used by local watcher

Hermes should **not** print or duplicate secrets into repo files.
If needed, fetch from the existing environment or operator.

### Vercel Projects
- frontend project: `usmaili`
- backend project: `uworld-api-deploy`

## Test 3 Artifacts Relevant To Nidhi

Primary artifacts already present in repo:
- `artifacts/manifests/test3_nidhi_v1.json`
- `artifacts/manifests/test3_nidhi_v1.coverage_report.json`
- `artifacts/manifests/test3_nidhi_v1.explanations.json`
- `artifacts/evals/test3_nidhi_v1.json`
- `artifacts/evals/test3_nidhi_v1.md`
- `artifacts/research/nidhi_test3_decision-log.jsonl`
- `artifacts/research/nidhi_test3_exclusion_set.json`
- `artifacts/research/nidhi_test3_taken_exam_inventory.json`
- `artifacts/research/nidhi_test3_weakness_profile.json`
- `artifacts/exports/test3_exam.json`

Planning docs:
- `docs/superpowers/plans/2026-06-19-full-exam-nbme-rescore.md`
- `docs/superpowers/plans/2026-06-20-test3-nidhi-personalized-manifest.md`

## Files Hermes Should Treat As The Current Seams

### Live UX seam
- `vercel/uworld-frontend/qbank.html`

Use for:
- exam-session messaging
- inline render/recovery UX
- Nidhi-only `test3` encouragement behavior

### Global audit-notice seam
- `vercel/uworld-frontend/assets/js/audit-notice.js`

Use for:
- global toast/popup suppression or future reinstatement

### Live monitor seam
- `vercel/uworld-api-deploy/index.py`

Use for:
- `test3`-only monitor filtering
- admin/cron monitor responses
- telemetry-backed issue detection

### Intervention seam
- `vercel/uworld-api-deploy/render_overrides.py`
- relevant routes in `vercel/uworld-api-deploy/index.py`

Use for:
- rapid server-side render overrides for broken question presentation

## What Was Verified Before Handoff

### Tests run
Targeted backend contract tests passed:
- `vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_requires_admin_or_cron_auth`
- `vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_reports_active_named_exam_issues`

### Deployments completed
Executed production deploys for:
- `vercel/uworld-api-deploy`
- `vercel/uworld-frontend`

### Live source checks completed
Verified live source for:
- disabled audit notice JS
- removal of old Test 2 correction copy
- presence of Nidhi Test 3 encouragement code
- monitor narrowing to `test3`

## Open Cautions

1. There is unrelated repo noise in `git status`.
   Hermes should avoid broad staging or accidental deploys from unrelated changes.

2. The monitor contract test originally failed because it assumed exactly one active session.
   That assumption was brittle in a shared DB. The test now verifies the correct contract instead.

3. Vercel hobby cron is not suitable for per-minute monitoring.
   Do not rely on Vercel cron for sub-daily real-time monitoring unless the plan changes.

4. Browser cache may temporarily show stale frontend behavior.
   If someone still sees the old Test 2 notice, first suspect cached JS and hard-refresh.

## Recommended Next Actions For Hermes

Priority order:

1. **Do not touch Test 1 / Test 2 flows** unless explicitly asked.
2. Validate current `test3` session UX end-to-end for Nidhi only.
3. If a live rendering issue occurs, prefer the smallest production-safe fix:
   - inspect telemetry / monitor snapshot
   - patch via existing render-override seam if possible
   - only modify frontend rendering if the issue is systemic
4. Keep all interventions deterministic and diffable.
5. Record any future Nidhi-specific decisions in:
   - `artifacts/research/`
   - `artifacts/evals/`

## Useful Commands For Hermes

### Check backend monitor live
```bash
python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    'https://uworld-api-deploy.vercel.app/api/admin/monitor/nidhi/run',
    headers={'Authorization': 'Bearer <CRON_SECRET>'}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    payload = json.loads(resp.read().decode('utf-8'))
print(json.dumps({
    'ok': payload.get('ok'),
    'activeModes': sorted({s.get('mode') for s in (payload.get('activeSessions') or [])}),
    'latestMode': (payload.get('latestSession') or {}).get('mode'),
    'latestSessionId': (payload.get('latestSession') or {}).get('sessionId'),
    'actionNeeded': payload.get('actionNeeded'),
}, indent=2))
PY
```

### Check local watcher status
```bash
launchctl print gui/$(id -u)/com.fusmle.nidhi-monitor
```

### Run targeted backend tests
```bash
./.venv-test3/bin/python -m unittest \
  vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_requires_admin_or_cron_auth \
  vercel.uworld-api-deploy.tests.test_api_contract.ApiContractTests.test_nidhi_monitor_reports_active_named_exam_issues
```

### Deploy frontend
```bash
vercel deploy --prod --yes --cwd vercel/uworld-frontend
```

### Deploy backend
```bash
vercel deploy --prod --yes --cwd vercel/uworld-api-deploy
```

## Handoff Summary

If Hermes needs a single sentence:

> Production is already fixed so the old Test 2 audit notice is gone, Nidhi-only encouragement is live in `test3`, and monitoring is narrowed to Nidhi’s active `test3` session with a local per-minute watcher ready for intervention.
