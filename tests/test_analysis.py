from datetime import date, timedelta

import numpy as np
import pytest

from analysis import (
    analyze,
    descriptive_stats,
    detect_grubbs,
    detect_iqr,
    detect_moving,
    detect_zscore,
    grubbs_critical,
    normalize_methods,
    polynomial_trend,
    slice_dataset,
)


def make_dataset(values, active=True):
    dates = [
        (date(2026, 1, 1) + timedelta(days=index)).isoformat()
        for index in range(len(values))
    ]
    values = [float(value) for value in values]
    return {
        "dates": dates,
        "total": values,
        "mines": [
            {
                "id": "mine-1",
                "number": 1,
                "name": "Test Mine",
                "active": active,
                "capacity": 1000.0,
                "values": values,
            }
        ],
        "controls": {"mines": [], "events": [], "window": {"active_mines": 1}},
        "row_count": len(values),
        "source": {
            "spreadsheet_id": "test",
            "spreadsheet_url": "https://example.test",
            "fetched_at": "2026-01-01T00:00:00+00:00",
        },
    }


def series(values):
    return {
        "id": "total",
        "label": "Total output",
        "type": "total",
        "mine_number": None,
        "active": True,
        "values": [float(value) for value in values],
    }


def test_descriptive_statistics():
    result = descriptive_stats([1, 2, 3, 4, 5])
    assert result["n"] == 5
    assert result["mean"] == 3
    assert result["median"] == 3
    assert result["q1"] == 2
    assert result["q3"] == 4
    assert result["iqr"] == 2
    assert result["std"] == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=1))


def test_descriptive_statistics_small_samples():
    assert descriptive_stats([])["mean"] is None
    assert descriptive_stats([5])["std"] == 0
    assert descriptive_stats([5])["iqr"] == 0


def test_iqr_flags_high_outlier():
    values = np.array([8, 9, 10, 11, 12, 10, 9, 100], dtype=float)
    dates = [f"2026-01-{i + 1:02d}" for i in range(len(values))]
    found, note = detect_iqr(series(values), dates, values, 1.5)
    assert note is None
    assert len(found) == 1
    assert found[0]["type"] == "spike"
    assert found[0]["observed"] == 100
    assert found[0]["baseline"] == 10


def test_iqr_skips_short_and_constant_samples():
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    found, note = detect_iqr(series([1, 2, 3]), dates, np.array([1, 2, 3]), 1.5)
    assert found == [] and "fewer than 4" in note
    found, note = detect_iqr(series([5] * 6), dates + dates, np.array([5] * 6), 1.5)
    assert found == [] and "zero interquartile" in note


def test_zscore_detects_spike():
    values = np.array([10] * 9 + [1000], dtype=float)
    dates = [f"2026-01-{i + 1:02d}" for i in range(len(values))]
    found, note = detect_zscore(series(values), dates, values, 2.5)
    assert note is None
    assert len(found) == 1
    assert found[0]["type"] == "spike"
    assert found[0]["method"] == "zscore"


def test_moving_average_detects_change_and_warms_up():
    values = np.array([100] * 8 + [200] + [100] * 3, dtype=float)
    dates = [f"2026-01-{i + 1:02d}" for i in range(len(values))]
    found, note = detect_moving(series(values), dates, values, 3, 40)
    assert note is None
    assert any(item["date"] == dates[8] and item["type"] == "spike" for item in found)
    assert all(item["index"] >= 2 for item in found)


def test_moving_average_short_sample_note():
    found, note = detect_moving(
        series([1, 2]), ["2026-01-01", "2026-01-02"], np.array([1, 2]), 7, 50
    )
    assert found == []
    assert "skipped" in note


def test_grubbs_detects_single_extreme():
    values = np.array([10] * 9 + [1000], dtype=float)
    dates = [f"2026-01-{i + 1:02d}" for i in range(len(values))]
    found, note = detect_grubbs(series(values), dates, values, 0.05)
    assert note is None
    assert len(found) == 1
    assert found[0]["method"] == "grubbs"
    assert grubbs_critical(10, 0.05) > 2


def test_grubbs_small_sample_and_constant():
    found, note = detect_grubbs(series([1, 2]), ["2026-01-01", "2026-01-02"], np.array([1, 2]), 0.05)
    assert found == [] and "fewer than 3" in note
    found, note = detect_grubbs(series([2] * 5), ["2026-01-01"] * 5, np.array([2] * 5), 0.05)
    assert found == [] and "zero standard deviation" in note


def test_slice_dataset_and_invalid_range():
    dataset = make_dataset(list(range(20)))
    sliced = slice_dataset(dataset, "2026-01-05", "2026-01-10")
    assert sliced["start"] == "2026-01-05"
    assert sliced["end"] == "2026-01-10"
    assert len(sliced["dates"]) == 6
    with pytest.raises(ValueError):
        slice_dataset(dataset, "2027-01-01", "2027-01-02")
    with pytest.raises(ValueError):
        slice_dataset(dataset, "2026-01-10", "2026-01-05")


def test_analyze_returns_all_methods_and_small_sample_warnings():
    dataset = make_dataset([100, 102, 98, 101, 99, 100, 101, 99, 100, 500])
    result = analyze(dataset, start="2026-01-01", end="2026-01-10")
    assert len(result["stats"]) == 2
    assert result["summary"]["method_counts"]["moving"] >= 1
    assert result["date_range"]["days"] == 10
    assert result["params"]["moving"]["threshold_pct"] == 50
    assert any("Fewer than 30" in warning for warning in result["warnings"])
    assert all("deviation_pct" in anomaly for anomaly in result["anomalies"])


def test_normalize_methods_clamps_inputs():
    params = normalize_methods(
        {
            "iqr": {"enabled": False, "multiplier": -4},
            "zscore": {"threshold": 999},
            "moving": {"window": 1000, "threshold_pct": -1},
            "grubbs": {"alpha": 0.99},
        }
    )
    assert params["iqr"]["enabled"] is False
    assert params["iqr"]["multiplier"] == 0.1
    assert params["zscore"]["threshold"] == 20.0
    assert params["moving"]["window"] == 60
    assert params["moving"]["threshold_pct"] == 1.0
    assert params["grubbs"]["alpha"] == 0.2


def test_polynomial_trend_recovers_quadratic():
    values = [float((x - 20) ** 2) for x in range(41)]
    fitted = polynomial_trend(values, 2)
    assert fitted is not None
    assert max(abs(a - b) for a, b in zip(values, fitted)) < 1e-6


def test_polynomial_trend_insufficient_points():
    assert polynomial_trend([1, 2], 3) == [None, None]
