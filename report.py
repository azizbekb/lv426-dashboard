"""Professional PDF report generation."""

from __future__ import annotations

import html
import io
import threading
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from analysis import METHOD_LABELS, polynomial_trend

INK = colors.HexColor("#102A30")
DEEP = colors.HexColor("#0A1B20")
TEAL = colors.HexColor("#0E6B6B")
AMBER = colors.HexColor("#D89B2B")
RED = colors.HexColor("#B63A3A")
BLUE = colors.HexColor("#2E6F9E")
MUTED = colors.HexColor("#64777B")
PAPER = colors.HexColor("#F7F4EC")
ROW = colors.HexColor("#EDF2F0")
LINE = colors.HexColor("#C9D5D2")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 42
CONTENT_W = PAGE_W - 2 * MARGIN


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _num(value: Any, digits: int = 1) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+,.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def _short_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(value or "-")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverEyebrow",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=AMBER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            fontName="Helvetica-Bold",
            fontSize=31,
            leading=34,
            textColor=WHITE,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle2",
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=27,
            textColor=AMBER,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverBody",
            fontName="Helvetica",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#D9E3DF"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            fontName="Helvetica",
            fontSize=8.3,
            leading=11.5,
            textColor=INK,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySmall",
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.6,
            textColor=MUTED,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=INK,
            spaceBefore=2,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHead",
            fontName="Helvetica-Bold",
            fontSize=6.8,
            leading=8.4,
            textColor=WHITE,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            fontName="Helvetica",
            fontSize=6.7,
            leading=8.5,
            textColor=INK,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCellRight",
            fontName="Helvetica",
            fontSize=6.7,
            leading=8.5,
            textColor=INK,
            alignment=TA_RIGHT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DetailLabel",
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=8.3,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DetailValue",
            fontName="Helvetica",
            fontSize=7.3,
            leading=9.3,
            textColor=INK,
        )
    )
    return styles


S = _styles()


def _cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(DEEP)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 13, PAGE_W, 13, stroke=0, fill=1)
    canvas.setFillColor(AMBER)
    canvas.rect(0, PAGE_H - 16, PAGE_W, 3, stroke=0, fill=1)
    canvas.setStrokeColor(colors.HexColor("#335158"))
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 118, PAGE_W - MARGIN, 118)
    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(colors.HexColor("#9EB1B3"))
    canvas.drawString(MARGIN, 102, "WEYLAND-YUTANI // LV-426 MINING DIVISION")
    canvas.drawRightString(PAGE_W - MARGIN, 102, "CONFIDENTIAL - INTERNAL ANALYTICS")
    canvas.drawString(MARGIN, 89, "Source: public Google Spreadsheet snapshot")
    canvas.restoreState()


def _body_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 36, PAGE_W - MARGIN, PAGE_H - 36)
    canvas.line(MARGIN, 35, PAGE_W - MARGIN, 35)
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.setFillColor(TEAL)
    canvas.drawString(MARGIN, PAGE_H - 30, "WEYLAND-YUTANI // EXTRACTION ANALYTICS")
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 30, "ANOMALY REPORT")
    canvas.drawString(MARGIN, 24, "Statistical anomalies are screening signals; validate against operations records.")
    canvas.drawRightString(PAGE_W - MARGIN, 24, f"Page {doc.page}")
    canvas.restoreState()


def _section(title: str, subtitle: str | None = None) -> list[Any]:
    items: list[Any] = [
        Paragraph(_escape(title), S["H1"]),
        HRFlowable(width="100%", thickness=1.2, color=AMBER, spaceBefore=0, spaceAfter=6),
    ]
    if subtitle:
        items.append(Paragraph(_escape(subtitle), S["Body"]))
    return items


