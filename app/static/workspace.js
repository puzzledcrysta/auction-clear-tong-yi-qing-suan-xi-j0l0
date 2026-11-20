import {query, readInput, encodeInput} from './api.js';
import {el, evidence, table} from './table.js';

const byId = id => document.getElementById(id);
const settings = JSON.parse(byId('settings').textContent);
const links = [...document.querySelectorAll('[data-module]')];
const body = byId('grid-data');
const alert = byId('notice');
const live = byId('state');
const action = document.querySelector('#source button[type=submit]');
const topExport = byId('export');
let selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
let result = null;
let inputs = {};
let reviewVersion = 0;
let renderEpoch = 0;
let activeView = null;
const filter = byId('filter');
const differences = byId('differences');

function filterTable() {
  if (!activeView) return;
  const {columns, rows, stage} = activeView;
  const query = filter.value.trim().toLocaleLowerCase();
  const selected = rows.filter(row => {
    if (stage === 'reconcile' && differences.checked && row.code === 'MATCH') return false;
    return !query || [row.key,row.id,row.line,row.code,row.target,row.status,
      settings.reasons[row.code],row.detail,row.note,row.kind,row.reason]
      .some(value => String(value ?? '').toLocaleLowerCase().includes(query));
  });
  byId('shown').textContent = `${selected.length} / ${rows.length}`;
  table(body, columns, selected);
}
filter.addEventListener('input', filterTable);
differences.addEventListener('change', filterTable);
const uploaded = new Map();

function notice(message, error = false) {
  alert.value = message;
  alert.classList.toggle('problem', error);
}

function tag(code) {
  return el('span', settings.reasons[code] || code, code === 'MATCH' ? 'state' : 'state problem');
}


function showEvidence(row) {
  const panel = byId('evidence-panel');
  const record = byId('evidence-key');
  const details = byId('signal');
  if (!row) {
    record.textContent = '';
    details.replaceChildren(el('p', '本批没有可采信记录', 'empty'));
    return;
  }
  record.textContent = row.key;
  const content = el('ol', undefined, panel.dataset.instrument);
  for (const item of row.proof) {
    const line = el('li');
    line.append(el('span', item.metric));
    line.append(el('strong', item.unit ? `${item.value} ${item.unit}` : item.value, 'measure'));
    content.append(line);
  }
  details.replaceChildren(content);
}

function inspect(row) {
  const button = el('button', '查看依据', 'btn');
  button.type = 'button';
  button.addEventListener('click', () => showEvidence(row));
  const raw = evidence('原始字段', row.raw);
  const cell = el('div');
  cell.append(button, raw);
  return cell;
}

function setRun(report) {
  result = report;
  byId('created').textContent = `${report.manifest.created.slice(0, 19).replace('T', ' ')} UTC`;
  showEvidence(report.accepted[0]);
  const id = result.manifest.run_id;
  byId('run-id').textContent = id.slice(0, 9);
  byId('run-id').title = id;
  topExport.hidden = false;
  topExport.href = `/api/export/${id}`;
  const values = {...result.counts, delta: result.book.delta, mismatched: result.book.mismatched};
  for (const cell of document.querySelectorAll('[data-count]')) cell.textContent = values[cell.dataset.count];
  live.textContent = `批次 ${id.slice(0, 9)} · ${result.balanced ? '记录已对齐' : '记录数不符'}`;
}

