/**
 * dashboard.js (v4)
 * ================
 * Fixed: hover highlight, scroll zoom, no chart titles.
 */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

const sidebar = $('#sidebar');
const icons = $$('.sb-icon');
const panels = $$('.sb-panel');

const elFile = $('#data-file');
const elTsCode = $('#ts-code');
const elStart = $('#start-date');
const elEnd = $('#end-date');
const elBtnFetch = $('#btn-fetch');
const elFetchStatus = $('#fetch-status');
const elBtnRefresh = $('#btn-refresh-files');

const elIndCards = $$('.ind-card');
const elIndParams = $('#ind-params');
const elBtnApply = $('#btn-apply');
const elComputeStatus = $('#compute-status');

const elChartEmpty = $('#chart-empty');
const elChartContainer = $('#chart-container');
const elSignalContent = $('#signal-content');

// Backtest elements
const elBtFile = $('#bt-file');
const elBtStart = $('#bt-start-date');
const elBtEnd = $('#bt-end-date');
const elBtShort = $('#bt-short-sma');
const elBtLong = $('#bt-long-sma');
const elBtCapital = $('#bt-capital');
const elBtCommission = $('#bt-commission');
const elBtRun = $('#btn-bt-run');
const elBtReset = $('#btn-bt-reset');
const elBtStatus = $('#bt-status');
const elBacktestContainer = $('#backtest-container');

// Turtle elements
const elTuFile = $('#tu-file');
const elTuStart = $('#tu-start-date');
const elTuEnd = $('#tu-end-date');
const elTuEntryPeriod = $('#tu-entry-period');
const elTuExitPeriod = $('#tu-exit-period');
const elTuAtrPeriod = $('#tu-atr-period');
const elTuAddStep = $('#tu-add-step');
const elTuCapital = $('#tu-capital');
const elTuCommission = $('#tu-commission');
const elTuRun = $('#btn-tu-run');
const elTuReset = $('#btn-tu-reset');
const elTuStatus = $('#tu-status');
const elTurtleContainer = $('#turtle-container');

// ═══════════════════════════ State ═══════════════════════════

let activePanel = 'data';
let activeInd = 'price_ma';
let indicatorData = null;
let lastParams = null;
let backtestData = null;
let turtleData = null;
let fileListCache = [];  // cached file list for backtest date validation

// ═══════════════════════════ Chart Config ═══════════════════

const BG = '#f3f4f6';
const GRID_COLOR = 'rgba(0,0,0,0.04)';
const AXIS_LINE = 'rgba(0,0,0,0.08)';

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  scrollZoom: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
  toImageButtonOptions: { format: 'png', filename: 'quant_chart', scale: 2 },
};

function chartLayout(yTitle = '', extraY = {}) {
  return {
    paper_bgcolor: BG,
    plot_bgcolor: BG,
    margin: { l: 62, r: 24, t: 8, b: 48 },
    hovermode: 'x unified',
    hoverlabel: { bgcolor: '#ffffff', font: { color: '#1f2937', size: 11 }, bordercolor: '#e5e7eb' },
    showlegend: true,
    legend: { orientation: 'h', y: 1.02, x: 0, font: { size: 10, color: '#6b7280' },
              bgcolor: 'transparent' },
    xaxis: {
      showgrid: true, gridcolor: GRID_COLOR, gridwidth: 1,
      zeroline: false, showline: true, linecolor: AXIS_LINE, linewidth: 1,
      tickfont: { size: 9, color: '#9ca3af' },
    },
    yaxis: {
      title: yTitle ? { text: yTitle, font: { size: 10, color: '#6b7280' }, standoff: 8 } : { text: '' },
      showgrid: true, gridcolor: GRID_COLOR, gridwidth: 1,
      zeroline: false, showline: true, linecolor: AXIS_LINE, linewidth: 1,
      tickfont: { size: 9, color: '#9ca3af' },
      ...extraY,
    },
  };
}


// ═══════════════════════════ Hover Highlight ═══════════════
//  Target the inner Plotly graph div (NOT #chart-container itself)
//  to dim all traces except the one being hovered.

function getGraphDiv() {
  return document.querySelector('#chart-container .js-plotly-plot')
      || document.querySelector('#chart-container .plotly');
}

function onHover(ev) {
  const pts = ev.points || [];
  if (!pts.length) return;
  const graphDiv = getGraphDiv();
  if (!graphDiv || !graphDiv.data) return;

  const hoveredCurve = pts[0].curveNumber;
  const n = graphDiv.data.length;

  // Pluck current widths from trace data so we can restore them
  const widths = graphDiv.data.map(t => (t.line && t.line.width) ? t.line.width : 0);

  const updates = [];
  for (let i = 0; i < n; i++) {
    const t = graphDiv.data[i];
    if (t.type === 'bar') continue;
    if (i === hoveredCurve) {
      updates.push({ opacity: 1, 'line.width': (widths[i] || 1) * 2.0 });
    } else {
      updates.push({ opacity: 0.10, 'line.width': widths[i] || 0.5 });
    }
  }
  Plotly.restyle(graphDiv, updates);
}

function onUnhover() {
  const graphDiv = getGraphDiv();
  if (!graphDiv || !graphDiv.data) return;
  const n = graphDiv.data.length;
  const resets = [];
  for (let i = 0; i < n; i++) {
    const t = graphDiv.data[i];
    if (t.type === 'bar') continue;
    const w = (t.line && t.line.width) ? t.line.width : null;
    resets.push({ opacity: 1, 'line.width': w });
  }
  Plotly.restyle(graphDiv, resets);
}

let _hoverWired = false;

function enableHoverHighlight() {
  const gd = getGraphDiv();
  if (!gd) return;
  if (!_hoverWired) {
    gd.on('plotly_hover', onHover);
    gd.on('plotly_unhover', onUnhover);
    _hoverWired = true;
  }
}


// ═══════════════════════════ Sidebar ═══════════════════════

function openPanel(name) {
  if (activePanel === name) {
    activePanel = null;
    sidebar.classList.remove('expanded');
    icons.forEach(ic => ic.classList.remove('active'));
    panels.forEach(p => p.classList.remove('visible'));
  } else {
    activePanel = name;
    sidebar.classList.add('expanded');
    icons.forEach(ic => ic.classList.toggle('active', ic.dataset.panel === name));
    panels.forEach(p => p.classList.toggle('visible', p.id === `panel-${name}`));
  }

  // Hide all result containers first
  elBacktestContainer.style.display = 'none';
  elTurtleContainer.style.display = 'none';
  elMlContainer.style.display = 'none';
  // Also hide any injected compare table
  const compTable = $('#ml-compare-table-div');
  if (compTable) compTable.innerHTML = '';

  // View switching
  if (activePanel === 'backtest') {
    elChartContainer.style.display = 'none';
    elChartEmpty.style.display = 'none';
    elBacktestContainer.style.display = backtestData ? 'flex' : 'none';
    if (!backtestData) {
      elChartEmpty.style.display = 'flex';
      elChartEmpty.querySelector('h2').textContent = '双均线回测';
      elChartEmpty.querySelector('p').textContent = '设置参数 → 运行回测 → 查看结果';
    }
    if (backtestData) renderBacktest();
  } else if (activePanel === 'turtle') {
    elChartContainer.style.display = 'none';
    elChartEmpty.style.display = 'none';
    elTurtleContainer.style.display = turtleData ? 'flex' : 'none';
    if (!turtleData) {
      elChartEmpty.style.display = 'flex';
      elChartEmpty.querySelector('h2').textContent = '海龟交易法则';
      elChartEmpty.querySelector('p').textContent = '设置参数 → 运行回测 → 查看结果';
    }
    if (turtleData) renderTurtle();
  } else if (activePanel === 'ml') {
    elChartContainer.style.display = 'none';
    elChartEmpty.style.display = 'none';
    if (mlData) {
      elMlContainer.style.display = 'flex';
      renderML();
    } else if (mlCompareData) {
      elMlContainer.style.display = 'flex';
      renderMLCompare();
    } else {
      elChartEmpty.style.display = 'flex';
      elChartEmpty.querySelector('h2').textContent = '🤖 ML 量化分析';
      elChartEmpty.querySelector('p').textContent = '选择数据 → 配置模型 → 运行分析 → 查看结果';
    }
  } else if (activePanel && indicatorData) {
    elChartEmpty.style.display = 'none';
    elChartContainer.style.display = 'block';
    requestAnimationFrame(() => renderActiveChart());
  } else if (activePanel && !indicatorData) {
    elChartContainer.style.display = 'none';
    elChartEmpty.style.display = 'flex';
    elChartEmpty.querySelector('h2').textContent = 'Quant Dashboard';
    elChartEmpty.querySelector('p').textContent = '选择数据源 → 选择指标 → 查看图表';
  } else {
    // Collapsed
    if (indicatorData) {
      elChartEmpty.style.display = 'none';
      elChartContainer.style.display = 'block';
    } else {
      elChartContainer.style.display = 'none';
      elChartEmpty.style.display = 'flex';
    }
  }
}

