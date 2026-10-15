const state = { sources: [], current: null, observations: [], filtered: [], shown: 20, request: 0 };
const $ = (id) => document.getElementById(id);
const svgNS = 'http://www.w3.org/2000/svg';
const colors = ['#16805d', '#d2833d', '#497995', '#a9544a', '#7d6b50', '#438f90'];
const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });

function svgElement(tag, attrs = {}) {
  const node = document.createElementNS(svgNS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function showNotice(message, error = false) {
  const notice = $('notice');
  notice.hidden = !message;
  notice.textContent = message || '';
  notice.classList.toggle('error', error);
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(`${value}T00:00:00Z`);
  if (state.current?.frequency === 'Anual') return String(date.getUTCFullYear());
  if (state.current?.frequency === 'Mensal') return date.toLocaleDateString('pt-BR', { timeZone: 'UTC', month: 'short', year: 'numeric' });
  return date.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
}

function formatSummaryDate(value) {
  if (state.current?.frequency !== 'Mensal') return formatDate(value);
  const [year, month] = value.split('-');
  return `${month}/${year}`;
}

function formatValue(value, unit = '') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return `${number.format(Number(value))}${unit ? ` ${unit}` : ''}`;
}

function fillSelect(id, values, allLabel, preferred = '') {
  const select = $(id);
  select.replaceChildren();
  const all = document.createElement('option');
  all.value = '';
  all.textContent = allLabel;
  select.append(all);
  values.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
  select.value = preferred;
}

function buildNavigation() {
  const nav = $('source-nav');
  nav.replaceChildren();
  const groups = [...new Set(state.sources.map((source) => source.group))];
  groups.forEach((group) => {
    const block = document.createElement('div');
    block.className = 'source-group';
    const heading = document.createElement('h2');
    heading.textContent = group;
    block.append(heading);
    state.sources.filter((source) => source.group === group).forEach((source) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'source-option';
      button.disabled = !source.available;
      button.title = source.available ? source.name : source.note;
      button.dataset.source = source.id;
      const label = document.createElement('span');
      label.textContent = source.name;
      const dot = document.createElement('span');
      dot.className = 'status-dot';
      dot.setAttribute('aria-hidden', 'true');
      button.append(label, dot);
      button.addEventListener('click', () => loadSource(source.id));
      block.append(button);
    });
    nav.append(block);
  });
}

function sourceHeader() {
  const source = state.current;
  $('source-title').textContent = source.name;
  $('source-group').textContent = source.group.toUpperCase();
  $('source-subtitle').textContent = `${source.frequency} · ${source.stage} · ${source.unit}`;
  $('source-note').textContent = source.note;
  const badge = $('source-badge');
  badge.textContent = source.kind === 'demo' ? 'SINTÉTICO' : source.kind === 'local' ? 'ARQUIVO LOCAL' : 'API OFICIAL';
  badge.className = `source-badge ${source.kind === 'live' ? 'live' : source.kind === 'local' ? 'local' : ''}`;
  document.querySelectorAll('.source-option').forEach((button) => {
    button.classList.toggle('active', button.dataset.source === source.id);
    button.setAttribute('aria-current', button.dataset.source === source.id ? 'page' : 'false');
  });
}