def _table(data, widths, *, header=True, font_size=6.7, row_height=13, align_right_from=2):
    table = LongTable(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ]
        for row in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, row), (-1, row), PAPER))
    if align_right_from is not None:
        style.append(("ALIGN", (align_right_from, 1), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def _chart(stats_row: dict[str, Any], dates: list[str], anomalies: list[dict[str, Any]], degree: int) -> Image:
    values = np.asarray(stats_row["values"], dtype=float)
    x = np.arange(values.size)
    date_objects = [datetime.strptime(value, "%Y-%m-%d") for value in dates]
    trend = polynomial_trend(values, degree)

    fig, ax = plt.subplots(figsize=(10.2, 3.6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(date_objects, values, color="#0E6B6B", linewidth=1.35, label="Daily output", zorder=3)

    if trend and any(value is not None for value in trend):
        ax.plot(
            date_objects,
            trend,
            color="#D89B2B",
            linewidth=1.8,
            linestyle="--",
            label=f"Degree {degree} trend",
            zorder=4,
        )

    unique: dict[str, dict[str, Any]] = {}
    for anomaly in anomalies:
        if anomaly["series_id"] != stats_row["id"]:
            continue
        unique[f"{anomaly['date']}|{anomaly['type']}"] = anomaly
    spike_dates = [
        datetime.strptime(item["date"], "%Y-%m-%d")
        for item in unique.values()
        if item["type"] == "spike"
    ]
    drop_dates = [
        datetime.strptime(item["date"], "%Y-%m-%d")
        for item in unique.values()
        if item["type"] == "drop"
    ]
    value_by_date = dict(zip(date_objects, values))
    if spike_dates:
        ax.scatter(
            spike_dates,
            [value_by_date[item] for item in spike_dates],
            marker="^",
            s=44,
            color="#B63A3A",
            edgecolor="white",
            linewidth=0.6,
            label="Detected spike",
            zorder=6,
        )
    if drop_dates:
        ax.scatter(
            drop_dates,
            [value_by_date[item] for item in drop_dates],
            marker="v",
            s=44,
            color="#2E6F9E",
            edgecolor="white",
            linewidth=0.6,
            label="Detected drop",
            zorder=6,
        )

    ax.set_title(
        f"{stats_row['label']} - outlier review (degree {degree} trend)",
        loc="left",
        fontsize=10,
        fontweight="bold",
        color="#102A30",
        pad=8,
    )
    ax.set_ylabel("tonnes / day", fontsize=7.5, color="#4B5E62")
    ax.set_xlabel("Date", fontsize=7.5, color="#4B5E62")
    ax.grid(True, axis="y", color="#DCE6E3", linewidth=0.55)
    ax.grid(True, axis="x", color="#EEF3F1", linewidth=0.4)
    ax.tick_params(axis="both", labelsize=6.4, colors="#4B5E62")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#A8B8B4")
    span_days = (date_objects[-1] - date_objects[0]).days if len(date_objects) > 1 else 0
    if span_days > 540:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    elif span_days > 150:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(7, span_days // 6)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.margins(x=0.01)
    ax.legend(
        loc="upper left",
        fontsize=6.3,
        frameon=True,
        facecolor="white",
        edgecolor="#D7E2DF",
        ncol=3,
        handlelength=1.6,
    )
    fig.tight_layout(pad=0.7)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=CONTENT_W, height=CONTENT_W * 3.6 / 10.2)


def _detail_block(index: int, total: int, anomaly: dict[str, Any], styles) -> KeepTogether:
    type_color = "#B63A3A" if anomaly["type"] == "spike" else "#2E6F9E"
    type_text = "SPIKE" if anomaly["type"] == "spike" else "DROP"
    title = Paragraph(
        f"<font color='#64777B'>ANOMALY {index:02d} / {total:02d}</font> &nbsp; "
        f"<font color='{type_color}'><b>{type_text}</b></font> &nbsp; "
        f"{_escape(_short_date(anomaly['date']))} &nbsp; {_escape(anomaly['mine'])}",
        ParagraphStyle(
            name="AnomalyTitle",
            fontName="Helvetica-Bold",
            fontSize=8.7,
            leading=11,
            textColor=INK,
            spaceBefore=2,
            spaceAfter=3,
        ),
    )
    rows = [
        [
            Paragraph("DATE", styles["DetailLabel"]),
            Paragraph(_escape(_short_date(anomaly["date"])), styles["DetailValue"]),
            Paragraph("MINE / SERIES", styles["DetailLabel"]),
            Paragraph(_escape(anomaly["mine"]), styles["DetailValue"]),
        ],
        [
            Paragraph("MEASURED OUTPUT", styles["DetailLabel"]),
            Paragraph(f"{_num(anomaly['observed'])} t/day", styles["DetailValue"]),
            Paragraph("BASELINE", styles["DetailLabel"]),
            Paragraph(f"{_num(anomaly['baseline'])} t/day", styles["DetailValue"]),
        ],
        [
            Paragraph("DEVIATION", styles["DetailLabel"]),
            Paragraph(f"{_num(anomaly['deviation'])} t/day", styles["DetailValue"]),
            Paragraph("DEVIATION %", styles["DetailLabel"]),
            Paragraph(_pct(anomaly["deviation_pct"]), styles["DetailValue"]),
        ],
        [
            Paragraph("METHOD", styles["DetailLabel"]),
            Paragraph(_escape(METHOD_LABELS.get(anomaly["method"], anomaly["method"])), styles["DetailValue"]),
            Paragraph("THRESHOLD", styles["DetailLabel"]),
            Paragraph(_escape(anomaly["threshold"]), styles["DetailValue"]),
        ],
    ]
    table = Table(rows, colWidths=[78, 142, 62, 130])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF9F2")),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(type_color)),
            ]
        )
    )
    explanation = (
        f"The observed value is {_num(abs(anomaly['deviation']))} t/day "
        f"{'above' if anomaly['type'] == 'spike' else 'below'} the "
        f"{_num(anomaly['baseline'])} t/day baseline, a change of "
        f"{_pct(anomaly['deviation_pct'])}. Detection method: "
        f"{_escape(METHOD_LABELS.get(anomaly['method'], anomaly['method']))}."
    )
    return KeepTogether(
        [
            Spacer(1, 4),
            title,
            table,
            Paragraph(explanation, styles["BodySmall"]),
            Spacer(1, 5),
        ]
    )


_REPORT_LOCK = threading.Lock()


def build_pdf(
    dataset: dict[str, Any],
    analysis: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> bytes:
    with _REPORT_LOCK:
        return _build_pdf(dataset, analysis, options)


def _build_pdf(
    dataset: dict[str, Any],
    analysis: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> bytes:
    options = options or {}
    degree = int(options.get("trend_degree", 1) or 1)
    if degree not in {1, 2, 3, 4}:
        degree = 1
    selected_id = str(options.get("series_id", "total"))
    chart_type = str(options.get("chart_type", "line"))

    generated = datetime.now(timezone.utc)
    generated_text = generated.strftime("%d %b %Y, %H:%M UTC")
    range_info = analysis["date_range"]
    stats = analysis["stats"]
    anomalies = analysis["anomalies"]
    stats_by_id = {row["id"]: row for row in stats}
    if selected_id not in stats_by_id:
        selected_id = "total"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=58,
        bottomMargin=50,
        title="Weyland-Yutani Daily Extraction Anomaly Report",
        author="Weyland-Yutani Extraction Analytics",
        subject=f"Anomaly report {range_info['start']} to {range_info['end']}",
    )

    story: list[Any] = []
    total_row = stats_by_id["total"]

    # Cover
    story += [
        Spacer(1, 48),
        Paragraph("WEYLAND-YUTANI // LV-426 MINING DIVISION", S["CoverEyebrow"]),
        Paragraph("DAILY EXTRACTION", S["CoverTitle"]),
        Paragraph("ANOMALY REPORT", S["CoverTitle2"]),
        HRFlowable(width="55%", thickness=1.4, color=AMBER, spaceBefore=2, spaceAfter=18, hAlign="LEFT"),
        Paragraph(
            "Statistical surveillance of generated daily output across the LV-426 mine fleet.",
            ParagraphStyle(
                name="CoverLead",
                fontName="Helvetica",
                fontSize=11,
                leading=16,
                textColor=WHITE,
                spaceAfter=18,
            ),
        ),
        Table(
            [
                [
                    Paragraph("SELECTED RANGE", S["DetailLabel"]),
                    Paragraph(f"{_short_date(range_info['start'])} to {_short_date(range_info['end'])}", S["CoverBody"]),
                ],
                [
                    Paragraph("GENERATED", S["DetailLabel"]),
                    Paragraph(generated_text, S["CoverBody"]),
                ],
                [
                    Paragraph("DATA SNAPSHOT", S["DetailLabel"]),
                    Paragraph(
                        _escape(dataset["source"].get("fetched_at", "-")),
                        S["CoverBody"],
                    ),
                ],
                [
                    Paragraph("SERIES / DAYS", S["DetailLabel"]),
                    Paragraph(f"{len(stats)} series / {range_info['days']} daily observations", S["CoverBody"]),
                ],
            ],
            colWidths=[92, 330],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#D9E3DF")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#335158")),
                ]
            ),
        ),
        Spacer(1, 28),
        Table(
            [
                [
                    Paragraph("<font color='#D89B2B'><b>MEAN TOTAL</b></font>", S["CoverBody"]),
                    Paragraph("<font color='#D89B2B'><b>DETECTIONS</b></font>", S["CoverBody"]),
                    Paragraph("<font color='#D89B2B'><b>SPIKES / DROPS</b></font>", S["CoverBody"]),
                ],
                [
                    Paragraph(
                        f"<font size='18' color='#FFFFFF'><b>{_num(total_row['mean'], 0)}</b></font><font color='#D9E3DF'> t/day</font>",
                        S["CoverBody"],
                    ),
                    Paragraph(
                        f"<font size='18' color='#FFFFFF'><b>{analysis['summary']['anomaly_rows']}</b></font><font color='#D9E3DF'> method hits</font>",
                        S["CoverBody"],
                    ),
                    Paragraph(
                        f"<font size='18' color='#FFFFFF'><b>{analysis['summary']['spikes']} / {analysis['summary']['drops']}</b></font>",
                        S["CoverBody"],
                    ),
                ],
            ],
            colWidths=[170, 170, 170],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#132F35")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#335158")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#335158")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        Spacer(1, 24),
        Paragraph(
            f"Source: <link href='{_escape(dataset['source']['spreadsheet_url'])}' color='#D89B2B'>"
            "Weyland-Yutani extraction workbook</link> (read-only snapshot). "
            f"Report preference: {_escape(stats_by_id[selected_id]['label'])}, {degree}-degree trend.",
            S["CoverBody"],
        ),
    ]

    story.append(PageBreak())

    # Executive summary
    story += _section(
        "1. Executive summary",
        "Formula-generated daily mine output was read from the workbook, filtered to the selected range, and screened with four configurable statistical methods.",
    )
    summary_kpis = Table(
        [
            [
                Paragraph("TOTAL MEAN", S["DetailLabel"]),
                Paragraph("TOTAL MEDIAN", S["DetailLabel"]),
                Paragraph("TOTAL STD DEV", S["DetailLabel"]),
                Paragraph("DETECTION ROWS", S["DetailLabel"]),
            ],
            [
                Paragraph(f"<b>{_num(total_row['mean'], 0)}</b> t/day", S["Body"]),
                Paragraph(f"<b>{_num(total_row['median'], 0)}</b> t/day", S["Body"]),
                Paragraph(f"<b>{_num(total_row['std'], 0)}</b> t/day", S["Body"]),
                Paragraph(f"<b>{analysis['summary']['anomaly_rows']}</b> across methods", S["Body"]),
            ],
        ],
        colWidths=[CONTENT_W / 4] * 4,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    story += [
        summary_kpis,
        Spacer(1, 8),
        Paragraph(
            "The analysis builds a baseline for every active mine and for total output. "
            "A detection row is a method-specific signal; the same date may appear under more than one method. "
            f"The selected comparison window was {_short_date(range_info['start'])} to {_short_date(range_info['end'])} "
            f"({range_info['days']} days).",
            S["Body"],
        ),
        Paragraph("<b>Detections by method</b>", S["H2"]),
        Table(
            [["Method", "Detections", "Configuration"]] +
            [
                [
                    METHOD_LABELS[key],
                    str(analysis["summary"]["method_counts"].get(key, 0)),
                    _parameter_summary(key, analysis["params"]),
                ]
                for key in ("iqr", "zscore", "moving", "grubbs")
            ],
            colWidths=[150, 70, 291],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("LEADING", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                    ("BACKGROUND", (0, 2), (-1, 2), PAPER),
                    ("BACKGROUND", (0, 4), (-1, 4), PAPER),
                    ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        ),
        Spacer(1, 8),
        Paragraph(
            f"Data quality: {dataset['row_count']} rows in the source tab; {len(stats) - 1} active mine series plus total. "
            f"Snapshot time: {_escape(dataset['source'].get('fetched_at', '-'))}.",
            S["BodySmall"],
        ),
    ]

    # Summary statistics
    story.append(PageBreak())
    story += _section(
        "2. Summary statistics",
        "Mean, sample standard deviation, median, and interquartile range for every active mine and total output.",
    )
    stats_table = [
        ["Series", "N", "Mean", "Std dev", "Median", "IQR", "Detections", "Spikes / drops"]
    ]
    for row in stats:
        stats_table.append(
            [
                row["label"],
                str(row["n"]),
                _num(row["mean"]),
                _num(row["std"]),
                _num(row["median"]),
                _num(row["iqr"]),
                str(row["anomaly_count"]),
                f"{row['spike_count']} / {row['drop_count']}",
            ]
        )
    story.append(
        _table(
            stats_table,
            [124, 28, 66, 62, 66, 54, 61, 50],
            align_right_from=1,
        )
    )
    story += [
        Spacer(1, 5),
        Paragraph(
            "All values are tonnes per day. Standard deviation uses the sample estimator (n-1). "
            "IQR is Q3 minus Q1 using linear interpolation. Detection counts are method-specific and may overlap.",
            S["BodySmall"],
        ),
    ]

    # Parameters and limitations
    story.append(PageBreak())
    story += _section(
        "3. Detection parameters and limitations",
        "The report uses the settings supplied by the dashboard at generation time.",
    )
    parameter_table = [["Method", "Enabled", "Parameter", "Rule / baseline"]]
    parameter_table += [
        [
            METHOD_LABELS[key],
            "Yes" if analysis["params"][key]["enabled"] else "No",
            _parameter_summary(key, analysis["params"]),
            _parameter_rule(key),
        ]
        for key in ("iqr", "zscore", "moving", "grubbs")
    ]
    story.append(_table(parameter_table, [126, 48, 118, 219], align_right_from=None))
    story += [
        Spacer(1, 8),
        Paragraph("Interpretation notes", S["H2"]),
    ]
    notes = [
        "IQR fences are robust to moderate skew but flag any point outside the fences, including sustained regime changes.",
        "Z-scores use the selected window's mean and standard deviation; a single extreme value can inflate the standard deviation.",
        "Moving-average deviations compare each day with preceding days only and require a minimum warm-up period.",
        "Grubbs' test identifies at most one extreme observation per series and assumes approximately normal observations.",
        "Statistical anomalies are screening signals. Validate mine-level results against maintenance, staffing, and event records.",
    ]
    for note in notes:
        story.append(Paragraph(f"- {_escape(note)}", S["Body"]))
    if analysis["warnings"]:
        story.append(Paragraph("Small-sample and method limits", S["H2"]))
        for warning in analysis["warnings"][:18]:
            story.append(Paragraph(f"- {_escape(warning)}", S["BodySmall"]))
        if len(analysis["warnings"]) > 18:
            story.append(
                Paragraph(
                    f"- {len(analysis['warnings']) - 18} additional series-level notices are omitted here; they do not change the detections shown.",
                    S["BodySmall"],
                )
            )

    # Charts
    story.append(PageBreak())
    story += _section(
        "4. Outlier charts",
        "Daily series with detected spikes (red triangles) and drops (blue inverted triangles). Dashed line: selected polynomial trend.",
    )
    chart_ids = ["total"]
    if selected_id != "total":
        chart_ids.append(selected_id)
    anomaly_ids = []
    for anomaly in anomalies:
        if anomaly["series_id"] not in chart_ids and anomaly["series_id"] not in anomaly_ids:
            anomaly_ids.append(anomaly["series_id"])
    chart_ids += anomaly_ids
    story.append(
        Paragraph(
            f"Chart preference from dashboard: {_escape(chart_type)}. PDF charts use a line rendering so that daily values, outliers, and the {degree}-degree trend remain readable.",
            S["BodySmall"],
        )
    )
    for index, series_id in enumerate(chart_ids):
        row = stats_by_id.get(series_id)
        if not row:
            continue
        if index and index % 3 == 0:
            story.append(PageBreak())
        story.append(
            KeepTogether(
                [
                    _chart(row, _dates_for_chart(dataset, range_info), anomalies, degree),
                    Paragraph(
                        f"<b>{_escape(row['label'])}</b> - {row['n']} observations, {row['anomaly_count']} method detections.",
                        S["BodySmall"],
                    ),
                ]
            )
        )

    # Anomaly table
    story.append(PageBreak())
    story += _section(
        "5. Detected anomalies",
        "One row per method detection. The same observation can be confirmed by more than one method.",
    )
    if anomalies:
        anomaly_table = [["Date", "Mine", "Type", "Observed", "Baseline", "Deviation", "Method"]]
        for anomaly in anomalies:
            anomaly_table.append(
                [
                    _short_date(anomaly["date"]),
                    anomaly["mine"],
                    anomaly["type"].upper(),
                    _num(anomaly["observed"]),
                    _num(anomaly["baseline"]),
                    f"{_num(anomaly['deviation'])} ({_pct(anomaly['deviation_pct'])})",
                    METHOD_LABELS.get(anomaly["method"], anomaly["method"]),
                ]
            )
        story.append(_table(anomaly_table, [61, 88, 40, 62, 62, 98, 100], align_right_from=3))
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                "Observed, baseline, and deviation are tonnes per day; the value in parentheses is percentage deviation.",
                S["BodySmall"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No observations crossed the configured thresholds in this date range.",
                S["Body"],
            )
        )

    # Detailed review
    story.append(PageBreak())
    story += _section(
        "6. Detailed anomaly review",
        "Each detected spike or drop is listed separately with its measured value, baseline, method, threshold, and deviation.",
    )
    if anomalies:
        for index, anomaly in enumerate(anomalies, start=1):
            story.append(_detail_block(index, len(anomalies), anomaly, S))
    else:
        story.append(
            Paragraph(
                "No separate anomaly review is required because no detections were produced.",
                S["Body"],
            )
        )

    # Appendix
    story.append(PageBreak())
    story += _section(
        "Appendix A. Data provenance and method notes",
        "This report is generated from a read-only snapshot of the formula-driven Google Spreadsheet.",
    )
    provenance = [
        ["Source workbook", dataset["source"].get("spreadsheet_url", "-")],
        ["Spreadsheet ID", dataset["source"].get("spreadsheet_id", "-")],
        ["Snapshot retrieved", dataset["source"].get("fetched_at", "-")],
        ["Report generated", generated_text],
        ["Selected range", f"{_short_date(range_info['start'])} to {_short_date(range_info['end'])}"],
        ["Source rows", str(dataset["row_count"])],
        ["Active mine series", str(len(stats) - 1)],
        ["Dashboard preference", f"{stats_by_id[selected_id]['label']}; {chart_type}; degree {degree} trend"],
    ]
    provenance_table = [
        [Paragraph(_escape(key), S["DetailLabel"]), Paragraph(_escape(value), S["DetailValue"])]
        for key, value in provenance
    ]
    story.append(Table(provenance_table, colWidths=[118, 393], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))
    story += [
        Spacer(1, 8),
        Paragraph(
            "The generator tab uses live formulas. This report reflects the values present when the snapshot was retrieved; "
            "use Refresh Data in the dashboard before regenerating if generator parameters have changed.",
            S["Body"],
        ),
        Spacer(1, 5),
        Paragraph(
            "Prepared by the Weyland-Yutani Extraction Analytics dashboard. Not an operational safety or financial control.",
            S["BodySmall"],
        ),
    ]

    doc.build(story, onFirstPage=_cover_page, onLaterPages=_body_page)
    return buf.getvalue()


def _parameter_summary(key: str, params: dict[str, Any]) -> str:
    if key == "iqr":
        return f"k = {params['iqr']['multiplier']:g}"
    if key == "zscore":
        return f"|z| > {params['zscore']['threshold']:g}"
    if key == "moving":
        return f"{params['moving']['window']}-day window; {params['moving']['threshold_pct']:g}%"
    if key == "grubbs":
        return f"alpha = {params['grubbs']['alpha']:g}"
    return ""


def _parameter_rule(key: str) -> str:
    return {
        "iqr": "Q1 - k*IQR / Q3 + k*IQR; median baseline",
        "zscore": "mean +/- threshold * sample std dev",
        "moving": "mean of preceding window; deviation threshold",
        "grubbs": "two-sided max standardized residual test",
    }[key]


def _dates_for_chart(dataset: dict[str, Any], range_info: dict[str, Any]) -> list[str]:
    """Return the exact date labels for the analyzed interval."""
    dates = dataset["dates"]
    start = range_info["start"]
    end = range_info["end"]
    lo = int(np.searchsorted(dates, start, side="left"))
    hi = int(np.searchsorted(dates, end, side="right"))
    return dates[lo:hi]