icons.forEach(icon => icon.addEventListener('click', () => openPanel(icon.dataset.panel)));


// ═══════════════════════════ Indicator Selector ═══════════

const IND_PARAMS_HTML = {
  price_ma: `
    <div class="field"><label>MA 周期（可多选）</label>
      <div class="ma-toggles" id="ma-toggles">
        <label><input type="checkbox" value="5" checked> MA5</label>
        <label><input type="checkbox" value="10" checked> MA10</label>
        <label><input type="checkbox" value="20" checked> MA20</label>
        <label><input type="checkbox" value="60" checked> MA60</label>
        <label><input type="checkbox" value="120"> MA120</label>
        <label><input type="checkbox" value="250"> MA250</label>
      </div></div>`,
  rsi: `
    <div class="field"><label>周期 N = <span id="rsi-val">14</span></label>
      <input type="range" id="rsi-period" min="2" max="50" value="14" step="1"></div>`,
  macd: `
    <div class="param-row">
      <div class="field"><label>快线 P1</label><input type="number" id="macd-fast" value="12" min="2" max="50"></div>
      <div class="field"><label>慢线 P2</label><input type="number" id="macd-slow" value="26" min="5" max="100"></div>
      <div class="field"><label>信号线 P3</label><input type="number" id="macd-signal" value="9" min="2" max="50"></div>
    </div>`,
  bb: `
    <div class="param-row">
      <div class="field"><label>周期 N</label><input type="number" id="bb-period" value="20" min="5" max="100"></div>
      <div class="field"><label>带宽 Kσ</label><input type="number" id="bb-std" value="2.0" min="0.5" max="5.0" step="0.5"></div>
    </div>`,
};

function selectIndicator(ind) {
  activeInd = ind;
  elIndCards.forEach(c => c.classList.toggle('active', c.dataset.ind === ind));
  elIndParams.innerHTML = IND_PARAMS_HTML[ind] || '';
  elIndParams.classList.add('visible');

  const rsiSlider = $('#rsi-period');
  if (rsiSlider) {
    rsiSlider.addEventListener('input', () => {
      const span = $('#rsi-val');
      if (span) span.textContent = rsiSlider.value;
    });
  }
  if (indicatorData) renderActiveChart();
}

elIndCards.forEach(card => card.addEventListener('click', () => selectIndicator(card.dataset.ind)));


// ═══════════════════════════ Params ════════════════════════

function getParams() {
  const base = { file: elFile.value };
  const cbs = $$('#ma-toggles input:checked');
  if (cbs.length) base.ma_periods = Array.from(cbs).map(c => parseInt(c.value)).sort((a,b)=>a-b);
  const rsiEl = $('#rsi-period');
  if (rsiEl) base.rsi_period = parseInt(rsiEl.value);
  const mf = $('#macd-fast');
  if (mf) { base.macd_fast = parseInt(mf.value); base.macd_slow = parseInt($('#macd-slow').value); base.macd_signal = parseInt($('#macd-signal').value); }
  const bp = $('#bb-period');
  if (bp) { base.bb_period = parseInt(bp.value); base.bb_std = parseFloat($('#bb-std').value); }
  return base;
}


// ═══════════════════════════ API ══════════════════════════

async function loadFiles() {
  try {
    const resp = await fetch('/api/files');
    const files = await resp.json();
    fileListCache = files;
    const opts = files.map(f =>
      `<option value="${f.name}">${f.name} ${f.ts_code?'('+f.ts_code+')':''} — ${f.rows||'?'}行</option>`
    ).join('');
    elFile.innerHTML = opts;
    elBtFile.innerHTML = opts;
    elTuFile.innerHTML = opts;
    if (files.length) elFetchStatus.textContent = `共 ${files.length} 个文件可用`;
    updateBtDatePlaceholders();
    updateTuDatePlaceholders();
  } catch(e) { elFetchStatus.textContent = '加载文件列表失败'; }
}

async function fetchData() {
  const ts_code = elTsCode.value.trim();
  const start_date = elStart.value.trim();
  const end_date = elEnd.value.trim();
  if (!ts_code || !start_date || !end_date) { elFetchStatus.textContent = '请填写完整信息'; return; }
  elBtnFetch.disabled = true;
  elFetchStatus.textContent = '⏳ 获取中…';
  try {
    const resp = await fetch('/api/fetch', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ ts_code, start_date, end_date }),
    });
    const r = await resp.json();
    elFetchStatus.textContent = r.ok ? `✅ ${r.rows} 条 | ${r.date_min}–${r.date_max}` : `❌ ${r.error}`;
    if (r.ok) { await loadFiles(); elFile.value = r.filename; }
  } catch(e) { elFetchStatus.textContent = `❌ ${e.message}`; }
  finally { elBtnFetch.disabled = false; }
}

async function computeAndRender() {
  const params = getParams();
  if (!params.file) { elComputeStatus.textContent = '请先选择数据文件'; return; }
  params.ma_periods = params.ma_periods || [5,10,20,60,120];
  elBtnApply.disabled = true;
  elComputeStatus.textContent = '⏳ 计算中…';
  try {
    const resp = await fetch('/api/indicators', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(params),
    });
    const r = await resp.json();
    if (r.ok) {
      indicatorData = r;
      lastParams = params;
      _hoverWired = false;  // reset → re-bind after new render
      renderActiveChart();
      renderSignal(r.signal, params);
      elComputeStatus.textContent = `✅ ${r.n_records} 条 — ${r.data.dates[r.data.dates.length-1]}`;
    } else { elComputeStatus.textContent = `❌ ${r.error}`; }
  } catch(e) { elComputeStatus.textContent = `❌ ${e.message}`; }
  finally { elBtnApply.disabled = false; }
}


// ═══════════════════════════ Chart Builders ════════════════

function trim(dates, values) {
  let s = 0;
  while (s < values.length && (values[s] === 0 || values[s] === null)) s++;
  return [dates.slice(s), values.slice(s)];
}

const MA_SWATCH = ['#f59e0b','#10b981','#ef4444','#8b5cf6','#64748b','#06b6d4'];

