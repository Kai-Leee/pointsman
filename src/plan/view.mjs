// Grayscale HTML view of a checked plan: slot schedule with estimated (and, when given, actual) bars,
// per-task time and cost, unexpressed links and the closing feedback list.
const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const clock = (s) => (s == null ? '—' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);
const money = (v) => (v == null ? '—' : v < 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`);
const share = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);

/** `report` is { validation, gaps, estimate, skip, feedback }; `actual` maps task id to { start, end } seconds. */
export function renderPlanView(report, { title = 'Pointsman plan', actual = null } = {}) {
  const { validation, gaps, estimate, skip, feedback } = report;
  const spans = [...estimate.schedule.map((s) => s.end), ...Object.values(actual ?? {}).map((a) => a.end), 1];
  const max = Math.max(...spans), at = (s) => `${(s / max) * 100}%`;
  const lanes = Array.from({ length: estimate.slots }, (_, slot) => estimate.schedule.filter((s) => s.slot === slot));
  const bar = (start, end, text, cls) => `<div class="seg ${cls}" style="left:${at(start)};width:${at(Math.max(end - start, max / 400))}"><span>${esc(text)}</span></div>`;
  const rows = lanes.map((items, slot) => `<div class="row"><span class="lab">slot ${String.fromCharCode(65 + slot)}</span><div class="lane">${items
    .map((s) => bar(s.start, s.end, `${s.task} · ${clock(s.end - s.start)}`, 'est')).join('')}</div></div>`).join('');
  const actualRow = actual ? `<div class="row"><span class="lab">actual</span><div class="lane">${Object.entries(actual)
    .map(([id, a]) => bar(a.start, a.end, `${id} · ${clock(a.end - a.start)}`, 'act')).join('')}</div></div>` : '';
  const taskRows = validation.order.map((id) => {
    const t = estimate.tasks[id], before = validation.predecessors[id];
    return `<tr><td>${esc(id)}</td><td>${esc(t.profile ?? '—')}</td><td>${before.length ? esc(before.join(', ')) : '—'}</td><td class="n">${clock(t.seconds)}${t.range ? ` <small>(${clock(t.range.seconds[0])}–${clock(t.range.seconds[1])})</small>` : ''}</td><td class="n">${money(t.usd)}</td>${actual?.[id] ? `<td class="n">${clock(actual[id].end - actual[id].start)}</td>` : actual ? '<td class="n">—</td>' : ''}</tr>`;
  }).join('');
  const tot = estimate.totals;
  const items = feedback.length ? feedback.map((f) => `<li><b>${esc(f.kind)}</b> ${esc(f.text)}</li>`).join('') : '<li>nothing left to close</li>';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title>
<style>
:root{--bg:#0b0b0b;--panel:#141414;--line:#2c2c2c;--ink:#ececec;--muted:#8d8d8d;--est:#6f6f6f;--act:#d6d6d6;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 ui-monospace,Menlo,monospace;padding:28px max(16px,env(safe-area-inset-left,0px))}
main{max-width:1000px;margin:0 auto;display:flex;flex-direction:column;gap:24px}h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 8px}
.kpis{display:flex;flex-wrap:wrap;gap:12px}.kpi{border:1px solid var(--line);background:var(--panel);border-radius:6px;padding:10px 14px}.kpi b{display:block;font-size:18px}
.chart{border:1px solid var(--line);background:var(--panel);border-radius:6px;padding:14px;overflow-x:auto}.row{display:grid;grid-template-columns:70px 1fr;gap:8px;align-items:center;min-width:640px;margin:4px 0}
.lab{color:var(--muted);font-size:12px}.lane{position:relative;height:28px;border-left:1px solid var(--line)}
.seg{position:absolute;top:3px;bottom:3px;border-radius:3px;overflow:hidden;transform-origin:left;animation:grow .9s ease-out both}.seg span{display:block;padding:0 6px;font-size:11px;line-height:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.est{background:var(--est)}.act{background:var(--act);color:#0b0b0b}@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){.seg{animation:none}}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500;font-size:12px}.n{text-align:right;white-space:nowrap}small{color:var(--muted)}
.wrap{overflow-x:auto}ul{margin:0;padding-left:18px}li b{color:var(--muted);font-weight:500;margin-right:6px}p{margin:0;color:var(--muted)}
</style></head><body><main>
<h1>${esc(title)}</h1>
<div class="kpis">
<div class="kpi">tasks<b>${validation.order.length}</b></div>
<div class="kpi">estimated wall<b>${clock(tot.makespan_seconds)}</b></div>
<div class="kpi">vs one at a time<b>${share(tot.time_saved_vs_sequential)} less</b></div>
<div class="kpi">estimated Claude cost<b>${money(tot.usd)}</b></div>
<div class="kpi">vs all ${esc(tot.baseline_profile)}<b>${share(tot.usd_saved_vs_all_baseline_profile)} less</b></div>
<div class="kpi">decompose?<b>${skip.skip ? `skip (${esc(skip.reason)})` : 'yes'}</b></div>
</div>
<p>Estimates are medians of recorded runs for each model profile; ranges show the recorded spread. They are not measurements of this run.</p>
<section class="chart"><h2>Placement and order</h2>${rows}${actualRow}</section>
<section><h2>Tasks</h2><div class="wrap"><table><thead><tr><th>task</th><th>profile</th><th>after</th><th class="n">est. time</th><th class="n">est. cost</th>${actual ? '<th class="n">actual</th>' : ''}</tr></thead><tbody>${taskRows}</tbody></table></div></section>
<section><h2>Links the plan does not express</h2>${gaps?.links?.length ? `<ul>${gaps.links.map((l) => `<li>${esc(l.task)} → needs ${esc(l.needs)}: ${esc(l.file)} imports ${esc(l.imports)}</li>`).join('')}</ul>` : `<p>none found in ${gaps?.scanned?.length ?? 0} scanned files</p>`}</section>
<section><h2>To close out</h2><ul>${items}</ul></section>
</main></body></html>
`;
}