async function render() {
  const ticket = ++renderEpoch;
  const stage = selected;
  byId('phase').textContent = settings.tabs[stage];
  byId('review').hidden = true;
  byId('correction').hidden = true;
  for (const link of links) {
    if (link.dataset.module === stage) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (!result) return;
  const id = result.manifest.run_id;
  const raw = row => evidence('来源字段', row.raw);
  const key = [settings.key, 'key'];
  const line = ['行号', 'line', 'num'];
  try {
    let view, rows;
    if (stage === 'domain') {
      view = [key, [`成交总额 · ${settings.unit}`, 'amount', 'num'], line, ['明细依据', inspect]];
      rows = result.accepted;
    } else if (stage === 'quality') {
      view = [key, line, ['判定', row => tag(row.code)], ['说明', 'detail'], ['字段', raw]];
      rows = [...result.quarantine, ...result.suppressed].sort((a,b) => a.line-b.line);
    } else if (stage === 'reconcile') {
      view = [key, ['实际', 'amount', 'num'], ['外部账', 'reference', 'num'], ['差值', 'delta', 'num'], ['外部行', 'book_line', 'num'], ['结论', row => tag(row.code)]];
      rows = [...result.book.rows].sort((a,b) => Number(a.code === 'MATCH') - Number(b.code === 'MATCH'));
    } else if (stage === 'intake') {
      const intake = await query('/api/intake', inputs);
      view = [line, ['分类', 'kind'], ['字段', raw]];
      rows = [...intake.rows.map(row => ({...row,kind:'完整记录'})), ...intake.rejected.map(row => ({...row,kind:'坏行'})),
              ...intake.blank_lines.map(line => ({line,kind:'空白行',raw:[]})),
              ...intake.header_lines.map(line => ({line,kind:'重复表头',raw:[]}))].sort((a,b) => a.line-b.line);
    } else if (stage === 'contract') {
      const contract = await query('/api/contract', inputs);
      view = [key, line, ['修订', 'revision', 'num'], ['来源时刻 UTC', 'time'], ['字段', row => evidence('归一值', Object.entries(row.fields).map(([k,v]) => `${k} · ${v}`))]];
      rows = contract.accepted;
    } else if (stage === 'runs') {
      const runs = await query('/api/runs');
      view = [['指纹','id'], ['创建 UTC','created'], ['操作', row => {
        const current = row.id === id;
        const button = el('button',current ? '复算当前批' : '打开此批','btn');
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            if (current) {
              setRun(await query(`/api/runs/${id}/replay`, {}));
              notice('复算已核对');
            } else {
              const [past, original] = await Promise.all([
                query(`/api/runs/${row.id}`), query(`/api/runs/${row.id}/source`),
              ]);
              inputs = original;
              setRun(past);
              notice('已打开历史批次');
              await render();
            }
          }
          catch (error) { notice(error.message, true); }
          finally { button.disabled = false; }
        });
        return button;
      }]];
      rows = runs;
    } else if (stage === 'correction') {
      const list = await query(`/api/corrections/${id}`);
      view = [['冲销单','id', row => row.id.slice(0,9)], ['更正场次','target'], ['状态','status'],
              ['登记 UTC','created'], ['发布 UTC','published'],
              ['操作', row => correctionActions(row)]];
      rows = list.corrections;
      if (ticket === renderEpoch) {
        byId('correction').hidden = false;
        byId('correction-target').value = result.accepted[0]?.key || '';
        const timeline = await query(`/api/review/${id}`);
        const signed = timeline[0]?.decision === '确认';
        byId('correction-hint').textContent = signed
          ? '历史签核不可改写；本表单只登记晚到更正，并按更正影响另出冲销单。'
          : '批次须先在「市场签核」以“确认”结论签核后，才能登记晚到更正。';
      }
    } else {
      const timeline = await query(`/api/review/${id}`);
      view = [['版本','version','num'], ['结论','decision'], ['复核意见','note'], ['登记 UTC','changed']];
      rows = timeline;
      if (ticket === renderEpoch) {
        reviewVersion = timeline[0]?.version || 0;
        byId('review').hidden = false;
      }
    }
    if (ticket === renderEpoch) {
      if (activeView?.stage !== stage) filter.value = '';
      activeView = {stage, columns: view, rows};
      byId('tools').hidden = false;
      byId('only-differences').hidden = stage !== 'reconcile';
      filterTable();
    }
  } catch (error) {
    if (ticket === renderEpoch) notice(error.message, true);
  }
}

window.addEventListener('hashchange', () => {
  selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
  render();
});
byId('sample').addEventListener('click', async () => {
  const paths = ['shift', 'external'];
  try {
    const responses = await Promise.all(paths.map(name => fetch(`/api/samples/${name}`)));
    if (responses.some(item => !item.ok)) throw Error('样例暂时不可用');
    const files = await Promise.all(responses.map(item => item.arrayBuffer()));
    for (const [index,name] of ['source','book'].entries()) {
      const decoded = new TextDecoder('utf-8').decode(files[index]);
      byId(`${name}-csv`).value = decoded;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes:files[index]});
    }
    byId('source-file').value = '';
    byId('book-file').value = '';
    document.querySelector('#source details').open = true;
    notice('样例已载入');
  } catch (error) { notice(error.message, true); }
});
for (const name of ['source','book']) {
  byId(`${name}-file`).addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    action.disabled = true;
    try {
      const [text,bytes] = await readInput(file);
      byId(`${name}-csv`).value = text;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes});
      notice(`已读取 ${file.name}`);
    } catch (error) {
      event.target.value = '';
      notice(error.message, true);
    } finally { action.disabled = false; }
  });
}
byId('source').addEventListener('submit', async event => {
  event.preventDefault();
  const candidate = {};
  for (const [control,name] of [['source','data'],['book','book']]) {
    const text = byId(`${control}-csv`).value;
    const original = uploaded.get(control);
    if (original && text === original.text) candidate[`${name}_base64`] = encodeInput(original.bytes);
    else if (text.length || original) candidate[name] = text;
  }
  action.disabled = true;
  ++renderEpoch;
  notice('计算中');
  try {
    const report = await query('/api/runs', candidate);
    inputs = candidate;
    setRun(report);
    notice('批次已计算');
    await render();
  } catch (error) { notice(error.message, true); }
  finally { action.disabled = false; }
});
byId('review').addEventListener('submit', async event => {
  event.preventDefault();
  const id = result.manifest.run_id;
  const note = byId('review-note');
  try {
    await query(`/api/review/${id}`, {version: reviewVersion, decision: byId('decision').value, note: note.value});
    notice('复核已登记');
    note.value = '';
    await render();
  } catch (error) {
    notice(error.message, true);
    if (error.status === 409) await render();
  }
});

