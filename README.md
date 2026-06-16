# FUSMLE Deployment

Clean deployment snapshot for the live FUSMLE app.

## Contents

- `vercel/uworld-frontend/` — static frontend currently deployed at `usmaili.vercel.app`
- `vercel/uworld-api-deploy/` — Flask/Vercel backend API used by the frontend
- `vercel/uworld-api-deploy/gold_runtime.json` — runtime QBank data loaded by the backend
- `vercel/uworld-api-deploy/images_crop/` and `images_pages/` — runtime image assets used by the QBank

This repo intentionally excludes curation workspaces, source PDFs/OCR dumps, calibration artifacts, and agent/docs folders.

## TEST 1

Create Test → **TEST 1** launches the official April 2026 Step 1 sample in timed mode:

- 119 official items
- 6 blocks: 20/20/20/20/20/19
- 30 minutes per block
- Structured lab/vitals tables and matching-grid options
- Figure images bound to the correct questions