function renderActiveChart() {
  if (!indicatorData) return;

  elChartEmpty.style.display = 'none';
  elChartContainer.style.display = 'block';

  let traces, layout;
  const d = indicatorData.data, dates = d.dates;

  if (activeInd === 'price_ma') {
    const maKeys = Object.keys(d.ma).sort((a,b) => parseInt(a.slice(2)) - parseInt(b.slice(2)));
    const [cX, cY] = trim(dates, d.close);
    traces = [{
      x: cX, y: cY, type:'scatter', mode:'lines',
      line: { color: '#1e293b', width: 1.5 },
      name: 'Close', hovertemplate: '%{y:.2f}<extra>Close</extra>',
    }];
    maKeys.forEach((k, i) => {
      const [mx, my] = trim(dates, d.ma[k]);
      traces.push({
        x: mx, y: my, type:'scatter', mode:'lines',
        line: { color: MA_SWATCH[i % MA_SWATCH.length], width: parseInt(k.slice(2)) > 60 ? 1.3 : 0.8 },
        name: k, hovertemplate: '%{y:.2f}<extra>'+k+'</extra>',
      });
    });
    layout = chartLayout('CNY');

  } else if (activeInd === 'rsi') {
    const [rX, rY] = trim(dates, d.rsi);
    traces = [
      { x: rX, y: rY, type:'scatter', mode:'lines',
        line: { color: '#7c3aed', width: 1.4 }, name: `RSI(${d.rsi_period})`,
        hovertemplate: 'RSI: %{y:.1f}<extra></extra>',
        fill: 'tozeroy', fillcolor: 'rgba(124,58,237,0.04)' },
      { x: [dates[0],dates[dates.length-1]], y: [70,70], type:'scatter', mode:'lines',
        line: { color: '#f87171', width: 0.7, dash: 'dash' }, name: '超买 70', hoverinfo: 'skip' },
      { x: [dates[0],dates[dates.length-1]], y: [30,30], type:'scatter', mode:'lines',
        line: { color: '#4ade80', width: 0.7, dash: 'dash' }, name: '超卖 30', hoverinfo: 'skip' },
      { x: [dates[0],dates[dates.length-1]], y: [50,50], type:'scatter', mode:'lines',
        line: { color: 'rgba(0,0,0,0.06)', width: 0.5 }, name: '50', hoverinfo: 'skip', showlegend: false },
    ];
    layout = chartLayout('', { range: [0,100], tickvals: [0,30,50,70,100] });

  } else if (activeInd === 'macd') {
    const [hX, hY] = trim(dates, d.macd_hist);
    const colors = hY.map(v => v >= 0 ? 'rgba(239,68,68,0.45)' : 'rgba(16,185,129,0.45)');
    traces = [
      { x: hX, y: hY, type:'bar', marker: { color: colors }, name: 'Histogram',
        hovertemplate: '%{y:.2f}<extra>Hist</extra>' },
      { x: dates, y: d.dif, type:'scatter', mode:'lines',
        line: { color: '#3b82f6', width: 1.1 }, name: 'DIF',
        hovertemplate: 'DIF: %{y:.2f}<extra></extra>' },
      { x: dates, y: d.dea, type:'scatter', mode:'lines',
        line: { color: '#f97316', width: 1.1 }, name: 'DEA',
        hovertemplate: 'DEA: %{y:.2f}<extra></extra>' },
      { x: [dates[0],dates[dates.length-1]], y: [0,0], type:'scatter', mode:'lines',
        line: { color: 'rgba(0,0,0,0.05)', width: 0.5 }, name: '零轴', hoverinfo: 'skip', showlegend: false },
    ];
    layout = chartLayout();

  } else if (activeInd === 'bb') {
    const [bbX, bbU] = trim(dates, d.bb_upper);
    const [_, bbL] = trim(dates, d.bb_lower);
    traces = [
      { x: [...bbX, ...bbX.slice().reverse()], y: [...bbU, ...bbL.slice().reverse()],
        fill: 'toself', fillcolor: 'rgba(99,102,241,0.06)', line: { width: 0 },
        name: 'Band', hoverinfo: 'skip', showlegend: true },
    ];
    for (const [key, dash, w, label] of [['bb_upper','dash',0.6,'Upper'],['bb_mid','dot',0.8,'Mid'],['bb_lower','dash',0.6,'Lower']]) {
      const [dx, dy] = trim(dates, d[key]);
      traces.push({ x: dx, y: dy, type:'scatter', mode:'lines',
        line: { color: '#818cf8', width: w, dash }, name: `BB ${label}`,
        hovertemplate: '%{y:.2f}<extra>BB '+label+'</extra>' });
    }
    const [cX, cY] = trim(dates, d.close);
    traces.push({ x: cX, y: cY, type:'scatter', mode:'lines',
      line: { color: '#1e293b', width: 1.5 }, name: 'Close',
      hovertemplate: '%{y:.2f}<extra>Close</extra>' });
    layout = chartLayout('CNY');
  }

  Plotly.react('chart-container', traces, layout, PLOTLY_CONFIG).then(() => {
    enableHoverHighlight();
  });
}


// ═══════════════════════════ Signal Panel ═════════════════

function renderSignal(sig, params) {
  const p = params || lastParams || {};
  elSignalContent.innerHTML = `
    <div class="signal-row"><span class="sig-label">日期</span><span class="sig-value">${sig.date}</span></div>
    <div class="signal-row"><span class="sig-label">收盘价</span><span class="sig-value">¥${sig.close}</span></div>
    <hr style="border-color:rgba(255,255,255,.05);margin:4px 0;">
    <div class="signal-row"><span class="sig-label">RSI(${p.rsi_period||14})</span><span class="sig-value ${sig.rsi>70?'bullish':sig.rsi<30?'bearish':'neutral'}">${sig.rsi_label} (${sig.rsi})</span></div>
    <div class="signal-row"><span class="sig-label">MACD</span><span class="sig-value ${sig.macd_label.includes('金叉')?'bullish':'bearish'}">${sig.macd_label}</span></div>
    <div class="signal-row"><span class="sig-label">　DIF / DEA / Hist</span><span class="sig-value">${sig.macd_dif} / ${sig.macd_dea} / ${sig.macd_hist}</span></div>
    <hr style="border-color:rgba(255,255,255,.05);margin:4px 0;">
    <div class="signal-row"><span class="sig-label">布林带</span><span class="sig-value">${sig.bb_label} (${sig.bb_pos}%)</span></div>
    <div class="signal-row"><span class="sig-label">　Upper / Lower</span><span class="sig-value">¥${sig.bb_upper} / ¥${sig.bb_lower}</span></div>
  `;
}


// ═══════════════════════════ Backtest ═════════════════════

function getBtFileMeta() {
  const name = elBtFile.value;
  return fileListCache.find(f => f.name === name) || null;
}

function updateBtDatePlaceholders() {
  const meta = getBtFileMeta();
  if (meta && meta.date_min && meta.date_max) {
    elBtStart.placeholder = meta.date_min;
    elBtEnd.placeholder = meta.date_max;
  }
}

function onBtFileChange() {
  updateBtDatePlaceholders();
}

function resetBtParams() {
  elBtShort.value = 5;
  elBtLong.value = 20;
  elBtCapital.value = 100000;
  elBtCommission.checked = false;
  elBtStart.value = '';
  elBtEnd.value = '';
  updateBtDatePlaceholders();
  elBtStatus.textContent = '';
}

