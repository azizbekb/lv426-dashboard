"""Flask application for the Weyland-Yutani extraction dashboard."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, send_file

from analysis import analyze
from report import build_pdf
from sheets import SheetError, fetch_dataset

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


@app.after_request
def _headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "weyland-extraction-dashboard"})


@app.get("/api/dataset")
def dataset():
    force = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    try:
        payload = fetch_dataset(force=force)
    except SheetError as exc:
        return _json_error(f"Could not load the spreadsheet: {exc}", 502)
    return jsonify({"ok": True, "data": payload})


def _analysis_from_request(body: dict):
    dataset_force = bool(body.get("refresh"))
    try:
        data = fetch_dataset(force=dataset_force)
    except SheetError as exc:
        raise ValueError(f"Could not load the spreadsheet: {exc}") from exc
    return data, analyze(
        data,
        start=body.get("start"),
        end=body.get("end"),
        methods=body.get("methods"),
    )


@app.post("/api/analyze")
def analyze_route():
    body = request.get_json(silent=True) or {}
    try:
        data, result = _analysis_from_request(body)
    except ValueError as exc:
        return _json_error(str(exc), 422)
    return jsonify(
        {
            "ok": True,
            "data": {
                "source": data["source"],
                "row_count": data["row_count"],
                "date_bounds": {"start": data["dates"][0], "end": data["dates"][-1]},
                "controls": data["controls"],
                "cache": data.get("cache"),
                "warning": data.get("warning"),
            },
            "analysis": result,
        }
    )


@app.post("/api/report")
def report_route():
    body = request.get_json(silent=True) or {}
    try:
        data, result = _analysis_from_request(body)
        chart_type = str(body.get("chart_type", "line")).lower()
        if chart_type not in {"line", "bar", "stacked"}:
            chart_type = "line"
        trend_degree = int(body.get("trend_degree", 1) or 1)
        if trend_degree not in {1, 2, 3, 4}:
            trend_degree = 1
        series_id = str(body.get("series_id", "total"))
        valid_ids = {row["id"] for row in result["stats"]}
        if series_id not in valid_ids:
            series_id = "total"
        pdf = build_pdf(
            data,
            result,
            {
                "chart_type": chart_type,
                "trend_degree": trend_degree,
                "series_id": series_id,
            },
        )
    except ValueError as exc:
        return _json_error(str(exc), 422)
    except Exception as exc:  # pragma: no cover - defensive API boundary
        app.logger.exception("PDF generation failed")
        return _json_error(f"PDF generation failed: {exc}", 500)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"weyland-anomaly-report-{result['date_range']['start']}-to-{result['date_range']['end']}-{stamp}.pdf"
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return _json_error("API route not found", 404)
    return render_template("index.html"), 404


@app.errorhandler(413)
def too_large(_error):
    return _json_error("Request body is too large", 413)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