async function loadSource(id, refresh = false) {
  const source = state.sources.find((item) => item.id === id);
  if (!source || !source.available) return;
  state.current = source;
  state.observations = [];
  state.shown = 20;
  sourceHeader();
  showNotice('Consultando fonte…');
  $('refresh-button').disabled = true;
  const request = ++state.request;
  try {
    const response = await fetch(`/api/observations/${encodeURIComponent(id)}${refresh ? '?refresh=true' : ''}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    if (request !== state.request) return;
    state.observations = payload.observations;
    const products = [...new Set(state.observations.map((row) => row.product))].sort();
    const locations = [...new Set(state.observations.map((row) => row.location))].sort();
    const stages = [...new Set(state.observations.map((row) => row.stage))].sort();
    fillSelect('product-filter', products, 'Todos os produtos', ['v8', 'ibge'].includes(id) ? products[0] : '');
    fillSelect('location-filter', locations, 'Todas as localidades', id === 'v8' ? locations[0] : '');
    fillSelect('stage-filter', stages, 'Todas as etapas');
    $('range-filter').value = 'all';
    showNotice('');
    applyFilters();
  } catch (error) {
    if (request !== state.request) return;
    state.observations = [];
    fillSelect('product-filter', [], 'Todos os produtos');
    fillSelect('location-filter', [], 'Todas as localidades');
    fillSelect('stage-filter', [], 'Todas as etapas');
    applyFilters();
    showNotice(error.message, true);
  } finally {
    if (request === state.request) $('refresh-button').disabled = false;
  }
}

function applyFilters() {
  const product = $('product-filter').value;
  const location = $('location-filter').value;
  const stage = $('stage-filter').value;
  const months = Number($('range-filter').value);
  let rows = state.observations.filter((row) =>
    (!product || row.product === product) &&
    (!location || row.location === location) &&
    (!stage || row.stage === stage)
  );
  if (months) {
    const latest = rows.reduce((max, row) => row.date > max ? row.date : max, '');
    const cutoff = new Date(`${latest}T00:00:00Z`);
    cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
    rows = rows.filter((row) => new Date(`${row.date}T00:00:00Z`) >= cutoff);
  }
  state.filtered = rows.sort((a, b) => b.date.localeCompare(a.date));
  state.shown = 20;
  renderSummary();
  renderChart();
  renderTable();
  renderProvenance();
}

function renderSummary() {
  const rows = state.filtered;
  const groups = new Set(rows.map((row) => `${row.product}|${row.location}|${row.stage}`));
  const latest = rows.find((row) => row.value !== null && Number.isFinite(Number(row.value)));
  const singleSeries = groups.size === 1;
  $('latest-value').textContent = latest && singleSeries ? formatValue(latest.value, latest.unit) : '—';
  $('latest-detail').textContent = groups.size > 1 ? `${groups.size} séries na seleção` :
    latest ? `${latest.product} · ${latest.stage} · ${latest.location}` : 'Sem valor válido';
  $('latest-date').textContent = rows.length ? formatSummaryDate(rows[0].date) : '—';
  $('date-detail').textContent = rows.length ? state.current.frequency : '—';
  $('observation-count').textContent = number.format(rows.length);
  const missing = rows.filter((row) => row.value === null).length;
  $('count-detail').textContent = missing ? `${missing} sem valor` : `${state.current?.frequency || ''} · ${state.current?.unit || ''}`;
  $('download-button').disabled = rows.length === 0;
}

function drawText(svg, text, x, y, attrs = {}) {
  const node = svgElement('text', { x, y, fill: '#72857a', 'font-size': '11', ...attrs });
  node.textContent = text;
  svg.append(node);
}

function renderChart() {
  const svg = $('chart');
  svg.replaceChildren();
  const compact = window.matchMedia('(max-width: 560px)').matches;
  const width = compact ? 700 : 960;
  const left = compact ? 88 : 64;
  const right = compact ? 676 : 918;
  svg.setAttribute('viewBox', `0 0 ${width} 360`);
  const legend = $('chart-legend');
  legend.replaceChildren();
  const rows = state.filtered.filter((row) => row.value !== null && Number.isFinite(Number(row.value)));
  if (!rows.length) {
    drawText(svg, 'Sem valores para os filtros selecionados', width / 2, 180, { 'text-anchor': 'middle', 'font-size': compact ? '20' : '14' });
    $('chart-footnote').textContent = '';
    return;
  }
  const groups = new Map();
  rows.forEach((row) => {
    const key = `${row.product} · ${row.location} · ${row.stage}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  const selected = [...groups.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 6);
  const plotted = selected.flatMap(([, items]) => items);
  const times = plotted.map((row) => Date.parse(`${row.date}T00:00:00Z`));
  const values = plotted.map((row) => Number(row.value));
  const minTime = Math.min(...times), maxTime = Math.max(...times);
  const minValue = Math.min(...values), maxValue = Math.max(...values);
  const padding = Math.max((maxValue - minValue) * 0.12, Math.abs(maxValue) * 0.02, 0.1);
  const low = minValue - padding, high = maxValue + padding;
  const x = (row) => left + ((Date.parse(`${row.date}T00:00:00Z`) - minTime) / (maxTime - minTime || 1)) * (right - left);
  const y = (row) => 297 - ((Number(row.value) - low) / (high - low)) * 258;
  for (let tick = 0; tick <= 4; tick++) {
    const yy = 297 - tick * 64.5;
    svg.append(svgElement('line', { x1: left, x2: right, y1: yy, y2: yy, stroke: '#e6ece8' }));
    drawText(svg, number.format(low + (high - low) * tick / 4), left - 9, yy + 4,
      { 'text-anchor': 'end', 'font-size': compact ? '19' : '11' });
  }
  [0, 0.5, 1].forEach((fraction) => {
    const stamp = minTime + (maxTime - minTime) * fraction;
    const day = new Date(stamp).toISOString().slice(0, 10);
    drawText(svg, formatDate(day), left + (right - left) * fraction, 326,
      { 'text-anchor': fraction === 0 ? 'start' : fraction === 1 ? 'end' : 'middle',
        'font-size': compact ? '19' : '11' });
  });
  selected.forEach(([label, items], index) => {
    const color = colors[index];
    const sorted = [...items].sort((a, b) => a.date.localeCompare(b.date));
    const path = sorted.map((row, point) => `${point ? 'L' : 'M'}${x(row).toFixed(1)},${y(row).toFixed(1)}`).join(' ');
    svg.append(svgElement('path', { d: path, fill: 'none', stroke: color, 'stroke-width': 2.5,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    sorted.forEach((row) => {
      const circle = svgElement('circle', { cx: x(row), cy: y(row), r: 4, fill: color,
        stroke: '#fff', 'stroke-width': 1.5, tabindex: 0 });
      const tooltip = () => {
        const box = $('chart').getBoundingClientRect();
        const tip = $('chart-tooltip');
        tip.textContent = `${formatDate(row.date)} · ${formatValue(row.value, row.unit)} · ${row.quality}`;
        tip.hidden = false;
        tip.style.left = `${Math.min(box.width - 170, Math.max(5, x(row) / width * box.width + 8))}px`;
        tip.style.top = `${Math.max(4, y(row) / 360 * box.height - 39)}px`;
      };
      circle.addEventListener('mouseenter', tooltip);
      circle.addEventListener('focus', tooltip);
      circle.addEventListener('mouseleave', () => { $('chart-tooltip').hidden = true; });
      circle.addEventListener('blur', () => { $('chart-tooltip').hidden = true; });
      svg.append(circle);
    });
    const item = document.createElement('span');
    item.className = 'legend-item';
    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch';
    swatch.style.background = color;
    item.append(swatch, document.createTextNode(label));
    legend.append(item);
  });
  $('chart-footnote').textContent = groups.size > 6 ? `Exibindo 6 de ${groups.size} séries. Refine os filtros para ver as demais.` :
    'Valores observados; sem interpolação de períodos ausentes.';
}

function renderTable() {
  const body = $('observation-rows');
  body.replaceChildren();
  state.filtered.slice(0, state.shown).forEach((row) => {
    const tr = document.createElement('tr');
    const values = [formatDate(row.date), row.product, row.location, row.stage,
      formatValue(row.value, row.unit), row.quality];
    values.forEach((value, index) => {
      const td = document.createElement('td');
      td.textContent = value;
      if (index === 4) td.className = 'numeric';
      if (index === 5) td.className = `quality ${row.quality === 'OK' || row.quality === 'SINTETICO' ? '' : row.quality === 'AUSENTE' ? 'missing' : 'flagged'}`;
      tr.append(td);
    });
    body.append(tr);
  });
  if (!state.filtered.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.textContent = 'Nenhuma observação para a seleção.';
    tr.append(td);
    body.append(tr);
  }
  $('table-count').textContent = `${Math.min(state.shown, state.filtered.length)} de ${state.filtered.length} observações`;
  $('more-button').hidden = state.shown >= state.filtered.length;
}

function renderProvenance() {
  const url = state.filtered.find((row) => row.source_url)?.source_url;
  const link = $('source-link');
  link.hidden = !url;
  if (url) link.href = url;
  else link.removeAttribute('href');
}

function downloadCsv() {
  const headers = ['data', 'produto', 'localidade', 'etapa', 'valor', 'unidade', 'qualidade',
    'fonte_primaria', 'distribuidor', 'url_fonte'];
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  const lines = [headers.join(',')];
  state.filtered.forEach((row) => lines.push([
    row.date, row.product, row.location, row.stage, row.value, row.unit, row.quality,
    row.primary_source, row.distributor, row.source_url,
  ].map(escape).join(',')));
  const blob = new Blob(['\ufeff', lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `agro-intelligence-${state.current.id}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function start() {
  try {
    const response = await fetch('/api/sources');
    if (!response.ok) throw new Error('Não foi possível carregar as fontes.');
    state.sources = await response.json();
    buildNavigation();
    ['product-filter', 'location-filter', 'stage-filter', 'range-filter'].forEach((id) =>
      $(id).addEventListener('change', applyFilters));
    $('refresh-button').addEventListener('click', () => loadSource(state.current.id, true));
    $('download-button').addEventListener('click', downloadCsv);
    $('more-button').addEventListener('click', () => { state.shown += 20; renderTable(); });
    await loadSource(state.sources.find((source) => source.id === 'v8' && source.available)?.id || 'demo');
  } catch (error) {
    showNotice(error.message, true);
  }
}

start();