async function runBacktest() {
  const file = elBtFile.value;
  if (!file) { elBtStatus.textContent = '❌ 请选择数据文件'; return; }

  const shortSma = parseInt(elBtShort.value);
  const longSma = parseInt(elBtLong.value);
  if (shortSma >= longSma) {
    elBtStatus.textContent = '❌ 短周期必须小于长周期';
    return;
  }
  if (shortSma < 2) { elBtStatus.textContent = '❌ 短周期 SMA 最小为 2'; return; }

  const capital = parseFloat(elBtCapital.value);
  if (capital <= 0) { elBtStatus.textContent = '❌ 初始资金必须大于 0'; return; }

  const startDate = elBtStart.value.trim() || null;
  const endDate = elBtEnd.value.trim() || null;

  const params = {
    file,
    short_sma: shortSma,
    long_sma: longSma,
    commission_enabled: elBtCommission.checked,
    initial_capital: capital,
    start_date: startDate,
    end_date: endDate,
  };

  elBtRun.disabled = true;
  elBtStatus.textContent = '⏳ 回测计算中…';
  try {
    const resp = await fetch('/api/backtest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    const r = await resp.json();
    if (r.ok) {
      backtestData = r;
      renderBacktest();
      elBtStatus.textContent = `✅ 回测完成 — ${r.data.dates.length} 个交易日`;
    } else {
      elBtStatus.textContent = `❌ ${r.error}`;
    }
  } catch (e) {
    elBtStatus.textContent = `❌ ${e.message}`;
  } finally {
    elBtRun.disabled = false;
  }
}

function renderBacktest() {
  if (!backtestData) return;
  const d = backtestData.data;
  const m = backtestData.metrics;

  // Show backtest container
  elChartEmpty.style.display = 'none';
  elChartContainer.style.display = 'none';
  elBacktestContainer.style.display = 'flex';
  _hoverWired = false;

  // ── KPI Cards ──────────────────────────────────────────
  renderBacktestKPIs(m);

  // ── Middle: Dual MA + Signals Chart ────────────────────
  renderMAChart(d, backtestData.params);

  // ── Bottom-Left: Drawdown Chart ────────────────────────
  renderDrawdownChart(d);

  // ── Bottom-Right: Strategy vs Benchmark ────────────────
  renderComparisonChart(d, m);
}

function renderBacktestKPIs(m) {
  // 年化收益率
  const ann = m.annual_return;
  let annCls = 'neutral', annText = 'N/A';
  if (ann !== null && ann !== undefined) {
    annText = (ann >= 0 ? '+' : '') + ann.toFixed(2) + '%';
    annCls = ann > 0 ? 'positive' : (ann < 0 ? 'negative' : 'neutral');
  }
  $('#kpi-annual').className = 'bt-kpi-card ' + annCls;
  $('#kpi-annual').innerHTML = `
    <span class="bt-kpi-value">${annText}</span>
    <span class="bt-kpi-label">年化收益率</span>
    <span class="bt-kpi-sub">总收益: ${m.total_return >= 0 ? '+' : ''}${m.total_return.toFixed(2)}%</span>`;

  // 夏普比率
  const sh = m.sharpe_ratio;
  let shCls = 'neutral', shText = 'N/A';
  if (sh !== null && sh !== undefined) {
    shText = sh.toFixed(2);
    shCls = sh >= 2 ? 'positive' : (sh >= 1 ? 'warning' : (sh < 0 ? 'negative' : 'neutral'));
  }
  $('#kpi-sharpe').className = 'bt-kpi-card ' + shCls;
  $('#kpi-sharpe').innerHTML = `
    <span class="bt-kpi-value">${shText}</span>
    <span class="bt-kpi-label">夏普比率</span>
    <span class="bt-kpi-sub">基准收益: ${m.benchmark_return >= 0 ? '+' : ''}${m.benchmark_return.toFixed(2)}%</span>`;

  // 最大回撤
  const mdd = m.max_drawdown;
  let mddCls = 'neutral', mddText = 'N/A';
  if (mdd !== null && mdd !== undefined) {
    mddText = mdd.toFixed(2) + '%';
    mddCls = mdd > -10 ? 'positive' : (mdd > -20 ? 'warning' : 'negative');
  }
  $('#kpi-drawdown').className = 'bt-kpi-card ' + mddCls;
  $('#kpi-drawdown').innerHTML = `
    <span class="bt-kpi-value">${mddText}</span>
    <span class="bt-kpi-label">最大回撤</span>
    <span class="bt-kpi-sub">${m.max_drawdown_date || ''}</span>`;

  // 胜率
  const wr = m.win_rate;
  let wrCls = 'neutral', wrText = 'N/A';
  if (wr !== null && wr !== undefined) {
    wrText = wr.toFixed(1) + '%';
    wrCls = wr >= 60 ? 'positive' : (wr >= 40 ? 'warning' : (wr < 30 ? 'negative' : 'neutral'));
  }
  const plText = m.profit_loss_ratio !== null && m.profit_loss_ratio !== undefined
    ? '盈亏比 ' + m.profit_loss_ratio.toFixed(2) : '';
  $('#kpi-winrate').className = 'bt-kpi-card ' + wrCls;
  $('#kpi-winrate').innerHTML = `
    <span class="bt-kpi-value">${wrText}</span>
    <span class="bt-kpi-label">胜率</span>
    <span class="bt-kpi-sub">${m.trade_count}笔交易${plText ? ' | ' + plText : ''}</span>`;
}

function renderMAChart(d, params) {
  const traces = [
    {
      x: d.dates, y: d.close, type: 'scatter', mode: 'lines',
      line: { color: '#64748b', width: 1.2 },
      name: 'Close', hovertemplate: '收盘: %{y:.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.short_ma, type: 'scatter', mode: 'lines',
      line: { color: '#f59e0b', width: 1.0 },
      name: `SMA(${params.short_sma})`, hovertemplate: '短均: %{y:.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.long_ma, type: 'scatter', mode: 'lines',
      line: { color: '#3b82f6', width: 1.0 },
      name: `SMA(${params.long_sma})`, hovertemplate: '长均: %{y:.2f}<extra></extra>',
    },
  ];

  // Buy markers — red upward triangles
  if (d.buy_signals && d.buy_signals.length > 0) {
    traces.push({
      x: d.buy_signals.map(s => s.date), y: d.buy_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'triangle-up', color: '#ef4444', size: 12, line: { width: 0 } },
      name: '买入 (金叉)',
      hovertemplate: '<b>买入</b><br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>',
    });
  }

  // Sell markers — green downward triangles
  if (d.sell_signals && d.sell_signals.length > 0) {
    traces.push({
      x: d.sell_signals.map(s => s.date), y: d.sell_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'triangle-down', color: '#10b981', size: 12, line: { width: 0 } },
      name: '卖出 (死叉)',
      hovertemplate: '<b>卖出</b><br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>',
    });
  }

  const layout = {
    ...chartLayout('价格 (CNY)'),
    title: { text: '双均线交叉信号', font: { size: 13, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 60, r: 24, t: 36, b: 40 },
  };

  Plotly.react('bt-chart-ma', traces, layout, PLOTLY_CONFIG);
}

function renderDrawdownChart(d) {
  const dd = d.drawdown;
  const traces = [
    {
      x: d.dates, y: dd, type: 'scatter', mode: 'none',
      fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.12)',
      name: '回撤', hoverinfo: 'skip', showlegend: false,
    },
    {
      x: d.dates, y: dd, type: 'scatter', mode: 'lines',
      line: { color: '#ef4444', width: 1.1 },
      name: '回撤 %', hovertemplate: '回撤: %{y:.2f}%<extra></extra>',
    },
    {
      x: [d.dates[0], d.dates[d.dates.length - 1]], y: [0, 0],
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.08)', width: 0.5 },
      name: '0%', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('回撤 (%)'),
    title: { text: '回撤曲线', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 55, r: 18, t: 36, b: 40 },
    yaxis: {
      ...chartLayout().yaxis,
      title: { text: '回撤 (%)', font: { size: 10, color: '#6b7280' }, standoff: 6 },
    },
  };

  Plotly.react('bt-chart-dd', traces, layout, PLOTLY_CONFIG);
}

function renderComparisonChart(d, m) {
  const traces = [
    {
      x: d.dates, y: d.portfolio_value, type: 'scatter', mode: 'lines',
      line: { color: '#dc2626', width: 1.6 },
      name: '双均线策略',
      hovertemplate: '策略: ¥%{y:,.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.benchmark_value, type: 'scatter', mode: 'lines',
      line: { color: '#9ca3af', width: 1.0, dash: 'dash' },
      name: '买入持有 (基准)',
      hovertemplate: '基准: ¥%{y:,.2f}<extra></extra>',
    },
    {
      x: [d.dates[0], d.dates[d.dates.length - 1]],
      y: [m.initial_capital, m.initial_capital],
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.06)', width: 0.5 },
      name: '初始资金', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('组合净值 (CNY)'),
    title: { text: '策略 vs 基准', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 65, r: 18, t: 36, b: 40 },
    yaxis: {
      ...chartLayout().yaxis,
      title: { text: '净值 (CNY)', font: { size: 10, color: '#6b7280' }, standoff: 8 },
    },
  };

  Plotly.react('bt-chart-cmp', traces, layout, PLOTLY_CONFIG);
}


// ═══════════════════════════ Turtle ═════════════════════

function getTuFileMeta() {
  const name = elTuFile.value;
  return fileListCache.find(f => f.name === name) || null;
}

function updateTuDatePlaceholders() {
  const meta = getTuFileMeta();
  if (meta && meta.date_min && meta.date_max) {
    elTuStart.placeholder = meta.date_min;
    elTuEnd.placeholder = meta.date_max;
  }
}

function onTuFileChange() {
  updateTuDatePlaceholders();
}

function resetTurtleParams() {
  elTuEntryPeriod.value = 20;
  elTuExitPeriod.value = 10;
  elTuAtrPeriod.value = 14;
  elTuAddStep.value = 0.5;
  elTuCapital.value = 100000;
  elTuCommission.checked = false;
  elTuStart.value = '';
  elTuEnd.value = '';
  updateTuDatePlaceholders();
  elTuStatus.textContent = '';
}

