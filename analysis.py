"""Statistics and anomaly detection for generated mine output."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Iterable

import numpy as np
from scipy import stats as scipy_stats

DEFAULT_METHODS: dict[str, Any] = {
    "iqr": {"enabled": True, "multiplier": 1.5},
    "zscore": {"enabled": True, "threshold": 3.0},
    "moving": {"enabled": True, "window": 7, "threshold_pct": 25.0},
    "grubbs": {"enabled": True, "alpha": 0.05},
}

METHOD_LABELS = {
    "iqr": "IQR rule",
    "zscore": "Z-score",
    "moving": "Moving-average deviation",
    "grubbs": "Grubbs' test",
}

METHOD_SHORT = {"iqr": "IQR", "zscore": "Z", "moving": "MA", "grubbs": "Grubbs"}


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _number(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def normalize_methods(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    iqr = raw.get("iqr") or {}
    zscore = raw.get("zscore") or {}
    moving = raw.get("moving") or {}
    grubbs = raw.get("grubbs") or {}
    return {
        "iqr": {
            "enabled": bool(iqr.get("enabled", True)),
            "multiplier": _number(iqr.get("multiplier"), 1.5, 0.1, 10.0),
        },
        "zscore": {
            "enabled": bool(zscore.get("enabled", True)),
            "threshold": _number(zscore.get("threshold"), 3.0, 0.5, 20.0),
        },
        "moving": {
            "enabled": bool(moving.get("enabled", True)),
            "window": int(_number(moving.get("window"), 7, 2, 60)),
            "threshold_pct": _number(moving.get("threshold_pct"), 50.0, 1.0, 500.0),
        },
        "grubbs": {
            "enabled": bool(grubbs.get("enabled", True)),
            "alpha": _number(grubbs.get("alpha"), 0.05, 0.001, 0.2),
        },
    }


def _series(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    result = [
        {
            "id": "total",
            "label": "Total output",
            "type": "total",
            "mine_number": None,
            "active": True,
            "values": dataset["total"],
        }
    ]
    for mine in dataset["mines"]:
        if not mine.get("active") and not any(abs(value) > 1e-9 for value in mine["values"]):
            continue
        result.append(
            {
                "id": mine["id"],
                "label": mine["name"],
                "type": "mine",
                "mine_number": mine["number"],
                "active": bool(mine.get("active")),
                "values": mine["values"],
            }
        )
    return result


def date_bounds(dataset: dict[str, Any]) -> tuple[str, str]:
    return dataset["dates"][0], dataset["dates"][-1]


def _slice_indices(dataset: dict[str, Any], start: str | None, end: str | None) -> tuple[int, int]:
    dates = dataset["dates"]
    first, last = date_bounds(dataset)
    start = start or first
    end = end or last
    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format") from exc
    if start > end:
        raise ValueError("Start date must be on or before end date")
    lo = max(0, np.searchsorted(dates, start, side="left"))
    hi = min(len(dates), np.searchsorted(dates, end, side="right"))
    if hi <= lo:
        raise ValueError("The selected date range does not overlap the generated data")
    return int(lo), int(hi)


def slice_dataset(dataset: dict[str, Any], start: str | None, end: str | None) -> dict[str, Any]:
    lo, hi = _slice_indices(dataset, start, end)
    dates = dataset["dates"][lo:hi]
    return {
        "start": dates[0],
        "end": dates[-1],
        "requested_start": start or dates[0],
        "requested_end": end or dates[-1],
        "index_start": lo,
        "index_end": hi,
        "dates": dates,
        "total": dataset["total"][lo:hi],
        "mines": [
            {
                **mine,
                "values": mine["values"][lo:hi],
            }
            for mine in dataset["mines"]
        ],
    }


def descriptive_stats(values: Iterable[float]) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    n = int(array.size)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "std": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "min": None,
            "max": None,
        }
    mean = float(np.mean(array))
    std = float(np.std(array, ddof=1)) if n > 1 else 0.0
    q1, median, q3 = (float(value) for value in np.percentile(array, [25, 50, 75]))
    return {
        "n": n,
        "mean": _finite(mean),
        "std": _finite(std),
        "median": _finite(median),
        "q1": _finite(q1),
        "q3": _finite(q3),
        "iqr": _finite(q3 - q1),
        "min": _finite(float(np.min(array))),
        "max": _finite(float(np.max(array))),
    }


def _anomaly(
    *,
    series: dict[str, Any],
    date: str,
    index: int,
    observed: float,
    baseline: float,
    method: str,
    threshold: str,
    kind: str,
) -> dict[str, Any]:
    deviation = observed - baseline
    pct = (deviation / baseline * 100.0) if abs(baseline) > 1e-9 else None
    return {
        "id": f"{series['id']}|{date}|{method}",
        "date": date,
        "index": index,
        "series_id": series["id"],
        "mine": series["label"],
        "mine_number": series["mine_number"],
        "type": kind,
        "observed": _finite(observed),
        "baseline": _finite(baseline),
        "deviation": _finite(deviation),
        "deviation_pct": _finite(pct),
        "method": method,
        "method_label": METHOD_LABELS[method],
        "method_short": METHOD_SHORT[method],
        "threshold": threshold,
    }


def detect_iqr(
    series: dict[str, Any], dates: list[str], values: np.ndarray, multiplier: float
) -> tuple[list[dict[str, Any]], str | None]:
    n = int(values.size)
    if n < 4:
        return [], "IQR skipped: fewer than 4 observations."
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    iqr = float(q3 - q1)
    if iqr <= 1e-12:
        return [], "IQR skipped: zero interquartile range for a constant series."
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    found = []
    for index, value in enumerate(values):
        if value > upper or value < lower:
            found.append(
                _anomaly(
                    series=series,
                    date=dates[index],
                    index=index,
                    observed=float(value),
                    baseline=float(median),
                    method="iqr",
                    threshold=f"k={multiplier:g}; fences {lower:,.1f} / {upper:,.1f}",
                    kind="spike" if value > upper else "drop",
                )
            )
    return found, None


def detect_zscore(
    series: dict[str, Any], dates: list[str], values: np.ndarray, threshold: float
) -> tuple[list[dict[str, Any]], str | None]:
    n = int(values.size)
    if n < 3:
        return [], "Z-score skipped: fewer than 3 observations."
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    if std <= 1e-12:
        return [], "Z-score skipped: zero standard deviation for a constant series."
    z = (values - mean) / std
    found = []
    for index, value in enumerate(values):
        if abs(z[index]) > threshold:
            found.append(
                _anomaly(
                    series=series,
                    date=dates[index],
                    index=index,
                    observed=float(value),
                    baseline=mean,
                    method="zscore",
                    threshold=f"|z| > {threshold:g} (z={z[index]:.2f})",
                    kind="spike" if value > mean else "drop",
                )
            )
    return found, None


def detect_moving(
    series: dict[str, Any],
    dates: list[str],
    values: np.ndarray,
    window: int,
    threshold_pct: float,
) -> tuple[list[dict[str, Any]], str | None]:
    n = int(values.size)
    min_periods = max(2, min(window, window // 2))
    if n <= min_periods:
        return [], f"Moving-average deviation skipped: fewer than {min_periods + 1} observations."
    found = []
    for index in range(min_periods, n):
        baseline_values = values[max(0, index - window) : index]
        baseline = float(np.mean(baseline_values))
        if baseline <= 1e-9:
            continue
        pct = (values[index] - baseline) / baseline * 100.0
        if abs(pct) >= threshold_pct:
            found.append(
                _anomaly(
                    series=series,
                    date=dates[index],
                    index=index,
                    observed=float(values[index]),
                    baseline=baseline,
                    method="moving",
                    threshold=f"{window}-day baseline; |dev| ≥ {threshold_pct:g}%",
                    kind="spike" if pct > 0 else "drop",
                )
            )
    return found, None


def grubbs_critical(n: int, alpha: float) -> float:
    if n < 3:
        raise ValueError("Grubbs' test requires at least 3 observations")
    t_value = scipy_stats.t.ppf(1.0 - alpha / (2.0 * n), n - 2)
    if not math.isfinite(t_value):
        return float("nan")
    return (n - 1) / math.sqrt(n) * math.sqrt((t_value**2) / (n - 2 + t_value**2))


def detect_grubbs(
    series: dict[str, Any], dates: list[str], values: np.ndarray, alpha: float
) -> tuple[list[dict[str, Any]], str | None]:
    n = int(values.size)
    if n < 3:
        return [], "Grubbs' test skipped: fewer than 3 observations."
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    if std <= 1e-12:
        return [], "Grubbs' test skipped: zero standard deviation for a constant series."
    critical = grubbs_critical(n, alpha)
    if not math.isfinite(critical):
        return [], "Grubbs' test skipped: significance level is too small for this sample size."
    deviations = np.abs(values - mean)
    index = int(np.argmax(deviations))
    g_stat = float(deviations[index] / std)
    if g_stat <= critical:
        return [], None
    value = float(values[index])
    return [
        _anomaly(
            series=series,
            date=dates[index],
            index=index,
            observed=value,
            baseline=mean,
            method="grubbs",
            threshold=f"G={g_stat:.3f} > {critical:.3f}; α={alpha:g}",
            kind="spike" if value > mean else "drop",
        )
    ], None


def analyze(
    dataset: dict[str, Any],
    *,
    start: str | None = None,
    end: str | None = None,
    methods: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = normalize_methods(methods)
    selected = slice_dataset(dataset, start, end)
    dates = selected["dates"]
    series = _series(selected)
    warnings: list[str] = []
    stats_rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    if len(dates) < 30:
        warnings.append("Fewer than 30 observations: statistical tests have low power.")

    for item in series:
        values = np.asarray(item["values"], dtype=float)
        result = descriptive_stats(values)
        item_anomalies: list[dict[str, Any]] = []
        if params["iqr"]["enabled"]:
            found, note = detect_iqr(item, dates, values, params["iqr"]["multiplier"])
            item_anomalies.extend(found)
            if note:
                warnings.append(f"{item['label']}: {note}")
        if params["zscore"]["enabled"]:
            found, note = detect_zscore(item, dates, values, params["zscore"]["threshold"])
            item_anomalies.extend(found)
            if note:
                warnings.append(f"{item['label']}: {note}")
        if params["moving"]["enabled"]:
            found, note = detect_moving(
                item,
                dates,
                values,
                params["moving"]["window"],
                params["moving"]["threshold_pct"],
            )
            item_anomalies.extend(found)
            if note:
                warnings.append(f"{item['label']}: {note}")
        if params["grubbs"]["enabled"]:
            found, note = detect_grubbs(item, dates, values, params["grubbs"]["alpha"])
            item_anomalies.extend(found)
            if note:
                warnings.append(f"{item['label']}: {note}")

        anomalies.extend(item_anomalies)
        stats_rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "type": item["type"],
                "mine_number": item["mine_number"],
                "active": item["active"],
                "values": [float(value) for value in values],
                **result,
                "anomaly_count": len(item_anomalies),
                "spike_count": sum(1 for anomaly in item_anomalies if anomaly["type"] == "spike"),
                "drop_count": sum(1 for anomaly in item_anomalies if anomaly["type"] == "drop"),
            }
        )

    anomalies.sort(key=lambda row: (row["date"], row["series_id"], row["method"]))
    method_counts = {
        method: sum(1 for anomaly in anomalies if anomaly["method"] == method)
        for method in METHOD_LABELS
    }
    unique_points = {(anomaly["series_id"], anomaly["date"], anomaly["type"]) for anomaly in anomalies}
    return {
        "date_range": {
            "start": selected["start"],
            "end": selected["end"],
            "compared_start": dates[0],
            "compared_end": dates[-1],
            "index_start": selected["index_start"],
            "index_end": selected["index_end"],
            "days": len(dates),
        },
        "params": params,
        "stats": stats_rows,
        "anomalies": anomalies,
        "summary": {
            "series_count": len(series),
            "anomaly_rows": len(anomalies),
            "unique_points": len(unique_points),
            "spikes": sum(1 for anomaly in anomalies if anomaly["type"] == "spike"),
            "drops": sum(1 for anomaly in anomalies if anomaly["type"] == "drop"),
            "method_counts": method_counts,
        },
        "warnings": sorted(set(warnings)),
        "method_labels": METHOD_LABELS,
        "limitations": [
            "IQR fences and Z-scores assume the selected range is broadly representative; regime changes can create false positives.",
            "The moving-average method compares each day with preceding days only, so it detects abrupt changes rather than sustained shifts.",
            "Grubbs' test reports at most one extreme observation per series and assumes approximately normal data.",
            "Anomalies are statistical signals, not proof of an operational event.",
        ],
    }


def polynomial_trend(values: Iterable[float], degree: int) -> list[float | None]:
    array = np.asarray(list(values), dtype=float)
    n = int(array.size)
    degree = int(degree)
    if degree < 1 or n < degree + 1:
        return [None] * n
    x = np.linspace(-1.0, 1.0, n)
    try:
        coefficients = np.polyfit(x, array, degree)
        fitted = np.polyval(coefficients, x)
    except (np.linalg.LinAlgError, ValueError):
        return [None] * n
    return [float(value) if math.isfinite(value) else None for value in fitted]
