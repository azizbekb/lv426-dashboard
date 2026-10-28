from datetime import date, timedelta

import pytest

import app as app_module


def fixture_dataset(days=40):
    dates = [(date(2027, 1, 1) + timedelta(days=index)).isoformat() for index in range(days)]
    base = [1000 + (index % 7) * 12 for index in range(days)]
    base[12] = 1900
    base[25] = 430
    mine_a = [round(value * 0.55, 1) for value in base]
    mine_b = [round(value * 0.45, 1) for value in base]
    return {
        "dates": dates,
        "total": [float(value) for value in base],
        "mines": [
            {
                "id": "mine-1",
                "number": 1,
                "name": "Alpha Cut",
                "active": True,
                "capacity": 1000.0,
                "values": mine_a,
            },
            {
                "id": "mine-2",
                "number": 2,
                "name": "Beta Cut",
                "active": True,
                "capacity": 800.0,
                "values": mine_b,
            },
        ],
        "controls": {
            "window": {"start": dates[0], "end": dates[-1], "days": days, "active_mines": 2},
            "distribution": {"type": "Normal", "normal_mean": 1.0, "normal_std": 0.18,
                             "uniform_min": 0.7, "uniform_max": 1.3},
            "dynamics": {"annual_trend": 0.03, "seed": 20261027},
            "mines": [{"number": 1, "name": "Alpha Cut", "active": True},
                      {"number": 2, "name": "Beta Cut", "active": True}],
            "events": [{"name": "Test event"}],
            "weekday_factors": {},
        },
        "row_count": days,
        "source": {
            "spreadsheet_id": "test-sheet",
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
            "fetched_at": "2027-02-09T00:00:00+00:00",
            "access": "test fixture",
        },
        "cache": "refresh",
    }


@pytest.fixture
def client(monkeypatch):
    data = fixture_dataset()
    calls = {"count": 0}

    def fake_fetch(force=False):
        calls["count"] += 1
        return data

    monkeypatch.setattr(app_module, "fetch_dataset", fake_fetch)
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as test_client:
        test_client.fake_calls = calls
        yield test_client


def test_health_and_index(client):
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.get_json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200
    assert b"Anomaly methods" in page.data
    assert b"Generate PDF report" in page.data


def test_dataset_route(client):
    response = client.get("/api/dataset?refresh=1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["row_count"] == 40
    assert len(payload["data"]["mines"]) == 2
    assert client.fake_calls["count"] >= 1


def test_analyze_route(client):
    response = client.post(
        "/api/analyze",
        json={
            "start": "2027-01-10",
            "end": "2027-02-05",
            "methods": {
                "iqr": {"enabled": True, "multiplier": 1.5},
                "zscore": {"enabled": True, "threshold": 2.5},
                "moving": {"enabled": True, "window": 7, "threshold_pct": 40},
                "grubbs": {"enabled": True, "alpha": 0.05},
            },
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["analysis"]["date_range"]["days"] == 27
    assert len(payload["analysis"]["stats"]) == 3
    assert payload["analysis"]["summary"]["anomaly_rows"] > 0
    assert payload["data"]["date_bounds"]["start"] == "2027-01-01"


def test_analyze_invalid_range(client):
    response = client.post(
        "/api/analyze",
        json={"start": "2028-01-01", "end": "2028-01-02"},
    )
    assert response.status_code == 422
    assert response.get_json()["ok"] is False


def test_report_route_returns_pdf(client):
    response = client.post(
        "/api/report",
        json={
            "start": "2027-01-01",
            "end": "2027-02-09",
            "trend_degree": 2,
            "series_id": "mine-1",
            "chart_type": "line",
            "methods": {
                "iqr": {"enabled": True, "multiplier": 1.5},
                "zscore": {"enabled": False},
                "moving": {"enabled": True, "window": 7, "threshold_pct": 40},
                "grubbs": {"enabled": True, "alpha": 0.05},
            },
        },
    )
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-")
    assert len(response.data) > 100_000
    assert "attachment" in response.headers["Content-Disposition"]
    assert "weyland-anomaly-report" in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"


def test_report_invalid_body(client):
    response = client.post("/api/report", json={"start": "2027-01-01", "end": "not-a-date"})
    assert response.status_code == 422