async function runTurtle() {
  const file = elTuFile.value;
  if (!file) { elTuStatus.textContent = '❌ 请选择数据文件'; return; }

  const entryPeriod = parseInt(elTuEntryPeriod.value);
  const exitPeriod = parseInt(elTuExitPeriod.value);
  const atrPeriod = parseInt(elTuAtrPeriod.value);
  const addStep = parseFloat(elTuAddStep.value);

  if (entryPeriod < 2) { elTuStatus.textContent = '❌ 入场通道周期最小为 2'; return; }
  if (exitPeriod < 2) { elTuStatus.textContent = '❌ 出场通道周期最小为 2'; return; }
  if (atrPeriod < 2) { elTuStatus.textContent = '❌ ATR 周期最小为 2'; return; }
  if (addStep <= 0) { elTuStatus.textContent = '❌ 加仓步长必须大于 0'; return; }

  const capital = parseFloat(elTuCapital.value);
  if (capital <= 0) { elTuStatus.textContent = '❌ 初始资金必须大于 0'; return; }

  const params = {
    file,
    entry_period: entryPeriod,
    exit_period: exitPeriod,
    atr_period: atrPeriod,
    add_step: addStep,
    commission_enabled: elTuCommission.checked,
    initial_capital: capital,
    start_date: elTuStart.value.trim() || null,
    end_date: elTuEnd.value.trim() || null,
  };

  elTuRun.disabled = true;
  elTuStatus.textContent = '⏳ 回测计算中…';
  try {
    const resp = await fetch('/api/turtle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    const r = await resp.json();
    if (r.ok) {
      turtleData = r;
      renderTurtle();
      elTuStatus.textContent = `✅ 回测完成 — ${r.data.dates.length} 个交易日`;
    } else {
      elTuStatus.textContent = `❌ ${r.error}`;
    }
  } catch (e) {
    elTuStatus.textContent = `❌ ${e.message}`;
  } finally {
    elTuRun.disabled = false;
  }
}

function renderTurtle() {
  if (!turtleData) return;
  const d = turtleData.data;
  const m = turtleData.metrics;
  const p = turtleData.params;

  elChartEmpty.style.display = 'none';
  elChartContainer.style.display = 'none';
  elBacktestContainer.style.display = 'none';
  elTurtleContainer.style.display = 'flex';
  _hoverWired = false;

  renderTurtleKPIs(m);
  renderTurtleMainChart(d, p);
  renderTurtleDrawdownChart(d);
  renderTurtleComparisonChart(d, m);
}

function renderTurtleKPIs(m) {
  // 年化收益率
  const ann = m.annual_return;
  let annCls = 'neutral', annText = 'N/A';
  if (ann !== null && ann !== undefined) {
    annText = (ann >= 0 ? '+' : '') + ann.toFixed(2) + '%';
    annCls = ann > 0 ? 'positive' : (ann < 0 ? 'negative' : 'neutral');
  }
  const card = (id, cls, val, label, sub) => {
    const el = $('#' + id);
    if (el) { el.className = 'bt-kpi-card ' + cls; el.innerHTML = val + label + sub; }
  };
  card('tu-kpi-annual', annCls,
    `<span class="bt-kpi-value">${annText}</span>`,
    `<span class="bt-kpi-label">年化收益率</span>`,
    `<span class="bt-kpi-sub">总收益: ${m.total_return >= 0 ? '+' : ''}${m.total_return.toFixed(2)}%</span>`);

  // 夏普比率
  const sh = m.sharpe_ratio;
  let shCls = 'neutral', shText = 'N/A';
  if (sh !== null && sh !== undefined) {
    shText = sh.toFixed(2);
    shCls = sh >= 2 ? 'positive' : (sh >= 1 ? 'warning' : (sh < 0 ? 'negative' : 'neutral'));
  }
  card('tu-kpi-sharpe', shCls,
    `<span class="bt-kpi-value">${shText}</span>`,
    `<span class="bt-kpi-label">夏普比率</span>`,
    `<span class="bt-kpi-sub">基准收益: ${m.benchmark_return >= 0 ? '+' : ''}${m.benchmark_return.toFixed(2)}%</span>`);

  // 最大回撤
  const mdd = m.max_drawdown;
  let mddCls = 'neutral', mddText = 'N/A';
  if (mdd !== null && mdd !== undefined) {
    mddText = mdd.toFixed(2) + '%';
    mddCls = mdd > -10 ? 'positive' : (mdd > -20 ? 'warning' : 'negative');
  }
  card('tu-kpi-drawdown', mddCls,
    `<span class="bt-kpi-value">${mddText}</span>`,
    `<span class="bt-kpi-label">最大回撤</span>`,
    `<span class="bt-kpi-sub">${m.max_drawdown_date || ''}</span>`);

  // 胜率
  const wr = m.win_rate;
  let wrCls = 'neutral', wrText = 'N/A';
  if (wr !== null && wr !== undefined) {
    wrText = wr.toFixed(1) + '%';
    wrCls = wr >= 60 ? 'positive' : (wr >= 40 ? 'warning' : (wr < 30 ? 'negative' : 'neutral'));
  }
  const plText = m.profit_loss_ratio !== null && m.profit_loss_ratio !== undefined
    ? '盈亏比 ' + m.profit_loss_ratio.toFixed(2) : '';
  card('tu-kpi-winrate', wrCls,
    `<span class="bt-kpi-value">${wrText}</span>`,
    `<span class="bt-kpi-label">胜率</span>`,
    `<span class="bt-kpi-sub">${m.trade_count}笔交易${plText ? ' | ' + plText : ''}</span>`);
}

function renderTurtleMainChart(d, p) {
  const traces = [
    {
      x: d.dates, y: d.close, type: 'scatter', mode: 'lines',
      line: { color: '#64748b', width: 1.2 },
      name: 'Close', hovertemplate: '收盘: %{y:.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.entry_upper, type: 'scatter', mode: 'lines',
      line: { color: '#f59e0b', width: 1.0, dash: 'dash' },
      name: `入场通道 (${p.entry_period}日高)`,
      hovertemplate: '上轨: %{y:.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.exit_lower, type: 'scatter', mode: 'lines',
      line: { color: '#3b82f6', width: 1.0, dash: 'dash' },
      name: `出场通道 (${p.exit_period}日低)`,
      hovertemplate: '下轨: %{y:.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.stop_line, type: 'scatter', mode: 'lines',
      line: { color: 'rgba(168,85,247,0.35)', width: 0.8 },
      name: '止损线', hovertemplate: '止损: %{y:.2f}<extra></extra>',
      connectgaps: false,
    },
  ];

  // Buy signals — red upward triangles
  if (d.buy_signals && d.buy_signals.length > 0) {
    traces.push({
      x: d.buy_signals.map(s => s.date), y: d.buy_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'triangle-up', color: '#ef4444', size: 10, line: { width: 0 } },
      name: '入场', hovertemplate: '<b>入场</b><br>%{x}<br>¥%{y:.2f}<extra></extra>',
    });
  }

  // Add signals — orange upward triangles (smaller)
  if (d.add_signals && d.add_signals.length > 0) {
    traces.push({
      x: d.add_signals.map(s => s.date), y: d.add_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'triangle-up', color: '#f97316', size: 8, line: { width: 0 } },
      name: '加仓', hovertemplate: '<b>加仓</b><br>%{x}<br>¥%{y:.2f}<extra></extra>',
    });
  }

  // Sell signals — green downward triangles
  if (d.sell_signals && d.sell_signals.length > 0) {
    traces.push({
      x: d.sell_signals.map(s => s.date), y: d.sell_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'triangle-down', color: '#10b981', size: 10, line: { width: 0 } },
      name: '出场 (通道)', hovertemplate: '<b>出场</b><br>%{x}<br>¥%{y:.2f}<extra></extra>',
    });
  }

  // Stop-loss signals — purple cross markers
  if (d.stop_signals && d.stop_signals.length > 0) {
    traces.push({
      x: d.stop_signals.map(s => s.date), y: d.stop_signals.map(s => s.price),
      type: 'scatter', mode: 'markers',
      marker: { symbol: 'x', color: '#a855f7', size: 10, line: { width: 2 } },
      name: '止损', hovertemplate: '<b>止损</b><br>%{x}<br>¥%{y:.2f}<extra></extra>',
    });
  }

  const layout = {
    ...chartLayout('价格 (CNY)'),
    title: { text: '海龟交易信号', font: { size: 13, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 60, r: 24, t: 36, b: 40 },
  };

  Plotly.react('tu-chart-main', traces, layout, PLOTLY_CONFIG);
}

function renderTurtleDrawdownChart(d) {
  const dd = d.drawdown;
  const traces = [
    {
      x: d.dates, y: dd, type: 'scatter', mode: 'none',
      fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.12)',
      name: '回撤', hoverinfo: 'skip', showlegend: false,
    },
    {
      x: d.dates, y: dd, type: 'scatter', mode: 'lines',
      line: { color: '#ef4444', width: 1.1 },
      name: '回撤 %', hovertemplate: '回撤: %{y:.2f}%<extra></extra>',
    },
    {
      x: [d.dates[0], d.dates[d.dates.length - 1]], y: [0, 0],
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.08)', width: 0.5 },
      name: '0%', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('回撤 (%)'),
    title: { text: '回撤曲线', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 55, r: 18, t: 36, b: 40 },
    yaxis: {
      ...chartLayout().yaxis,
      title: { text: '回撤 (%)', font: { size: 10, color: '#6b7280' }, standoff: 6 },
    },
  };

  Plotly.react('tu-chart-dd', traces, layout, PLOTLY_CONFIG);
}

