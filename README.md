# LV-426 Extraction Monitor

A read-only web dashboard and PDF reporting application for the formula-driven
Weyland-Yutani daily extraction workbook.

- Spreadsheet: <https://docs.google.com/spreadsheets/d/1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM/edit>
- Local application: <http://127.0.0.1:5000> (while `app.py` is running)
- Deployment status: **prepared for Render, not publicly deployed**. No Render account access was available in this workspace.

## What it does

- Live-loads the `Data` and `Controls` tabs from the public Google Spreadsheet.
- Supports explicit **Refresh data** with a short server-side cache.
- Calculates mean, sample standard deviation, median, Q1, Q3, and IQR for total output and every active mine.
- Implements four configurable anomaly detectors:
  - IQR rule with adjustable fence multiplier
  - Z-score with adjustable absolute threshold
  - Percentage deviation from a preceding moving average with adjustable window and threshold
  - Two-sided Grubbs' test with adjustable significance
- Clearly separates spikes and drops and reports date, mine, observed value, baseline, deviation, percentage deviation, method, and threshold.
- Provides line, bar, and stacked-mine charts with outlier markers, polynomial trendlines of degree 1-4, legends, tooltips, axes, and date-range presets.
- Produces a multi-page PDF with a cover, summary statistics, configured parameters, charts, anomaly tables, and a separate detailed block for every detection.
- Handles short samples, constant series, insufficient Grubbs sample sizes, and network failures with explicit messages.

## Architecture

```text
Browser (vanilla JS + local Chart.js)
        |
        | /api/dataset, /api/analyze, /api/report
        v
Flask application
  sheets.py    public CSV retrieval, parsing, cache
  analysis.py  statistics and anomaly detection
  report.py    ReportLab + Matplotlib PDF
        |
        v
Google Sheets public CSV endpoints (read-only)
```

The Google Sheet is never written to. No OAuth secrets are required or stored by the application.

## Local run

```bash
cd /home/azizbek/weyland-dashboard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open <http://127.0.0.1:5000>.

The app binds to `0.0.0.0` on `PORT` (local default: `5000`). Render injects `PORT`; do not hard-code a Render port.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SPREADSHEET_ID` | `1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM` | Source workbook |
| `DATA_GID` | `2076345475` | `Data` tab fallback export ID |
| `CONTROLS_GID` | `706373598` | `Controls` tab fallback export ID |
| `CACHE_TTL_SECONDS` | `45` | Server cache lifetime |
| `MPLCONFIGDIR` | unset locally; `/tmp/mplconfig` on Render | Matplotlib cache directory; keeps Render's ephemeral filesystem writable |
| `PORT` | `5000` | Local port; Render injects its own value (default `10000`) |

## Data retrieval

The backend first requests Google's public `export?format=csv&gid=...` endpoint
for the `Data` tab and `Controls` tab, then falls back to the public `gviz` CSV
endpoint. Mine names, active flags, capacities, scenario settings, and event
metadata are read from `Controls`; daily values come from `Data`.

The sheet must remain accessible to anyone with the link. If it is made private,
the dashboard will show a data-source error and preserve the last in-memory
snapshot until the process restarts.

## Anomaly method notes

- **IQR:** baseline is the median; flags values outside
  `Q1 - k*IQR` and `Q3 + k*IQR`. Requires at least four observations and a
  non-zero IQR.
- **Z-score:** baseline is the range mean; requires at least three observations
  and non-zero sample standard deviation.
- **Moving average:** baseline uses the preceding `window` days, excluding the
  current day. A warm-up period is required. Default window is 7 days and default
  threshold is 50%.
- **Grubbs:** reports at most one extreme observation per series, using a
  two-sided test at the selected alpha. Requires at least three observations and
  non-zero sample standard deviation.

All detections are statistical screening signals, not proof of an operational event.

## Tests

```bash
.venv/bin/pytest -q
```

Coverage includes descriptive statistics, each detection method, small samples,
constant series, range slicing, method clamping, polynomial fitting, API routes,
sheet parsing, and PDF generation.

The suite contains 23 tests. Browser verification was performed with Playwright
and headless Chromium. The app had no JavaScript console errors during load,
refresh, chart changes, date changes, method changes, PDF download, or a
simulated network failure.

## PDF report

The endpoint `POST /api/report` accepts:

```json
{
  "start": "2027-10-03",
  "end": "2027-12-31",
  "series_id": "total",
  "chart_type": "line",
  "trend_degree": 1,
  "methods": {
    "iqr": {"enabled": true, "multiplier": 1.5},
    "zscore": {"enabled": true, "threshold": 3.0},
    "moving": {"enabled": true, "window": 7, "threshold_pct": 50},
    "grubbs": {"enabled": true, "alpha": 0.05}
  }
}
```

It returns an A4 PDF attachment. Charts are rendered server-side so report layout
does not depend on a browser print dialog.

## Deployment

The application is ready for Render but **has not been deployed publicly** from
this workspace. Render requires a Git repository and access to your Render
account, neither of which is available here. No passwords, API keys, or access
tokens are needed for this app.

### Render prerequisites

- A GitHub, GitLab, or Bitbucket account connected to Render.
- This project committed to a repository Render can read.
- The Google Sheet must remain accessible to **anyone with the link**. The app
  reads it through Google's public CSV export and never writes to it.

Push the project to Git from this directory:

```bash
cd /home/azizbek/weyland-dashboard
git init
git add .
git commit -m "Prepare Render deployment"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repo>.git
git push -u origin main
```

