(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const PALETTE = [
    "#53b8af", "#d8a24a", "#7ba7d1", "#c97b6d", "#8cc58e", "#b58ac6",
    "#6fc4cf", "#caa46d", "#7f92cf", "#c687a8", "#a6bf72", "#d09a64",
    "#65a9a1", "#9f9cda", "#d3b66b"
  ];

  const state = {
    dataset: null,
    analysis: null,
    chart: null,
    range: { start: null, end: null },
    loading: false,
    requestSeq: 0,
    selectedSeries: "total",
    hasLoaded: false,
    lastWarning: null,
  };

  const el = {};

  document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    if (window.Chart) {
      Chart.defaults.color = "#8fa6a6";
      Chart.defaults.font.family = '"IBM Plex Mono", Consolas, monospace';
      Chart.defaults.font.size = 9;
    }
    loadDataset(false);
  });

  function cacheElements() {
    const ids = [
      "loadingBar", "sourcePill", "sourceDot", "sourceText", "snapshotText", "refreshBtn",
      "pdfBtn", "errorBanner", "errorText", "retryBtn", "sourceLink", "coverageText",
      "mineCountText", "eventCountText", "startDate", "endDate", "applyRangeBtn",
      "ctxDistribution", "ctxTrend", "ctxActive", "ctxSeed", "kpiMean", "kpiMedian",
      "kpiStd", "kpiIqr", "kpiAnomalies", "kpiDays", "kpiMeanFoot", "kpiMedianFoot",
      "kpiIqrFoot", "kpiAnomalyUnit", "kpiAnomalyFoot", "kpiDaysFoot", "chartTitle",
      "seriesSelect", "chartType", "trendDegree", "showOutliers", "chartNote",
      "mainChart", "chartLoading", "methodBadge", "methodsForm", "applyMethodsBtn",
      "methodSummary", "warningsToggle", "warningsLabel", "warningsBox", "statsMeta",
      "statsBody", "anomalyMethodFilter", "anomalyTypeFilter", "anomalyCount",
      "anomalyBody", "footerRange", "footerFetched", "toast", "pdfOverlay",
      "pdfModalTitle", "pdfModalText"
    ];
    ids.forEach((id) => { el[id] = document.getElementById(id); });
  }

  function bindEvents() {
    el.refreshBtn.addEventListener("click", () => loadDataset(true));
    el.retryBtn.addEventListener("click", () => loadDataset(true));
    el.applyRangeBtn.addEventListener("click", () => applyRange());
    el.startDate.addEventListener("change", () => setActivePreset(null));
    el.endDate.addEventListener("change", () => setActivePreset(null));
    $$(".preset").forEach((button) => {
      button.addEventListener("click", () => {
        if (!state.dataset) return;
        const days = button.dataset.days;
        setActivePreset(button);
        if (days === "all") {
          el.startDate.value = state.dataset.dates[0];
          el.endDate.value = state.dataset.dates[state.dataset.dates.length - 1];
        } else {
          const end = state.dataset.dates[state.dataset.dates.length - 1];
          const endDate = parseISO(end);
          endDate.setUTCDate(endDate.getUTCDate() - (Number(days) - 1));
          const start = toISO(endDate);
          el.startDate.value = start < state.dataset.dates[0] ? state.dataset.dates[0] : start;
          el.endDate.value = end;
        }
        applyRange();
      });
    });

    el.applyMethodsBtn.addEventListener("click", () => runAnalysis());
    el.methodsForm.addEventListener("submit", (event) => {
      event.preventDefault();
      runAnalysis();
    });
    $$("[data-enable]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        syncMethodCards();
        updateMethodBadge();
      });
    });

    el.seriesSelect.addEventListener("change", () => {
      state.selectedSeries = el.seriesSelect.value;
      renderChart();
      renderChartNote();
    });
    el.chartType.addEventListener("change", () => {
      renderChart();
      renderChartNote();
    });
    el.trendDegree.addEventListener("change", () => {
      renderChart();
      renderChartNote();
    });
    el.showOutliers.addEventListener("change", renderChart);

    el.statsBody.addEventListener("click", (event) => {
      const row = event.target.closest("tr[data-series-id]");
      if (!row) return;
      state.selectedSeries = row.dataset.seriesId;
      if (el.seriesSelect.value !== state.selectedSeries) el.seriesSelect.value = state.selectedSeries;
      renderChart();
      renderChartNote();
      $(".chart-panel").scrollIntoView({ behavior: "smooth", block: "center" });
    });

    el.anomalyMethodFilter.addEventListener("change", renderAnomalies);
    el.anomalyTypeFilter.addEventListener("change", renderAnomalies);
    el.warningsToggle.addEventListener("click", () => {
      const isHidden = el.warningsBox.hidden;
      el.warningsBox.hidden = !isHidden;
      el.warningsToggle.querySelector("span:last-child").textContent = isHidden ? "-" : "+";
    });
    el.pdfBtn.addEventListener("click", generatePdf);
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !el.pdfOverlay.hidden) {
        showToast("Report generation cannot be interrupted safely; please wait.", "error");
      }
    });
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const payload = await response.json();
        if (payload && payload.error) message = payload.error;
      } catch (_) { /* keep generic message */ }
      throw new Error(message);
    }
    return response;
  }

  async function loadDataset(force) {
    if (state.loading) return;
    setBusy(true);
    setError(null);
    setSourceState("loading");
    el.sourceText.textContent = force ? "Refreshing workbook" : "Loading workbook";
    try {
      const response = await api(`/api/dataset${force ? "?refresh=1" : ""}`);
      const payload = await response.json();
      const dataset = payload.data;
      state.dataset = dataset;
      state.hasLoaded = true;
      renderDatasetMeta();
      setupDateBounds();
      if (!force || !state.range.start) {
        setDefaultRange();
      }
      const analyzed = await runAnalysis({ preserveBusy: true });
      if (!analyzed) {
        el.sourceText.textContent = "Analysis failed";
        return;
      }
      setSourceState("live");
      if (dataset.warning) {
        showToast(dataset.warning, "error");
      } else if (force) {
        showToast(`Workbook refreshed. ${dataset.row_count} daily rows loaded.`);
      }
    } catch (error) {
      const message = humanizeError(error);
      setSourceState("error");
      setError(message);
      el.sourceText.textContent = "Workbook unavailable";
      renderFatalState(message);
    } finally {
      setBusy(false);
    }
  }

  function setDefaultRange() {
    if (!state.dataset) return;
    const end = state.dataset.dates[state.dataset.dates.length - 1];
    const endDate = parseISO(end);
    endDate.setUTCDate(endDate.getUTCDate() - 89);
    let start = toISO(endDate);
    if (start < state.dataset.dates[0]) start = state.dataset.dates[0];
    state.range = { start, end };
    el.startDate.value = start;
    el.endDate.value = end;
    setActivePreset($$(".preset").find((button) => button.dataset.days === "90") || null);
  }

  function setupDateBounds() {
    if (!state.dataset) return;
    el.startDate.min = state.dataset.dates[0];
    el.startDate.max = state.dataset.dates[state.dataset.dates.length - 1];
    el.endDate.min = state.dataset.dates[0];
    el.endDate.max = state.dataset.dates[state.dataset.dates.length - 1];
    if (el.startDate.value < el.startDate.min) el.startDate.value = el.startDate.min;
    if (el.endDate.value > el.endDate.max) el.endDate.value = el.endDate.max;
  }

  async function applyRange() {
    const start = el.startDate.value;
    const end = el.endDate.value;
    if (!start || !end) {
      showToast("Choose both a start and end date.", "error");
      return;
    }
    if (start > end) {
      showToast("Start date must be on or before end date.", "error");
      return;
    }
    state.range = { start, end };
    await runAnalysis();
  }

  async function runAnalysis(options = {}) {
    if (!state.dataset) return;
    let methods;
    try {
      methods = gatherMethods();
    } catch (error) {
      showToast(error.message, "error");
      return;
    }
    const start = state.range.start || el.startDate.value;
    const end = state.range.end || el.endDate.value;
    const seq = ++state.requestSeq;
    setChartLoading(true);
    el.applyMethodsBtn.disabled = true;
    el.applyMethodsBtn.classList.add("is-loading");
    if (!options.preserveBusy) setBusy(true);
    try {
      const response = await api("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ start, end, methods }),
      });
      const payload = await response.json();
      if (seq !== state.requestSeq) return;
      state.analysis = payload.analysis;
      if (payload.data && payload.data.warning) state.lastWarning = payload.data.warning;
      renderAll();
      setSourceState("live");
      if (payload.data) {
        el.snapshotText.textContent = `Snapshot ${friendlyTimestamp(payload.data.source.fetched_at)}`;
      }
      return true;
    } catch (error) {
      if (seq !== state.requestSeq) return;
      const message = humanizeError(error);
      setError(message);
      setSourceState("error");
      showToast(message, "error");
      return false;
    } finally {
      if (seq === state.requestSeq) {
        setChartLoading(false);
        el.applyMethodsBtn.disabled = false;
        el.applyMethodsBtn.classList.remove("is-loading");
        if (!options.preserveBusy) setBusy(false);
      }
    }
  }

  function gatherMethods() {
    const enabled = (key) => $(`[data-enable="${key}"]`).checked;
    const number = (key) => Number($(`[data-param="${key}"]`).value);
    const iqrMultiplier = number("iqr.multiplier");
    const zThreshold = number("zscore.threshold");
    const movingWindow = number("moving.window");
    const movingThreshold = number("moving.threshold_pct");
    const alpha = number("grubbs.alpha");
    if (!Number.isFinite(iqrMultiplier) || iqrMultiplier <= 0) throw new Error("IQR multiplier must be greater than zero.");
    if (!Number.isFinite(zThreshold) || zThreshold <= 0) throw new Error("Z-score threshold must be greater than zero.");
    if (!Number.isInteger(movingWindow) || movingWindow < 2 || movingWindow > 60) throw new Error("Moving-average window must be a whole number from 2 to 60.");
    if (!Number.isFinite(movingThreshold) || movingThreshold <= 0) throw new Error("Moving-average threshold must be greater than zero.");
    if (!Number.isFinite(alpha) || alpha <= 0 || alpha >= 1) throw new Error("Grubbs significance must be between 0 and 1.");
    return {
      iqr: { enabled: enabled("iqr"), multiplier: iqrMultiplier },
      zscore: { enabled: enabled("zscore"), threshold: zThreshold },
      moving: { enabled: enabled("moving"), window: Math.round(movingWindow), threshold_pct: movingThreshold },
      grubbs: { enabled: enabled("grubbs"), alpha },
    };
  }

  function syncMethodCards() {
    $$(".method-card").forEach((card) => {
      const checkbox = card.querySelector("[data-enable]");
      card.classList.toggle("is-disabled", !checkbox.checked);
      card.querySelectorAll("[data-param]").forEach((input) => {
        input.disabled = !checkbox.checked;
      });
    });
  }

  function updateMethodBadge() {
    const count = $$("[data-enable]").filter((checkbox) => checkbox.checked).length;
    el.methodBadge.textContent = `${count} active`;
  }

  function renderAll() {
    if (!state.analysis) return;
    syncMethodCards();
    updateMethodBadge();
    renderDatasetMeta();
    renderKpis();
    renderContext();
    renderSeriesOptions();
    renderStats();
    renderAnomalies();
    renderMethodSummary();
    renderWarnings();
    renderChartNote();
    renderChart();
    el.pdfBtn.disabled = false;
    el.footerRange.textContent = `Range ${friendlyDate(state.analysis.date_range.start)} - ${friendlyDate(state.analysis.date_range.end)}`;
  }

  function renderDatasetMeta() {
    if (!state.dataset) return;
    const data = state.dataset;
    el.sourceLink.href = data.source.spreadsheet_url;
    el.coverageText.textContent = `${friendlyDate(data.dates[0])} - ${friendlyDate(data.dates[data.dates.length - 1])}`;
    const activeSeries = (state.analysis ? state.analysis.stats.length - 1 : data.mines.filter((mine) => mine.active).length);
    el.mineCountText.textContent = `${activeSeries} active`;
    el.eventCountText.textContent = `${data.controls.events.length} configured`;
    const fetched = friendlyTimestamp(data.source.fetched_at);
    el.snapshotText.textContent = `Snapshot ${fetched}`;
    el.footerFetched.textContent = `Snapshot ${fetched}`;
    el.sourceText.textContent = data.cache === "stale" ? "Cached snapshot" : "Workbook connected";
    setSourceState(data.cache === "stale" ? "error" : "live");
  }

  function renderContext() {
    if (!state.dataset || !state.analysis) return;
    const controls = state.dataset.controls;
    const active = controls.window.active_mines || state.analysis.stats.length - 1;
    const dist = controls.distribution;
    let distributionText = dist.type || "Normal";
    if (distributionText.toLowerCase().startsWith("norm")) {
      distributionText += ` / ${formatNumber(dist.normal_mean, 2)}x`;
    } else {
      distributionText += ` / ${formatNumber(dist.uniform_min, 2)}-${formatNumber(dist.uniform_max, 2)}x`;
    }
    el.ctxDistribution.textContent = distributionText;
    el.ctxTrend.textContent = `${formatNumber((controls.dynamics.annual_trend || 0) * 100, 1)}% / yr`;
    el.ctxActive.textContent = `${Math.round(active)} of ${controls.mines.length}`;
    el.ctxSeed.textContent = String(Math.round(controls.dynamics.seed || 0));
  }

  function renderKpis() {
    const analysis = state.analysis;
    const total = analysis.stats.find((row) => row.id === "total");
    if (!total) return;
    el.kpiMean.textContent = formatNumber(total.mean, 0);
    el.kpiMedian.textContent = formatNumber(total.median, 0);
    el.kpiStd.textContent = formatNumber(total.std, 0);
    el.kpiIqr.textContent = formatNumber(total.iqr, 0);
    el.kpiAnomalies.textContent = String(analysis.summary.anomaly_rows);
    el.kpiDays.textContent = String(analysis.date_range.days);
    el.kpiMeanFoot.textContent = `${friendlyDate(analysis.date_range.start)} - ${friendlyDate(analysis.date_range.end)}`;
    el.kpiMedianFoot.textContent = "Robust to extreme days";
    el.kpiIqrFoot.textContent = `Q1 ${formatNumber(total.q1, 0)} / Q3 ${formatNumber(total.q3, 0)}`;
    el.kpiAnomalyUnit.textContent = `${analysis.summary.unique_points} unique observations`;
    el.kpiAnomalyFoot.textContent = `${analysis.summary.spikes} spikes / ${analysis.summary.drops} drops`;
    el.kpiDaysFoot.textContent = `from ${state.dataset.row_count} source days`;
    el.statsMeta.textContent = `${analysis.stats.length - 1} mines + total / ${analysis.date_range.days} days`;
  }

  function renderSeriesOptions() {
    const current = state.selectedSeries;
    el.seriesSelect.innerHTML = "";
    state.analysis.stats.forEach((row) => {
      const option = document.createElement("option");
      option.value = row.id;
      option.textContent = row.id === "total" ? "Total output" : row.label;
      el.seriesSelect.appendChild(option);
    });
    if (state.analysis.stats.some((row) => row.id === current)) {
      state.selectedSeries = current;
    } else {
      state.selectedSeries = "total";
    }
    el.seriesSelect.value = state.selectedSeries;
  }

  function renderStats() {
    const rows = state.analysis.stats;
    el.statsBody.innerHTML = rows.map((row) => {
      const isTotal = row.id === "total";
      return `
        <tr class="${isTotal ? "total-row" : ""}" data-series-id="${escapeHtml(row.id)}" title="Click to chart this series">
          <td class="mine-name">${escapeHtml(row.label)}</td>
          <td class="num">${row.n}</td>
          <td class="num">${formatNumber(row.mean, 1)}</td>
          <td class="num">${formatNumber(row.std, 1)}</td>
          <td class="num">${formatNumber(row.median, 1)}</td>
          <td class="num">${formatNumber(row.iqr, 1)}</td>
          <td class="num">${row.spike_count || 0}</td>
          <td class="num">${row.drop_count || 0}</td>
          <td class="num">${row.anomaly_count || 0}</td>
        </tr>`;
    }).join("");
  }

  function filteredAnomalies() {
    if (!state.analysis) return [];
    const method = el.anomalyMethodFilter.value;
    const type = el.anomalyTypeFilter.value;
    return state.analysis.anomalies.filter((anomaly) => {
      if (method !== "all" && anomaly.method !== method) return false;
      if (type !== "all" && anomaly.type !== type) return false;
      return true;
    });
  }

  function renderAnomalies() {
    if (!state.analysis) return;
    const rows = filteredAnomalies();
    el.anomalyCount.textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
    if (!rows.length) {
      el.anomalyBody.innerHTML = `<tr><td colspan="8" class="empty-cell">No detections match the current filters.</td></tr>`;
      return;
    }
    el.anomalyBody.innerHTML = rows.map((row) => {
      const direction = row.type === "spike" ? "type-spike" : "type-drop";
      const devClass = row.deviation >= 0 ? "dev-positive" : "dev-negative";
      return `
        <tr>
          <td class="date-cell">${escapeHtml(friendlyDate(row.date))}</td>
          <td class="mine-name">${escapeHtml(row.mine)}</td>
          <td><span class="type-pill ${direction}">${row.type.toUpperCase()}</span></td>
          <td class="num">${formatNumber(row.observed, 1)}</td>
          <td class="num">${formatNumber(row.baseline, 1)}</td>
          <td class="num ${devClass}">${formatSigned(row.deviation, 1)}</td>
          <td class="num ${devClass}">${formatSigned(row.deviation_pct, 1)}%</td>
          <td><span class="method-pill">${escapeHtml(shortMethod(row.method))}</span></td>
        </tr>`;
    }).join("");
  }

  function renderMethodSummary() {
    const analysis = state.analysis;
    const counts = analysis.summary.method_counts;
    const parts = [
      `IQR <strong>${counts.iqr || 0}</strong>`,
      `Z <strong>${counts.zscore || 0}</strong>`,
      `MA <strong>${counts.moving || 0}</strong>`,
      `Grubbs <strong>${counts.grubbs || 0}</strong>`,
    ];
    el.methodSummary.innerHTML = `${parts.join(" &nbsp;/&nbsp; ")}<br><span>${analysis.summary.unique_points} unique spike/drop observations after de-duplication.</span>`;
  }

  function renderWarnings() {
    const warnings = state.analysis.warnings || [];
    el.warningsToggle.hidden = warnings.length === 0;
    el.warningsLabel.textContent = `Small-sample notes (${warnings.length})`;
    el.warningsBox.innerHTML = warnings.map((warning) => `<p>${escapeHtml(warning)}</p>`).join("");
    if (!warnings.length) {
      el.warningsBox.hidden = true;
      el.warningsToggle.querySelector("span:last-child").textContent = "+";
    }
  }

  function renderChartNote() {
    const analysis = state.analysis;
    if (!analysis) return;
    const selected = analysis.stats.find((row) => row.id === state.selectedSeries);
    if (el.chartType.value === "stacked") {
      el.chartNote.textContent = `All active mines are stacked. Markers show ${selected.label} detections at the top of that mine's segment; the dashed trend tracks total fleet output.`;
    } else {
      const unique = uniqueAnomalies(selected.id).length;
      el.chartNote.textContent = `${selected.label} / ${analysis.date_range.days} days / ${unique} unique anomaly point${unique === 1 ? "" : "s"} / degree ${el.trendDegree.value} trend.`;
    }
  }

  function renderChart() {
    if (!state.analysis || !state.dataset || !window.Chart) return;
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    const analysis = state.analysis;
    const dates = state.dataset.dates.slice(analysis.date_range.index_start, analysis.date_range.index_end);
    const includeYear = dates[0].slice(0, 4) !== dates[dates.length - 1].slice(0, 4) || dates.length > 365;
    const labels = dates.map((date) => chartDate(date, includeYear));
    const selected = analysis.stats.find((row) => row.id === state.selectedSeries) || analysis.stats[0];
    const degree = Number(el.trendDegree.value);
    const chartType = el.chartType.value;
    const showOutliers = el.showOutliers.checked;
    const activeMines = analysis.stats.filter((row) => row.type === "mine");
    const totalRow = analysis.stats.find((row) => row.id === "total");
    const datasets = [];

    if (chartType === "stacked") {
      activeMines.forEach((mine, index) => {
        datasets.push({
          label: mine.label,
          data: mine.values,
          type: "bar",
          stack: "mines",
          backgroundColor: hexToRgba(PALETTE[index % PALETTE.length], 0.72),
          borderColor: PALETTE[index % PALETTE.length],
          borderWidth: 0.5,
          order: 4,
        });
      });
      const trend = polynomialTrend(totalRow.values, degree);
      if (trend) {
        datasets.push({
          label: `Total trend (deg ${degree})`,
          data: trend,
          type: "line",
          borderColor: "#e2a63d",
          backgroundColor: "transparent",
          borderWidth: 1.8,
          borderDash: [6, 5],
          pointRadius: 0,
          fill: false,
          order: 1,
        });
      }
      if (showOutliers) {
        addOutlierDatasets(datasets, selected, activeMines, totalRow, true);
      }
    } else {
      const isBar = chartType === "bar";
      datasets.push({
        label: selected.label,
        data: selected.values,
        type: isBar ? "bar" : "line",
        borderColor: "#53b8af",
        backgroundColor: isBar ? "rgba(83,184,175,0.62)" : "rgba(83,184,175,0.055)",
        borderWidth: isBar ? 0.6 : 1.7,
        pointRadius: 0,
        pointHoverRadius: 3,
        tension: 0.12,
        fill: !isBar,
        order: 3,
      });
      const trend = polynomialTrend(selected.values, degree);
      if (trend) {
        datasets.push({
          label: `Degree ${degree} trend`,
          data: trend,
          type: "line",
          borderColor: "#e2a63d",
          backgroundColor: "transparent",
          borderWidth: 1.9,
          borderDash: [6, 5],
          pointRadius: 0,
          fill: false,
          order: 1,
        });
      }
      if (showOutliers) {
        addOutlierDatasets(datasets, selected, activeMines, totalRow, false);
      }
    }

    const stacked = chartType === "stacked";
    state.chart = new Chart(el.mainChart.getContext("2d"), {
      type: stacked ? "bar" : chartType,
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        animation: { duration: 260 },
        layout: { padding: { top: 4, right: 4 } },
        scales: {
          x: {
            stacked,
            grid: { color: "rgba(83,184,175,0.055)", drawTicks: false },
            border: { color: "#29474d" },
            ticks: {
              color: "#789093",
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 10,
              font: { size: 8.5 },
            },
            title: { display: true, text: "Date", color: "#789093", font: { size: 9, family: "monospace" } },
          },
          y: {
            stacked,
            beginAtZero: true,
            grid: { color: "rgba(83,184,175,0.07)", drawTicks: false },
            border: { color: "#29474d" },
            ticks: {
              color: "#789093",
              font: { size: 8.5 },
              callback: (value) => compactNumber(value),
            },
            title: { display: true, text: "tonnes / day", color: "#789093", font: { size: 9, family: "monospace" } },
          },
        },
        plugins: {
          legend: {
            position: "bottom",
            align: "start",
            labels: {
              color: "#8fa6a6",
              usePointStyle: true,
              boxWidth: 7,
              boxHeight: 7,
              padding: 10,
              font: { size: 8.5, family: "monospace" },
              filter: (item, chartData) => {
                const dataset = chartData.datasets[item.datasetIndex];
                return dataset && dataset.data && dataset.data.some((value) => value !== null);
              },
            },
          },
          tooltip: {
            backgroundColor: "#0a1b1e",
            borderColor: "#335158",
            borderWidth: 1,
            titleColor: "#f0c777",
            bodyColor: "#dbe7e3",
            footerColor: "#8fa6a6",
            padding: 10,
            titleFont: { family: "monospace", size: 9 },
            bodyFont: { family: "monospace", size: 9 },
            footerFont: { family: "monospace", size: 8 },
            callbacks: {
              title: (items) => {
                if (!items.length) return "";
                const index = items[0].dataIndex;
                return labels[index] ? fullDateFromLabel(dates[index]) : "";
              },
              label: (context) => {
                const dataset = context.dataset;
                if (dataset.kind === "outlier") {
                  const meta = dataset.meta && dataset.meta[context.dataIndex];
                  if (!meta) return "";
                  return `${meta.type === "spike" ? "Spike" : "Drop"} / ${meta.methods.join(", ")}`;
                }
                if (context.parsed.y === null || context.parsed.y === undefined) return "";
                return `${dataset.label}: ${formatNumber(context.parsed.y, 0)} t/day`;
              },
              afterBody: (items) => {
                if (!items.length) return [];
                const item = items.find((entry) => entry.dataset.kind === "outlier");
                if (!item) return [];
                const meta = item.dataset.meta[item.dataIndex];
                if (!meta) return [];
                return [
                  `Observed: ${formatNumber(meta.observed, 0)} t/day`,
                  `Baseline: ${formatNumber(meta.baseline, 0)} t/day`,
                  `Deviation: ${formatSigned(meta.deviation, 0)} t/day (${formatSigned(meta.deviation_pct, 1)}%)`,
                ];
              },
            },
          },
        },
      },
    });
  }

  function addOutlierDatasets(datasets, selected, activeMines, totalRow, stacked) {
    const grouped = uniqueAnomalies(selected.id);
    if (!grouped.length) return;
    const length = selected.values.length;
    const mineOrder = activeMines.findIndex((mine) => mine.id === selected.id);
    const spikeData = new Array(length).fill(null);
    const dropData = new Array(length).fill(null);
    const spikeMeta = {};
    const dropMeta = {};
    grouped.forEach((anomaly) => {
      let y = anomaly.observed;
      if (stacked) {
        if (selected.id === "total") {
          y = totalRow.values[anomaly.index];
        } else {
          y = 0;
          for (let i = 0; i <= mineOrder; i += 1) y += activeMines[i].values[anomaly.index] || 0;
        }
      }
      if (anomaly.type === "spike") {
        spikeData[anomaly.index] = y;
        spikeMeta[anomaly.index] = anomaly;
      } else {
        dropData[anomaly.index] = y;
        dropMeta[anomaly.index] = anomaly;
      }
    });
    if (spikeData.some((value) => value !== null)) {
      datasets.push({
        label: "Spikes",
        data: spikeData,
        type: "line",
        kind: "outlier",
        meta: spikeMeta,
        borderColor: "#e06a5f",
        backgroundColor: "#e06a5f",
        pointBackgroundColor: "#e06a5f",
        pointBorderColor: "#071214",
        pointBorderWidth: 1,
        pointRadius: 7,
        pointHoverRadius: 9,
        pointStyle: "triangle",
        showLine: false,
        spanGaps: false,
        order: 0,
      });
    }
    if (dropData.some((value) => value !== null)) {
      datasets.push({
        label: "Drops",
        data: dropData,
        type: "line",
        kind: "outlier",
        meta: dropMeta,
        borderColor: "#6aa9d2",
        backgroundColor: "#6aa9d2",
        pointBackgroundColor: "#6aa9d2",
        pointBorderColor: "#071214",
        pointBorderWidth: 1,
        pointRadius: 7,
        pointHoverRadius: 9,
        pointStyle: "triangle",
        pointRotation: 180,
        showLine: false,
        spanGaps: false,
        order: 0,
      });
    }
  }

  function uniqueAnomalies(seriesId) {
    const grouped = new Map();
    state.analysis.anomalies.forEach((anomaly) => {
      if (anomaly.series_id !== seriesId) return;
      const key = `${anomaly.index}|${anomaly.type}`;
      if (!grouped.has(key)) {
        grouped.set(key, { ...anomaly, methods: [shortMethod(anomaly.method)] });
      } else {
        const item = grouped.get(key);
        if (!item.methods.includes(shortMethod(anomaly.method))) item.methods.push(shortMethod(anomaly.method));
      }
    });
    return Array.from(grouped.values()).sort((a, b) => a.index - b.index);
  }

  function polynomialTrend(values, degree) {
    const n = values.length;
    if (!n || n < degree + 1) return null;
    const xs = values.map((_, index) => (n === 1 ? 0 : -1 + (2 * index) / (n - 1)));
    const matrix = Array.from({ length: degree + 1 }, () => new Array(degree + 2).fill(0));
    for (let row = 0; row <= degree; row += 1) {
      for (let col = 0; col <= degree; col += 1) {
        matrix[row][col] = xs.reduce((sum, x) => sum + Math.pow(x, row + col), 0);
      }
      matrix[row][degree + 1] = values.reduce((sum, y, index) => sum + y * Math.pow(xs[index], row), 0);
    }
    const coefficients = solveLinearSystem(matrix);
    if (!coefficients) return null;
    return xs.map((x) => coefficients.reduce((sum, coefficient, power) => sum + coefficient * Math.pow(x, power), 0));
  }

  function solveLinearSystem(matrix) {
    const n = matrix.length;
    for (let col = 0; col < n; col += 1) {
      let pivot = col;
      for (let row = col + 1; row < n; row += 1) {
        if (Math.abs(matrix[row][col]) > Math.abs(matrix[pivot][col])) pivot = row;
      }
      if (Math.abs(matrix[pivot][col]) < 1e-10) return null;
      [matrix[col], matrix[pivot]] = [matrix[pivot], matrix[col]];
      const divisor = matrix[col][col];
      for (let j = col; j <= n; j += 1) matrix[col][j] /= divisor;
      for (let row = 0; row < n; row += 1) {
        if (row === col) continue;
        const factor = matrix[row][col];
        for (let j = col; j <= n; j += 1) matrix[row][j] -= factor * matrix[col][j];
      }
    }
    return matrix.map((row) => row[n]);
  }

  async function generatePdf() {
    if (!state.analysis || !state.dataset) {
      showToast("Load the workbook before generating a report.", "error");
      return;
    }
    let methods;
    try {
      methods = gatherMethods();
    } catch (error) {
      showToast(error.message, "error");
      return;
    }
    const start = el.startDate.value;
    const end = el.endDate.value;
    if (!start || !end || start > end) {
      showToast("Choose a valid date range before generating the report.", "error");
      return;
    }
    el.pdfOverlay.hidden = false;
    el.pdfBtn.disabled = true;
    el.pdfBtn.classList.add("is-loading");
    el.pdfModalText.textContent = "Rendering charts, summary tables, anomaly logs and detailed findings...";
    try {
      const response = await api("/api/report", {
        method: "POST",
        body: JSON.stringify({
          start,
          end,
          methods,
          series_id: state.selectedSeries,
          chart_type: el.chartType.value,
          trend_degree: Number(el.trendDegree.value),
        }),
      });
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = filenameFromDisposition(disposition) || `weyland-anomaly-report-${start}-${end}.pdf`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 8000);
      showToast(`PDF report generated (${(blob.size / 1024 / 1024).toFixed(1)} MB). Download started.`);
    } catch (error) {
      showToast(humanizeError(error), "error");
    } finally {
      el.pdfOverlay.hidden = true;
      el.pdfBtn.disabled = false;
      el.pdfBtn.classList.remove("is-loading");
    }
  }

  function renderFatalState(message) {
    el.statsBody.innerHTML = `<tr><td colspan="9" class="empty-cell">${escapeHtml(message)}</td></tr>`;
    el.anomalyBody.innerHTML = `<tr><td colspan="8" class="empty-cell">Anomaly analysis unavailable until the workbook loads.</td></tr>`;
    el.chartNote.textContent = "No data available.";
    el.pdfBtn.disabled = true;
    ["kpiMean", "kpiMedian", "kpiStd", "kpiIqr", "kpiAnomalies", "kpiDays"].forEach((id) => { el[id].textContent = "-"; });
  }

  function setSourceState(stateName) {
    el.sourceDot.classList.remove("live", "error", "loading");
    if (stateName) el.sourceDot.classList.add(stateName);
  }

  function setBusy(isBusy) {
    state.loading = isBusy;
    el.loadingBar.hidden = !isBusy;
    el.refreshBtn.disabled = isBusy;
    el.refreshBtn.classList.toggle("is-loading", isBusy);
    if (isBusy) {
      el.refreshBtn.querySelector(".btn-label").textContent = "Refreshing";
    } else {
      el.refreshBtn.querySelector(".btn-label").textContent = "Refresh data";
    }
  }

  function setChartLoading(isLoading) {
    el.chartLoading.hidden = !isLoading;
  }

  function setError(message) {
    if (!message) {
      el.errorBanner.hidden = true;
      el.errorText.textContent = "";
      return;
    }
    el.errorBanner.hidden = false;
    el.errorText.textContent = message;
  }

  function showToast(message, type = "info") {
    el.toast.textContent = message;
    el.toast.classList.toggle("error", type === "error");
    el.toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => { el.toast.hidden = true; }, 5200);
  }

  function setActivePreset(button) {
    $$(".preset").forEach((item) => item.classList.toggle("active", item === button));
  }

  function formatNumber(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function formatSigned(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    const formatted = Math.abs(Number(value)).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return `${Number(value) >= 0 ? "+" : "-"}${formatted}`;
  }

  function compactNumber(value) {
    const number = Number(value);
    if (Math.abs(number) >= 1000000) return `${(number / 1000000).toFixed(1)}M`;
    if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(1)}k`;
    return String(Math.round(number));
  }

  function parseISO(value) {
    return new Date(`${value}T00:00:00Z`);
  }

  function toISO(date) {
    return date.toISOString().slice(0, 10);
  }

  function friendlyDate(value) {
    if (!value) return "-";
    const date = parseISO(value);
    return `${String(date.getUTCDate()).padStart(2, "0")} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  }

  function friendlyTimestamp(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const day = String(date.getUTCDate()).padStart(2, "0");
    const month = MONTHS[date.getUTCMonth()];
    const hours = String(date.getUTCHours()).padStart(2, "0");
    const minutes = String(date.getUTCMinutes()).padStart(2, "0");
    return `${day} ${month} ${date.getUTCFullYear()}, ${hours}:${minutes} UTC`;
  }

  function chartDate(value, includeYear = false) {
    const date = parseISO(value);
    const base = `${String(date.getUTCDate()).padStart(2, "0")} ${MONTHS[date.getUTCMonth()]}`;
    return includeYear ? `${base} '${String(date.getUTCFullYear()).slice(-2)}` : base;
  }

  function fullDateFromLabel(value) {
    const date = parseISO(value);
    return `${String(date.getUTCDate()).padStart(2, "0")} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  }

  function shortMethod(method) {
    return { iqr: "IQR", zscore: "Z-score", moving: "MA", grubbs: "Grubbs" }[method] || method;
  }

  function hexToRgba(hex, alpha) {
    const value = hex.replace("#", "");
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function filenameFromDisposition(disposition) {
    const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    if (utf8) return decodeURIComponent(utf8[1]);
    const plain = /filename="?([^";]+)"?/i.exec(disposition);
    return plain ? plain[1] : null;
  }

  function humanizeError(error) {
    const message = String((error && error.message) || error || "Unknown error");
    if (/failed to fetch|networkerror|load failed|network request failed/i.test(message)) {
      return "Could not reach the dashboard server. Check that the app is running, then retry.";
    }
    return message;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
})();