function renderTurtleComparisonChart(d, m) {
  const traces = [
    {
      x: d.dates, y: d.portfolio_value, type: 'scatter', mode: 'lines',
      line: { color: '#dc2626', width: 1.6 },
      name: '海龟策略',
      hovertemplate: '策略: ¥%{y:,.2f}<extra></extra>',
    },
    {
      x: d.dates, y: d.benchmark_value, type: 'scatter', mode: 'lines',
      line: { color: '#9ca3af', width: 1.0, dash: 'dash' },
      name: '买入持有 (基准)',
      hovertemplate: '基准: ¥%{y:,.2f}<extra></extra>',
    },
    {
      x: [d.dates[0], d.dates[d.dates.length - 1]],
      y: [m.initial_capital, m.initial_capital],
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.06)', width: 0.5 },
      name: '初始资金', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('组合净值 (CNY)'),
    title: { text: '策略 vs 基准', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 65, r: 18, t: 36, b: 40 },
    yaxis: {
      ...chartLayout().yaxis,
      title: { text: '净值 (CNY)', font: { size: 10, color: '#6b7280' }, standoff: 8 },
    },
  };

  Plotly.react('tu-chart-cmp', traces, layout, PLOTLY_CONFIG);
}


// ═══════════════════════════ Events ═══════════════════════

window.setCode = code => { elTsCode.value = code; };
elBtnFetch.addEventListener('click', fetchData);
elBtnApply.addEventListener('click', computeAndRender);
elBtnRefresh.addEventListener('click', loadFiles);
elFile.addEventListener('change', computeAndRender);
[elTsCode, elStart, elEnd].forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') fetchData(); });
});

// Backtest events
elBtRun.addEventListener('click', runBacktest);
elBtReset.addEventListener('click', resetBtParams);
elBtFile.addEventListener('change', onBtFileChange);
[elBtStart, elBtEnd].forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') runBacktest(); });
});

// Turtle events
elTuRun.addEventListener('click', runTurtle);
elTuReset.addEventListener('click', resetTurtleParams);
elTuFile.addEventListener('change', onTuFileChange);
[elTuStart, elTuEnd].forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') runTurtle(); });
});

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (activePanel === 'backtest' && backtestData) {
      renderBacktest();
    } else if (activePanel === 'turtle' && turtleData) {
      renderTurtle();
    } else if (activePanel === 'ml' && mlData) {
      renderML();
    } else if (activePanel === 'ml' && mlCompareData) {
      renderMLCompare();
    } else if (indicatorData) {
      renderActiveChart();
    }
  }, 250);
});

// ═══════════════════════════ ML Quant ═══════════════════════

let mlData = null;
let mlCompareData = null;

// DOM refs
const elMlFile = $('#ml-file');
const elMlModelType = $('#ml-model-type');
const elMlTaskType = $('#ml-task-type');
const elMlTopN = $('#ml-top-n');
const elMlWinsorize = $('#ml-winsorize');
const elMlTrainRatio = $('#ml-train-ratio');
const elMlValRatio = $('#ml-val-ratio');
const elMlStandardize = $('#ml-standardize');
const elMlBtnAnalyze = $('#btn-ml-analyze');
const elMlBtnCompare = $('#btn-ml-compare');
const elMlStatus = $('#ml-status');
const elMlContainer = $('#ml-container');

function loadMLFiles() {
  fetch('/api/ml/files')
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        const files = data.files || [];
        const opts = files.map(f =>
          `<option value="${f.name}">${f.name} (${f.dir}) — ${f.n_cols||'?'}列</option>`
        ).join('');
        elMlFile.innerHTML = opts;
        // 默认选 factor panel 数据
        const factorOpt = Array.from(elMlFile.options).find(o => o.value.includes('factor'));
        if (factorOpt) factorOpt.selected = true;
      }
    });
}

async function runMLAnalyze() {
  const file = elMlFile.value;
  if (!file) { elMlStatus.textContent = '❌ 请选择数据文件'; return; }

  const params = {
    file,
    model_type: elMlModelType.value,
    task_type: elMlTaskType.value,
    top_n: parseInt(elMlTopN.value) || 30,
    winsorize_pct: parseFloat(elMlWinsorize.value) / 100 || 0.01,
    train_ratio: parseFloat(elMlTrainRatio.value) || 0.6,
    val_ratio: parseFloat(elMlValRatio.value) || 0.2,
    standardize: elMlStandardize.checked,
  };

  elMlBtnAnalyze.disabled = true;
  elMlBtnCompare.disabled = true;
  elMlStatus.textContent = '⏳ ML 分析运行中…（可能需要几十秒）';
  mlCompareData = null;

  try {
    const resp = await fetch('/api/ml/analyze', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(params),
    });
    const r = await resp.json();
    if (r.ok) {
      mlData = r;
      renderML();
      elMlStatus.textContent = `✅ 分析完成 — ${r.data_summary?.n_stocks || '?'}只股票 × ${r.data_summary?.n_quarters || '?'}季度`;
    } else {
      elMlStatus.textContent = `❌ ${r.error}`;
    }
  } catch (e) {
    elMlStatus.textContent = `❌ ${e.message}`;
  } finally {
    elMlBtnAnalyze.disabled = false;
    elMlBtnCompare.disabled = false;
  }
}

async function runMLCompare() {
  const file = elMlFile.value;
  if (!file) { elMlStatus.textContent = '❌ 请选择数据文件'; return; }

  const params = {
    file,
    model_types: ['linear', 'decision_tree', 'random_forest'],
    task_type: elMlTaskType.value,
    top_n: parseInt(elMlTopN.value) || 30,
  };

  elMlBtnAnalyze.disabled = true;
  elMlBtnCompare.disabled = true;
  elMlStatus.textContent = '⏳ 多模型对比运行中…（可能需要几分钟）';
  mlData = null;

  try {
    const resp = await fetch('/api/ml/compare', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(params),
    });
    const r = await resp.json();
    if (r.ok) {
      mlCompareData = r;
      renderMLCompare();
      elMlStatus.textContent = `✅ 对比完成 — ${r.model_types?.length || 0} 个模型`;
    } else {
      elMlStatus.textContent = `❌ ${r.error}`;
    }
  } catch (e) {
    elMlStatus.textContent = `❌ ${e.message}`;
  } finally {
    elMlBtnAnalyze.disabled = false;
    elMlBtnCompare.disabled = false;
  }
}