`.gitignore` keeps `.venv`, caches, and generated PDFs out of the repository.
Do not add `.env` files or credentials.

### Option A: Deploy with the included Blueprint (recommended)

1. Sign in to <https://dashboard.render.com>.
2. Choose **New > Blueprint**.
3. Connect your Git provider and select the repository you just pushed.
4. Render detects `render.yaml` at the repository root. Confirm the service
   `weyland-extraction-dashboard`.
5. Click **Apply** / **Create**. Render runs the build and creates the service.
6. Wait for the deploy status to become **Live**.
7. Open the service page and copy the public URL shown there. It is normally
   `https://weyland-extraction-dashboard.onrender.com`, but Render appends a
   suffix if that name is already taken.

The Blueprint sets:

- Runtime: native Python `3.12.3` (also pinned in `.python-version`)
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`
- Health check: `/healthz`
- Plan: free
- Environment: `SPREADSHEET_ID`, `CACHE_TTL_SECONDS=45`,
  `MPLCONFIGDIR=/tmp/mplconfig`, `PYTHONUNBUFFERED=1`
- Automatic deploys: off (`autoDeployTrigger: 'off'`)

No secret environment variables are required.

### Option B: Create the Web Service manually

Use this if you prefer not to use the Blueprint.

1. In Render, choose **New > Web Service** and connect the repository.
2. Set:
   - **Name:** `weyland-extraction-dashboard` (or any available name)
   - **Region:** e.g. Oregon
   - **Branch:** `main`
   - **Language / Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`
   - **Plan:** Free
3. Under **Advanced**, set **Health Check Path** to `/healthz` and add:
   - `PYTHON_VERSION=3.12.3`
   - `SPREADSHEET_ID=1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM`
   - `CACHE_TTL_SECONDS=45`
   - `MPLCONFIGDIR=/tmp/mplconfig`
   - `PYTHONUNBUFFERED=1`
4. Click **Create Web Service** and wait for **Live**.
5. Copy the generated `onrender.com` URL from the service page.

Do **not** set `PORT` manually. Render supplies it, and the start command binds
the app to `0.0.0.0:$PORT`.

### Verify the public deployment

Copy the full URL shown on the Render service page (for example,
`https://weyland-extraction-dashboard.onrender.com`) and set it here:

```bash
export PUBLIC_URL='https://YOUR-SERVICE.onrender.com'
curl -fsS "$PUBLIC_URL/healthz"
curl -fsS "$PUBLIC_URL/api/dataset?refresh=1" > /tmp/dataset.json
python3 - <<'PY'
import json
payload = json.load(open("/tmp/dataset.json"))
data = payload["data"]
print(payload["ok"], data["row_count"], data["dates"][0], data["dates"][-1])
PY
```

Expected health response:

```json
{"ok":true,"service":"weyland-extraction-dashboard"}
```

Then open `$PUBLIC_URL` in a browser, confirm the KPIs load, click **Refresh
data**, and generate one PDF report. The first request after Render's free-tier
idle period can take longer while the instance starts.

### Render troubleshooting

- **Health check fails / 502:** confirm the start command is exactly the one
  above and that it binds to `0.0.0.0:$PORT`. Check the Render logs for Python
  import or memory errors.
- **Build fails:** confirm Python `3.12.3` and that `requirements.txt` was
  committed. `requirements-dev.txt` is not installed in production.
- **Workbook unavailable:** confirm the Google Sheet is still shared as
  **Anyone with the link**. Private sheets require credentials, which this app
  does not use.
- **PDF is slow or fails:** use a shorter range, or upgrade from the free
  512 MB plan. The free plan also spins down after inactivity.
- **Public URL is not live yet:** the URL exists only after Render completes a
  successful deploy. A URL copied before the deploy is finished will not work.

### Docker alternative

The included Docker image is optional. It is not required for Render's native
Python runtime:

```bash
docker build -t weyland-dashboard .
docker run --rm -p 8000:8000 \
  -e SPREADSHEET_ID=1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM \
  weyland-dashboard
```

Open <http://127.0.0.1:8000> for the local container.

### Deployment verification performed here

- `pytest -q`: **23 passed**.
- `pip check`: no broken requirements.
- `render.yaml` validates against Render's published JSON schema.
- The exact production start command was run locally with `PORT=10000`:
  `/healthz` returned 200, the API loaded 730 rows, and a 15-page PDF was
  produced.
- A container capped at 512 MB (matching Render's free plan) loaded the dataset
  and produced both a 15-page report and a 53-page all-data report at roughly
  224-230 MB peak memory.
- No application code or frontend asset contains a hard-coded `localhost` URL;
  the browser uses relative `/api/...` paths.

## Known limitations

- Only active mine series (or mines with non-zero data) are analyzed; inactive
  zero-output mines are omitted from statistics and charts.
- Grubbs' test is a single-outlier test per series.
- The moving-average method uses preceding days only and is sensitive to the
  selected threshold; the default 50% avoids flagging ordinary noise.
- The dashboard is read-only. Refreshing after changing generator settings does
  not modify the sheet.
- PDF reports for multi-year ranges can be long because every method-specific
  detection receives a detailed block.
- The app depends on the public Google Sheets CSV endpoint; availability and
  rate limits are controlled by Google.
- The deployment files were verified locally, but no public Render deployment
  was performed in this environment; the public URL must be created by you.

## Demo

See [DEMO.md](DEMO.md) for a concise, no-narration demonstration sequence.
