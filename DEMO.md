# No-Narration Demo Plan

## Setup

- Dashboard: <http://127.0.0.1:5000> locally, or your deployed Render URL.
- Generator: <https://docs.google.com/spreadsheets/d/1kKnoVzwH-ua29vyfNwk0OcqYyPDkRXe03sSHLRNgPGM/edit>
- Use a desktop browser at 1440-1600 px wide.
- Close other tabs and notification popups.

## Sequence

1. **Open the generator**
   - Open the spreadsheet.
   - Select the `Controls` tab.
   - Change `Random seed` from `20261027` to `20261028`.
   - Change `Xenomorph infestation` probability from `100%` to `40%`.
   - Wait for formulas to finish recalculating.

2. **Refresh the dashboard**
   - Switch to the dashboard.
   - Click **Refresh data**.
   - Wait for the snapshot time and all KPI values to update.
   - Point at the **Workbook connected** indicator.

3. **Review statistics**
   - Click **90D**.
   - Scroll to **Summary statistics**.
   - Point to the total row and two mine rows.
   - Move the pointer across Mean, Std dev, Median, and IQR.

4. **Review anomalies**
   - Scroll to **Detected anomalies**.
   - Change **Method** to `IQR rule`; pause.
   - Change **Method** back to `All methods`.
   - Change **Direction** to `Spikes only`; pause.
   - Restore `Spikes and drops`.

5. **Change chart**
   - Scroll to the chart.
   - Select a mine such as `Fury-161`.
   - Change **Chart** from `Line` to `Bar`; pause.
   - Change **Chart** to `Stacked mines`; pause.
   - Change **Trend** from `Linear (1)` to `Cubic (3)`.
   - Toggle **Outliers** off and back on.
   - Hover a red spike marker and hold the tooltip open.

6. **Change detection parameters**
   - Set **IQR fence multiplier** to `1.2`.
   - Set **Moving average** window to `14` and threshold to `40`.
   - Click **Re-run detection**.
   - Pause on the updated detection count and table.

7. **Generate PDF**
   - Click **Generate PDF report**.
   - Wait for the download.
   - Open the PDF.
   - Show the cover and selected range.
   - Scroll to **Summary statistics**.
   - Scroll to **Outlier charts**; pause on a chart with markers and trendline.
   - Scroll to **Detected anomalies**.
   - Scroll to **Detailed anomaly review**; pause on one spike and one drop.
   - Return to the dashboard.

8. **Restore the generator**
   - Return to the `Controls` tab.
   - Restore `Random seed` to `20261027`.
   - Restore `Xenomorph infestation` probability to `100%`.
   - Wait for recalculation before leaving the sheet.

## Checkpoints

- Refresh updates the snapshot timestamp.
- KPI cards and statistics change with the selected range.
- Spike markers are red upward triangles; drops are blue downward triangles.
- The PDF filename includes the selected start and end dates.
- The PDF page count and content correspond to the active date range and method settings.

## Recovery

If the dashboard shows a workbook error, click **Retry**. If the public CSV
endpoint is temporarily unavailable, the app may show the last in-memory snapshot
with a cached-snapshot warning. Restart `app.py` only if no snapshot is available.