function renderML() {
  if (!mlData) return;
  const m = mlData.backtest_metrics || {};
  const mm = mlData.model_metrics || {};
  const nc = mlData.nav_curve || {};
  const qr = mlData.quarterly_results || [];
  const ic = mlData.ic_series || [];
  const fi = mlData.feature_importance || [];

  // Show ML container
  elChartEmpty.style.display = 'none';
  elChartContainer.style.display = 'none';
  elBacktestContainer.style.display = 'none';
  elTurtleContainer.style.display = 'none';
  elMlContainer.style.display = 'flex';
  _hoverWired = false;

  // ── KPI Cards ──────────────────────────────────────
  renderMLKPIs(m, mm);

  // ── Show model metrics row for regression/classification ──
  const modelMetricsRow = $('#ml-model-metrics-row');
  if (modelMetricsRow) {
    const taskType = mlData.config?.task_type || 'regression';
    if (taskType === 'regression') {
      modelMetricsRow.style.display = 'flex';
      const r2El = $('#ml-metric-r2');
      const mseEl = $('#ml-metric-mse');
      const maeEl = $('#ml-metric-mae');
      if (r2El) r2El.querySelector('.bt-kpi-label').textContent = 'R²';
      if (mseEl) mseEl.querySelector('.bt-kpi-label').textContent = 'MSE';
      if (maeEl) maeEl.querySelector('.bt-kpi-label').textContent = 'MAE';
    } else {
      modelMetricsRow.style.display = 'flex';
      const r2El = $('#ml-metric-r2');
      const mseEl = $('#ml-metric-mse');
      const maeEl = $('#ml-metric-mae');
      if (r2El) r2El.querySelector('.bt-kpi-label').textContent = 'Accuracy';
      if (mseEl) mseEl.querySelector('.bt-kpi-label').textContent = 'Precision';
      if (maeEl) maeEl.querySelector('.bt-kpi-label').textContent = 'F1 Score';
    }
  }

  // Fill model metrics
  const setKey = 'test_';  // use test set metrics
  fillMetricKPI('ml-metric-r2', mm[setKey + 'r2'] ?? mm[setKey + 'accuracy'],
    mm[setKey + 'r2'] != null ? 'R²' : 'Accuracy',
    (v) => (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%');
  fillMetricKPI('ml-metric-mse', mm[setKey + 'mse'] ?? mm[setKey + 'precision'],
    mm[setKey + 'mse'] != null ? 'MSE' : 'Precision',
    (v) => v.toFixed(4));
  fillMetricKPI('ml-metric-mae', mm[setKey + 'mae'] ?? mm[setKey + 'f1'],
    mm[setKey + 'mae'] != null ? 'MAE' : 'F1',
    (v) => v.toFixed(4));

  // ── Cumulative NAV Chart ───────────────────────────
  renderMLNavChart(nc, qr);

  // ── Quarterly Returns Chart ────────────────────────
  renderMLQuarterlyChart(qr);

  // ── Feature Importance Chart ───────────────────────
  renderMLImportanceChart(fi);

  // ── IC Series Chart ────────────────────────────────
  renderMLICChart(ic);
}

function renderMLKPIs(m, mm) {
  const ann = m.annual_return;
  fillKPI('ml-kpi-annual',
    ann != null ? ((ann >= 0 ? '+' : '') + ann.toFixed(2) + '%') : 'N/A',
    '年化收益率',
    `累计: ${m.cumulative_return != null ? (m.cumulative_return >= 0 ? '+' : '') + m.cumulative_return.toFixed(2) + '%' : 'N/A'}`,
    ann > 0 ? 'positive' : (ann < 0 ? 'negative' : 'neutral'));

  const sh = m.sharpe_ratio;
  fillKPI('ml-kpi-sharpe',
    sh != null ? sh.toFixed(3) : 'N/A', '夏普比率',
    `基准年化: ${m.benchmark_annual_return != null ? (m.benchmark_annual_return >= 0 ? '+' : '') + m.benchmark_annual_return.toFixed(2) + '%' : 'N/A'}`,
    sh >= 2 ? 'positive' : (sh >= 1 ? 'warning' : (sh < 0 ? 'negative' : 'neutral')));

  const mdd = m.max_drawdown;
  fillKPI('ml-kpi-drawdown',
    mdd != null ? mdd.toFixed(2) + '%' : 'N/A', '最大回撤',
    m.max_drawdown_quarter || '',
    mdd > -10 ? 'positive' : (mdd > -20 ? 'warning' : 'negative'));

  const wr = m.win_rate;
  fillKPI('ml-kpi-winrate',
    wr != null ? wr.toFixed(1) + '%' : 'N/A', '胜率',
    `超额胜率: ${m.excess_win_rate != null ? m.excess_win_rate.toFixed(1) + '%' : 'N/A'}`,
    wr >= 60 ? 'positive' : (wr >= 40 ? 'warning' : 'neutral'));

  // IC card
  const rankIC = mm.test_rank_ic_mean;
  fillKPI('ml-kpi-ic',
    rankIC != null ? rankIC.toFixed(4) : 'N/A', 'Rank IC (Mean)',
    `ICIR: ${mm.test_icir != null ? mm.test_icir.toFixed(2) : 'N/A'}`,
    rankIC > 0.05 ? 'positive' : (rankIC > 0 ? 'warning' : 'negative'));
}

function fillKPI(id, value, label, sub, cls) {
  const el = $('#' + id);
  if (!el) return;
  el.className = 'bt-kpi-card ' + (cls || 'neutral');
  el.innerHTML = `<span class="bt-kpi-value">${value}</span><span class="bt-kpi-label">${label}</span><span class="bt-kpi-sub">${sub}</span>`;
}

function fillMetricKPI(id, value, label, formatter) {
  const el = $('#' + id);
  if (!el) return;
  if (value != null) {
    const formatted = typeof formatter === 'function' ? formatter(value) : value;
    el.querySelector('.bt-kpi-value').textContent = formatted;
  }
}

function renderMLNavChart(nc, qr) {
  const quarters = nc.quarters || qr.map(r => r.quarter) || [];
  const pv = nc.portfolio_value || [];
  const bv = nc.benchmark_value || [];
  const initCap = mlData.backtest_metrics?.initial_capital || 1000000;

  const traces = [
    {
      x: quarters, y: pv, type: 'scatter', mode: 'lines+markers',
      line: { color: '#4f46e5', width: 2.0 },
      marker: { size: 6, color: '#4f46e5' },
      name: 'ML 策略', hovertemplate: '净值: ¥%{y:,.0f}<extra>ML 策略</extra>',
    },
    {
      x: quarters, y: bv, type: 'scatter', mode: 'lines+markers',
      line: { color: '#9ca3af', width: 1.2, dash: 'dash' },
      marker: { size: 5, color: '#9ca3af' },
      name: '等权基准', hovertemplate: '净值: ¥%{y:,.0f}<extra>等权基准</extra>',
    },
    {
      x: [quarters[0], quarters[quarters.length - 1]],
      y: [initCap, initCap], type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.06)', width: 0.5 },
      name: '初始资金', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('组合净值 (CNY)'),
    title: { text: '累计净值曲线 — ML 策略 vs 等权基准', font: { size: 13, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 70, r: 24, t: 36, b: 50 },
    yaxis: { ...chartLayout().yaxis, title: { text: '净值 (CNY)', font: { size: 10, color: '#6b7280' }, standoff: 8 }},
  };

  Plotly.react('ml-chart-nav', traces, layout, PLOTLY_CONFIG);
}

function renderMLQuarterlyChart(qr) {
  const quarters = qr.map(r => r.quarter);
  const stratRets = qr.map(r => (r.strategy_return != null ? r.strategy_return * 100 : null));
  const benchRets = qr.map(r => (r.benchmark_return != null ? r.benchmark_return * 100 : null));
  // Excess returns as bar colors
  const excessColors = qr.map(r => {
    if (r.strategy_return == null || r.benchmark_return == null) return 'rgba(0,0,0,0.1)';
    return (r.strategy_return > r.benchmark_return) ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.5)';
  });

  const traces = [
    {
      x: quarters, y: benchRets, type: 'bar', name: '基准收益',
      marker: { color: 'rgba(156,163,175,0.5)' },
      hovertemplate: '基准: %{y:.2f}%<extra></extra>',
    },
    {
      x: quarters, y: stratRets, type: 'bar', name: '策略收益',
      marker: { color: excessColors },
      hovertemplate: '策略: %{y:.2f}%<extra></extra>',
    },
  ];

  const layout = {
    ...chartLayout('收益率 (%)'),
    barmode: 'overlay',
    title: { text: '每季度收益率', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 55, r: 18, t: 36, b: 50 },
    yaxis: { ...chartLayout().yaxis, title: { text: '收益率 (%)', font: { size: 10, color: '#6b7280' }, standoff: 6 }},
    xaxis: { ...chartLayout().xaxis, tickangle: -45 },
  };

  Plotly.react('ml-chart-quarterly', traces, layout, PLOTLY_CONFIG);
}

function renderMLImportanceChart(fi) {
  if (!fi || fi.length === 0) {
    Plotly.react('ml-chart-importance', [], chartLayout(), PLOTLY_CONFIG);
    return;
  }
  const topFi = fi.slice(0, 15).reverse();
  const traces = [{
    y: topFi.map(f => f.feature),
    x: topFi.map(f => f.importance),
    type: 'bar', orientation: 'h',
    marker: {
      color: topFi.map((_, i) => {
        const t = i / (topFi.length - 1 || 1);
        return `rgba(79,70,229,${0.3 + t * 0.7})`;
      }),
    },
    hovertemplate: '%{x:.4f}<extra>%{y}</extra>',
  }];

  const layout = {
    ...chartLayout(''),
    title: { text: '特征重要性 (Top 15)', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 180, r: 18, t: 36, b: 40 },
    xaxis: { ...chartLayout().xaxis, title: { text: 'Importance', font: { size: 10, color: '#6b7280' } }},
  };

  Plotly.react('ml-chart-importance', traces, layout, PLOTLY_CONFIG);
}

function renderMLICChart(ic) {
  if (!ic || ic.length === 0) {
    Plotly.react('ml-chart-ic', [], chartLayout(), PLOTLY_CONFIG);
    return;
  }
  const quarters = ic.map(d => d.quarter);
  const icVals = ic.map(d => d.ic);
  const rankIcVals = ic.map(d => d.rank_ic);

  const traces = [
    {
      x: quarters, y: icVals, type: 'scatter', mode: 'lines+markers',
      line: { color: '#3b82f6', width: 1.4 },
      marker: { size: 7, color: '#3b82f6' },
      name: 'IC', hovertemplate: 'IC: %{y:.4f}<extra></extra>',
    },
    {
      x: quarters, y: rankIcVals, type: 'scatter', mode: 'lines+markers',
      line: { color: '#f59e0b', width: 1.4 },
      marker: { size: 7, color: '#f59e0b' },
      name: 'Rank IC', hovertemplate: 'Rank IC: %{y:.4f}<extra></extra>',
    },
    {
      x: [quarters[0], quarters[quarters.length - 1]], y: [0, 0],
      type: 'scatter', mode: 'lines',
      line: { color: 'rgba(0,0,0,0.08)', width: 0.5 },
      name: 'Zero', hoverinfo: 'skip', showlegend: false,
    },
  ];

  const layout = {
    ...chartLayout('IC'),
    title: { text: 'IC / Rank IC 逐季表现', font: { size: 12, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 55, r: 18, t: 36, b: 50 },
    yaxis: { ...chartLayout().yaxis, title: { text: 'IC', font: { size: 10, color: '#6b7280' }, standoff: 6 }},
    xaxis: { ...chartLayout().xaxis, tickangle: -45 },
  };

  Plotly.react('ml-chart-ic', traces, layout, PLOTLY_CONFIG);
}

function renderMLCompare() {
  if (!mlCompareData) return;

  elChartEmpty.style.display = 'none';
  elChartContainer.style.display = 'none';
  elBacktestContainer.style.display = 'none';
  elTurtleContainer.style.display = 'none';
  elMlContainer.style.display = 'none';

  // Use a simple approach: show compare results in the ML container with a table
  elMlContainer.style.display = 'flex';
  _hoverWired = false;

  const comp = mlCompareData.comparison || {};
  const models = Object.keys(comp);

  // Build comparison KPI table at top
  let tableHTML = `
    <div class="ml-section-heading">📊 模型对比结果</div>
    <div style="overflow-x:auto;background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);">
    <table class="ml-compare-table">
      <thead><tr>
        <th>指标</th>
        ${models.map(m => `<th>${m.replace(/_/g,' ')}</th>`).join('')}
      </tr></thead>
      <tbody>`;

  const metricRows = [
    ['累计收益率 (%)', 'cumulative_return'],
    ['年化收益率 (%)', 'annual_return'],
    ['夏普比率', 'sharpe_ratio'],
    ['最大回撤 (%)', 'max_drawdown'],
    ['胜率 (%)', 'win_rate'],
    ['超额胜率 (%)', 'excess_win_rate'],
  ];

  for (const [label, key] of metricRows) {
    const vals = models.map(m => {
      const bm = comp[m]?.backtest_metrics || {};
      return bm[key];
    });
    const maxVal = Math.max(...vals.filter(v => v != null));
    const minVal = Math.min(...vals.filter(v => v != null));
    tableHTML += `<tr><td style="font-weight:600;">${label}</td>`;
    for (let i = 0; i < models.length; i++) {
      const v = vals[i];
      const isMax = v != null && v === maxVal && maxVal !== minVal;
      const isMin = v != null && v === minVal && maxVal !== minVal;
      let cls = '';
      if (isMax && (key.includes('return') || key.includes('sharpe') || key.includes('win'))) cls = 'positive highlight';
      else if (isMin && (key.includes('return') || key.includes('sharpe') || key.includes('win'))) cls = 'negative';
      else if (isMax && key.includes('drawdown')) cls = 'positive highlight';
      else if (isMin && key.includes('drawdown')) cls = 'negative';
      tableHTML += `<td class="${cls}">${v != null ? (typeof v === 'number' ? v.toFixed(2) : v) : 'N/A'}</td>`;
    }
    tableHTML += '</tr>';
  }

  // Add model metrics rows
  const modelMetricRows = [
    ['Rank IC Mean', 'rank_ic_mean', 'test_'],
    ['ICIR', 'icir', 'test_'],
  ];
  for (const [label, key, prefix] of modelMetricRows) {
    const vals = models.map(m => {
      const mm = comp[m]?.model_metrics || {};
      return mm[prefix + key];
    });
    const maxVal = Math.max(...vals.filter(v => v != null));
    const minVal = Math.min(...vals.filter(v => v != null));
    tableHTML += `<tr><td style="font-weight:600;">${label}</td>`;
    for (let i = 0; i < models.length; i++) {
      const v = vals[i];
      const isMax = v != null && v === maxVal && maxVal !== minVal;
      let cls = isMax ? 'positive highlight' : '';
      tableHTML += `<td class="${cls}">${v != null ? v.toFixed(4) : 'N/A'}</td>`;
    }
    tableHTML += '</tr>';
  }

  tableHTML += '</tbody></table></div>';

  // Render the table in a new div we create
  let tableDiv = $('#ml-compare-table-div');
  if (!tableDiv) {
    tableDiv = document.createElement('div');
    tableDiv.id = 'ml-compare-table-div';
    elMlContainer.insertBefore(tableDiv, elMlContainer.firstChild);
  }
  tableDiv.innerHTML = tableHTML;

  // ── Compare NAV Chart ──────────────────────────────
  const navTraces = [];
  const colors = ['#4f46e5', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'];
  models.forEach((m, i) => {
    const nc = comp[m]?.nav_curve || {};
    const qrComp = comp[m]?.quarterly_results || [];
    const quarters = nc.quarters || qrComp.map(r => r.quarter) || [];
    const pv = nc.portfolio_value || [];
    if (pv.length > 0) {
      navTraces.push({
        x: quarters, y: pv, type: 'scatter', mode: 'lines+markers',
        line: { color: colors[i % colors.length], width: 1.8 },
        marker: { size: 5 },
        name: m.replace(/_/g, ' '), hovertemplate: '%{x}<br>¥%{y:,.0f}<extra>' + m + '</extra>',
      });
    }
  });

  const navLayout = {
    ...chartLayout('组合净值 (CNY)'),
    title: { text: '累计净值曲线 — 多模型对比', font: { size: 13, color: '#374151' }, x: 0.01, y: 0.98 },
    margin: { l: 70, r: 24, t: 36, b: 50 },
    yaxis: { ...chartLayout().yaxis, title: { text: '净值 (CNY)', font: { size: 10, color: '#6b7280' }, standoff: 8 }},
  };
  Plotly.react('ml-chart-nav', navTraces, navLayout, PLOTLY_CONFIG);

  // Hide other ML charts
  Plotly.react('ml-chart-quarterly', [], chartLayout(), PLOTLY_CONFIG);
  Plotly.react('ml-chart-importance', [], chartLayout(), PLOTLY_CONFIG);
  Plotly.react('ml-chart-ic', [], chartLayout(), PLOTLY_CONFIG);

  // Update KPIs with best model
  const bestModel = models.reduce((best, m) => {
    const bm = comp[m]?.backtest_metrics || {};
    const bestBm = comp[best]?.backtest_metrics || {};
    return (bm.annual_return || -Infinity) > (bestBm.annual_return || -Infinity) ? m : best;
  }, models[0]);
  const bestM = comp[bestModel]?.backtest_metrics || {};
  const bestMM = comp[bestModel]?.model_metrics || {};
  renderMLKPIs(bestM, bestMM);
  elMlStatus.textContent = `✅ 对比完成 | 最佳: ${bestModel.replace(/_/g, ' ')} (年化 ${(bestM.annual_return||0).toFixed(2)}%)`;
}


// ═══════════════════════════ Events: ML ═══════════════

elMlBtnAnalyze.addEventListener('click', runMLAnalyze);
elMlBtnCompare.addEventListener('click', runMLCompare);
elMlFile.addEventListener('change', () => { mlData = null; mlCompareData = null; });


// ═══════════════════════════ Init ════════════════════════

(async function init() {
  await loadFiles();
  loadMLFiles();
  selectIndicator('price_ma');
  openPanel('data');
  if (elFile.value) await computeAndRender();
  onBtFileChange();
  onTuFileChange();
})();