function statusTag(text) {
  return el('span', text, text === '已发布' ? 'state' : 'state problem');
}

function awardList(line) {
  const wrap = el('details');
  wrap.append(el('summary', '各买家获配调整'));
  const list = el('ul');
  for (const change of line.award_changes) {
    list.append(el('li', `${change.bidder}：${change.old_quantity} → ${change.new_quantity}（${change.quantity_delta} ${change.unit}）`));
  }
  wrap.append(list);
  return wrap;
}

function bookEvidence(check) {
  const wrap = el('details');
  wrap.append(el('summary', '外账按场核对'));
  const list = el('ul');
  const registered = [
    ['登记时原签核金额', check.registered_old],
    ['登记时更正后金额', check.registered_new],
  ];
  for (const [label, item] of registered) {
    list.append(el('li', `${label}：${item.reference ?? '—'}（${settings.reasons[item.code] || item.code}）`));
  }
  if (check.publish) {
    list.append(el('li', `发布重核更正后金额：${check.publish.reference ?? '—'}（${settings.reasons[check.publish.code] || check.publish.code}）`));
  }
  wrap.append(list);
  return wrap;
}

function showCorrection(voucher) {
  byId('evidence-key').textContent = voucher.correction_id.slice(0, 9);
  const root = el('div', undefined, 'panel__body');
  const head = el('p');
  head.append(statusTag(voucher.status));
  head.append(el('span', ` 目标场次 ${voucher.target} · 冲销合计 ${voucher.total_reversal} ${settings.unit}`));
  root.append(head);
  root.append(el('p', voucher.scope.delimitation, 'empty'));
  for (const line of voucher.lines) {
    const block = el('dl');
    const title = el('dt');
    title.append(el('strong', `场次 ${line.key}`));
    block.append(title);
    const dd = el('dd');
    dd.append(el('div', `原签核金额 ${line.old_amount} → 更正后 ${line.new_amount}，冲销 ${line.reversal_amount} ${settings.unit}`));
    dd.append(el('div', `统一清算价 ${line.old_clearing.value} → ${line.new_clearing.value}（${line.clearing_delta} ${line.old_clearing.unit}）`));
    dd.append(awardList(line));
    dd.append(bookEvidence(line.book_check));
    block.append(dd);
    root.append(block);
  }
  if (voucher.original_review?.length) {
    const review = voucher.original_review[0];
    root.append(el('p', `原签核：v${review.version} ${review.decision} · ${review.note}`, 'empty'));
  }
  byId('signal').replaceChildren(root);
}

function correctionActions(row) {
  const cell = el('div');
  const open = el('button', '查看冲销单', 'btn');
  open.type = 'button';
  open.addEventListener('click', async () => {
    try { showCorrection(await query(`/api/correction/${row.id}`)); }
    catch (error) { notice(error.message, true); }
  });
  cell.append(open);
  if (row.status !== '已发布') {
    const publish = el('button', '按场核对并发布', 'btn btn--primary');
    publish.type = 'button';
    publish.addEventListener('click', async () => {
      publish.disabled = true;
      try {
        const body = {};
        const book = byId('correction-book').value.trim();
        if (book) body.book = book;
        const response = await query(`/api/correction/${row.id}/publish`, body);
        notice(response.published ? '冲销单已发布' : '冲销单此前已发布');
        showCorrection(response.voucher);
        await render();
      } catch (error) { notice(error.message, true); }
      finally { publish.disabled = false; }
    });
    cell.append(publish);
  }
  return cell;
}

byId('correction').addEventListener('submit', async event => {
  event.preventDefault();
  const runId = result.manifest.run_id;
  const payload = {
    target: byId('correction-target').value.trim(),
    note: byId('correction-note').value,
    data: byId('correction-csv').value,
  };
  const book = byId('correction-book').value.trim();
  if (book) payload.book = book;
  try {
    const response = await query(`/api/corrections/${runId}`, payload);
    notice(response.created ? '冲销单已生成，外账按场核对通过后才能发布' : '同一更正已登记，返回既有冲销单');
    showCorrection(response.voucher);
    byId('correction-note').value = '';
    await render();
  } catch (error) { notice(error.message, true); }
});
render();
