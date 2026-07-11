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

// ═══════════════════════════ State ═══════════════════════════

let activePanel = 'data';
let activeInd = 'price_ma';
let indicatorData = null;
let lastParams = null;
let backtestData = null;
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
  } else if (activePanel && indicatorData) {
    elBacktestContainer.style.display = 'none';
    elChartEmpty.style.display = 'none';
    elChartContainer.style.display = 'block';
    requestAnimationFrame(() => renderActiveChart());
  } else if (activePanel && !indicatorData) {
    elBacktestContainer.style.display = 'none';
    elChartContainer.style.display = 'none';
    elChartEmpty.style.display = 'flex';
    elChartEmpty.querySelector('h2').textContent = 'Quant Dashboard';
    elChartEmpty.querySelector('p').textContent = '选择数据源 → 选择指标 → 查看图表';
  } else {
    // Collapsed
    elBacktestContainer.style.display = 'none';
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
    if (files.length) elFetchStatus.textContent = `共 ${files.length} 个文件可用`;
    updateBtDatePlaceholders();
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

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (activePanel === 'backtest' && backtestData) {
      renderBacktest();
    } else if (indicatorData) {
      renderActiveChart();
    }
  }, 250);
});

// ═══════════════════════════ Init ════════════════════════

(async function init() {
  await loadFiles();
  selectIndicator('price_ma');
  openPanel('data');
  if (elFile.value) await computeAndRender();
  onBtFileChange();
})();
