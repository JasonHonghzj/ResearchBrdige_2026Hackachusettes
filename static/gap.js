/* ResearchBridge gap explorer. Counts and user selection travel together so a
 * brief can never silently describe a different pairing from the visible one. */
'use strict';
const $ = id => document.getElementById(id);
const S = { grid:null, gaps:[], rejects:[], val:null, scope:null, selected:null,
  request:0, controller:null, briefMarkdown:'' };
const esc = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => Number(value ?? 0).toLocaleString('en-US');
const TOPIC = '("Early Detection of Cancer"[MeSH Terms] OR "Early Diagnosis"[MeSH Terms])';
const DEST = {
  check: {panels:['p1'], note:'A research question, two reproducible PubMed searches.'},
  map: {panels:['p2','p3'], note:'Browse saved disease–method pairings in early-detection research.'},
  library: {panels:[], bridge:true, note:'Explore the separate 60-paper Hackachusetts starter set.'},
  brief: {panels:['p6'], note:'Take the selected pairing and its evidence into a research discussion.'},
  method: {panels:['p5','p4'], note:'Data coverage, search limitations and the analysis behind this prototype.'},
};
const navBtns = [...document.querySelectorAll('.nav button')];
let dest = 'check';
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function showDest(id, replace = false){
  if (!DEST[id]) id = 'check';
  dest = id;
  const d = DEST[id];
  navBtns.forEach(b => {
    const active = b.dataset.dest === id;
    b.setAttribute('aria-selected', String(active)); b.tabIndex = active ? 0 : -1;
  });
  $('view-gap').hidden = !!d.bridge;
  $('view-bridge').hidden = !d.bridge;
  document.querySelectorAll('#view-gap .panel').forEach(p => p.classList.toggle('on', d.panels.includes(p.id)));
  $('destnote').textContent = d.note;
  document.documentElement.lang = d.bridge ? ($('b-lang').value === 'zh' ? 'zh-Hant' : $('b-lang').value) : 'en';
  if (d.bridge && window.Bridge) window.Bridge.init();
  renderSelbar();
  if (location.hash !== '#' + id) history[replace ? 'replaceState' : 'pushState'](null, '', '#' + id);
}
navBtns.forEach((b, i) => {
  b.id = 'nav-' + b.dataset.dest;
  b.setAttribute('aria-controls', b.dataset.dest === 'library' ? 'view-bridge' : DEST[b.dataset.dest].panels.join(' '));
  b.addEventListener('click', () => showDest(b.dataset.dest));
  b.addEventListener('keydown', e => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    const next = delta ? (i + delta + navBtns.length) % navBtns.length : e.key === 'Home' ? 0 : e.key === 'End' ? navBtns.length - 1 : null;
    if (next === null) return;
    e.preventDefault(); navBtns[next].focus(); showDest(navBtns[next].dataset.dest);
  });
});
for (const [id, d] of Object.entries(DEST)) for (const panel of d.panels) $(panel).setAttribute('aria-labelledby', 'nav-' + id);
window.addEventListener('popstate', () => showDest(location.hash.slice(1), true));

function cancelCheck(){
  S.request++; S.controller?.abort(); S.controller = null;
  $('ckRun').disabled = false; $('ckRun').textContent = 'Check PubMed'; $('ckOut').removeAttribute('aria-busy');
}
function renderSelbar(){
  const x = S.selected;
  $('selbar').hidden = !x || !['map','brief','check'].includes(dest);
  if (!x) return;
  $('selval').textContent = x.problem + ' × ' + x.method;
  $('selbar').querySelector('.sel-l').textContent = x.source === 'map' ? 'Saved pairing' : 'Checked pairing';
}
function clearSelection(){
  cancelCheck(); S.selected = null;
  $('ckProblem').value = ''; $('ckMethod').value = ''; $('ckOut').innerHTML = '';
  renderSelection();
}
$('selclear').addEventListener('click', clearSelection);
function renderSelection(){
  renderSelbar(); renderGrid(); renderShortlist(); renderGap(); renderBrief();
}
function selectPair(row, source){
  cancelCheck();
  S.selected = {...row, source, tolerance:row.tolerance ?? 2};
  $('ckProblem').value = row.problem; $('ckMethod').value = row.method;
  renderSelection(); renderCheckResult();
}
function queriesFor(x){
  const maturity = `"${x.problem}"[MeSH Terms] AND "${x.method}"[MeSH Terms]`;
  return x.queries || {maturity, gap:maturity + ' AND ' + TOPIC};
}
const pubmed = query => 'https://pubmed.ncbi.nlm.nih.gov/?term=' + encodeURIComponent(query);
function queryLinks(x){
  const q = queriesFor(x);
  return `<div class="query-links"><a href="${esc(pubmed(q.maturity))}" target="_blank" rel="noopener noreferrer">Open overall PubMed search ↗</a><a href="${esc(pubmed(q.gap))}" target="_blank" rel="noopener noreferrer">Open early-detection search ↗</a></div>`;
}
function outcome(x){
  if (x.gap_papers > (x.tolerance ?? 2)) return {label:'Already studied', note:'Early-detection papers already appear for this pairing. Review them before narrowing the research question.'};
  if (x.maturity === 0) return {label:'Untried pairing', note:'No indexed use appears for the overall pairing. A low early-detection count alone gives no evidence of feasibility.'};
  if (x.maturity < 50) return {label:'Limited overall literature', note:'Few papers appear for the overall pairing. Ask a specialist whether the method is appropriate before treating this as an opportunity.'};
  return {label:'Candidate for review', note:'The overall pairing appears in the literature, with few results for early detection. Review the papers, synonyms and feasibility with a specialist.'};
}
function sourceLabel(x){
  if (x.source === 'map') return 'Saved map counts · collected during the build';
  const date = x.checked_utc ? new Date(x.checked_utc).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'}) : '';
  return (x.cached ? 'Cached PubMed check' : 'Fresh PubMed check') + (date ? ' · ' + date : '');
}
function renderCheckResult(){
  const x = S.selected;
  if (!x) return;
  const o = outcome(x), q = queriesFor(x);
  $('ckOut').innerHTML = `<div class="source-details">
    <div class="result-head"><strong>${esc(o.label)}</strong><span class="scope-badge">${esc(sourceLabel(x))}</span></div>
    <dl class="kv"><dt>Overall pairing</dt><dd>${fmt(x.maturity)} papers</dd><dt>For early detection</dt><dd>${fmt(x.gap_papers)} papers</dd><dt>Candidate threshold</dt><dd>≤${x.tolerance} early-detection papers</dd></dl>
    <p class="source-note">${esc(o.note)}</p>${queryLinks(x)}
    <div class="actions"><button class="btn" data-nav="brief">Build this brief →</button><button class="btn ghost" data-fresh>Refresh PubMed</button></div>
    <details class="source-details"><summary>Exact search queries</summary><div class="src mono" style="margin-top:10px">${esc(q.maturity)}<br><br>${esc(q.gap)}</div></details></div>`;
}

async function get(path, options){
  const r = await fetch(path, options);
  if (!r.ok) throw new Error('The saved data could not be loaded (HTTP ' + r.status + ').');
  return r.json();
}
function renderCorpus(){
  const prov = (S.scope.provenance || []).filter(p => p.strategy === 'per-year slices, deduplicated by PMID');
  $('heroPapers').textContent = fmt(S.grid.n_papers);
  $('heroCandidates').textContent = fmt(S.scope.confirmed_gaps);
  $('gAllLabel').textContent = `Show all ${S.grid.problems.length} × ${S.grid.methods.length}`;
  $('plog').innerHTML = prov.map(p => `<li><span class="ok">✓</span><span class="lbl">${esc((p.years || []).join('–'))}<span class="sub">${esc(p.strategy)} · ${Math.round(p.abstract_coverage * 100)}% abstracts · ${Math.round(p.mesh_coverage * 100)}% MeSH</span><span class="sub">Retrieved ${esc(p.retrieved_utc || 'during build')}</span></span><span class="num">${fmt(p.retrieved_unique)} unique papers</span></li>`).join('') +
    `<li><span class="ok">✓</span><span class="lbl">${fmt(S.scope.cells_checked)} candidate pairings checked<span class="sub">Saved counts from overall and early-detection PubMed searches. The map corpus is deduplicated across year boundaries.</span></span></li>`;
  const g = S.grid;
  $('corpuskv').innerHTML = `<dt>Papers</dt><dd>${fmt(g.n_papers)}</dd><dt>Disease terms</dt><dd>${g.problems.length}</dd><dt>Method terms</dt><dd>${g.methods.length}</dd><dt>Studied cells</dt><dd>${fmt(g.filled)} / ${fmt(g.cells)}</dd><dt>Low-result pairings</dt><dd>${fmt(S.scope.confirmed_gaps)} / ${fmt(S.scope.cells_checked)} checked</dd>`;
}

const SYNONYM = {
  cancer:['neoplasm','carcinoma','melanoma','adenoma','dysplasia','polyp'],
  tumour:['neoplasm','carcinoma'], tumor:['neoplasm','carcinoma'],
  ai:['learning','neural','artificial','support vector','algorithm','fuzzy'],
  ml:['learning','neural','support vector','algorithm'],
  'machine learning':['learning','neural','algorithm'],
  dna:['dna','sequence','polymerase','nucleic','genotyp','methylat'],
  gene:['gene','genom','genotyp','transcriptome','pedigree','sequence'], genetic:['gene','genom','genotyp','pedigree'],
  protein:['proteom','protein'], 'mass spec':['spectrometry','chromatograph'],
  brain:['alzheimer','parkinson','dementia','stroke'], neuro:['alzheimer','parkinson','dementia','stroke'],
  heart:['cardiovascular','myocardial','hypertension','heart'], cardio:['cardiovascular','myocardial','heart'],
  lung:['lung','pulmonary'], liver:['liver','hepat','cirrhosis'], kidney:['kidney','renal'], diabetes:['diabet'],
  blood:['liquid biopsy','occult','nucleic'], breath:['breath'],
};
function needles(q){
  const out = q.length >= 3 ? [q] : [];
  for (const k in SYNONYM) if (k === q || (q.length >= 3 && (k.includes(q) || q.includes(k)))) out.push(...SYNONYM[k]);
  return out.length ? [...new Set(out)] : [q];
}
function visibleAxes(){
  const q = $('gFilter').value.trim().toLowerCase(), all = $('gAll').checked;
  let P = S.grid.problems, M = S.grid.methods;
  if (q){
    const ns = needles(q), hit = x => ns.some(n => x.name.toLowerCase().includes(n));
    const hp = P.filter(hit), hm = M.filter(hit);
    if (!hp.length && !hm.length) return {P:[], M:[], q, all};
    if (hp.length) P = hp;
    if (hm.length) M = hm;
  } else if (!all) {P = P.slice(0,15); M = M.slice(0,12);}
  return {P,M,q,all};
}
function bucket(n){return n <= 0 ? 0 : n < 10 ? 1 : n < 40 ? 2 : n < 100 ? 3 : n < 400 ? 4 : 5;}
function renderGrid(){
  if (!S.grid) return;
  const {P,M,q,all} = visibleAxes(), g = S.grid, cur = S.selected;
  const pi = new Map(g.problems.map((x,i) => [x.name,i])), mi = new Map(g.methods.map((x,i) => [x.name,i]));
  const counts = new Map(g.counts.map(c => [c[0]+'|'+c[1],c[2]]));
  const confirmed = new Map(S.gaps.map(x => [x.problem+'|'+x.method,x]));
  $('map').innerHTML = P.length ? '<thead><tr><th scope="col">Disease / method</th>' + M.map(m => `<th class="col" scope="col"><span title="${esc(m.name)}">${esc(m.name)}</span></th>`).join('') + '</tr></thead><tbody>' + P.map(p =>
    `<tr><th class="row" scope="row" title="${esc(p.name)}">${esc(p.name)}</th>` + M.map(m => {
      const n = counts.get(pi.get(p.name)+'|'+mi.get(m.name)) || 0;
      const gap = n === 0 ? confirmed.get(p.name+'|'+m.name) : null;
      const picked = gap && cur && cur.problem === p.name && cur.method === m.name;
      const label = `${p.name} × ${m.name}: ${n} corpus papers` + (gap ? `; ${gap.gap_papers} early-detection results in saved PubMed search` : '; click to check PubMed');
      return `<td><button class="cell c${bucket(n)} ${gap ? picked ? 'flag pick' : 'flag' : ''}" data-problem="${esc(p.name)}" data-method="${esc(m.name)}" data-n="${n}" data-f="${gap ? 1 : 0}" data-mat="${gap?.maturity ?? 0}" data-gp="${gap?.gap_papers ?? 0}" aria-label="${esc(label)}"></button></td>`;
    }).join('') + '</tr>').join('') + '</tbody>' : '';
  $('gCount').textContent = `${P.length} × ${M.length} of ${g.problems.length} × ${g.methods.length}`;
  document.querySelector('#p2 .axisnote').textContent = !P.length ? `No terms match “${q}”. Try cancer, learning or a MeSH term.` :
    `${fmt(P.length*M.length)} cells shown${q ? ' for “'+q+'”' : all ? ' · full map' : ' · busiest diseases and methods'}. Counts are from the saved early-detection corpus. Select a ringed cell for saved evidence; select any other cell to check it.`;
}
function curated(){
  const seen = new Set();
  return S.gaps.map((x,i) => ({...x,index:i})).filter(x => {
    if (x.maturity < 50 || seen.has(x.problem)) return false;
    seen.add(x.problem); return true;
  }).slice(0,6);
}
function renderShortlist(){
  if (!S.grid) return;
  const cur = S.selected;
  $('shortlist').innerHTML = curated().map(x => `<button class="pick-card" data-pick="${x.index}" aria-pressed="${!!cur && cur.problem === x.problem && cur.method === x.method}"><strong>${esc(x.problem)}</strong><span>${esc(x.method)}</span><small>${fmt(x.maturity)} overall · ${x.gap_papers} early detection →</small></button>`).join('');
}
function renderGap(){
  const x = S.selected;
  if (!x){
    $('gapcard').innerHTML = '<p class="source-note">Select a saved pairing above, or run a PubMed check to see its evidence here.</p>';
    $('gapmeta').innerHTML = '<dt>Selection</dt><dd>No checked pairing</dd>';
  } else {
    const o = outcome(x), rank = S.gaps.findIndex(g => g.problem === x.problem && g.method === x.method);
    $('gapcard').innerHTML = `<div class="gaphead"><b>${esc(x.problem)}</b><span class="x">×</span><b>${esc(x.method)}</b></div><p class="source-note">${esc(sourceLabel(x))}</p><div class="metrics"><div><strong>${fmt(x.maturity)}</strong><span>overall PubMed papers</span></div><div><strong>${fmt(x.gap_papers)}</strong><span>early-detection papers</span></div></div><span class="scope-badge">${esc(o.label)}</span><p class="source-note">${esc(o.note)}</p>${queryLinks(x)}<div class="actions"><button class="btn" data-nav="brief">Build this brief →</button></div>`;
    $('gapmeta').innerHTML = `<dt>Data source</dt><dd>${x.source === 'map' ? 'Saved map' : x.cached ? 'Cached check' : 'Fresh check'}</dd><dt>Threshold</dt><dd>≤${x.tolerance} early-detection papers</dd><dt>Overall-count rank</dt><dd>${rank >= 0 ? (rank+1)+' / '+S.gaps.length : 'Custom pairing'}</dd>`;
  }
  $('rejects').innerHTML = S.rejects.slice(0,4).map(r => `<div style="font-size:12.5px;color:var(--ink-2)"><b style="color:var(--ink)">${esc(r.problem)} × ${esc(r.method)}</b><br>${fmt(r.gap_papers)} early-detection results in saved PubMed search</div>`).join('');
}
function renderValidation(){
  const v = S.val || {}, neg = v.established_negative_result;
  const rows = neg ? [['Flagged by bridge score',neg.flagged_real],['Rejected by bridge score',neg.rejected_real]].map(([label,value]) => {
    const match = String(value).match(/(\d+)\/(\d+)/);
    if (!match || +match[2] === 0) return null;
    return {label,real:+match[1],n:+match[2],pct:Math.round(+match[1]/+match[2]*100)};
  }).filter(Boolean) : [];
  $('bars').innerHTML = rows.length ? rows.map(r => `<div class="bar"><span class="bl">${esc(r.label)}<br><small>n = ${fmt(r.n)}</small></span><span class="track"><span class="fill" style="width:${r.pct}%"></span></span><span class="bv">${r.pct}%<br><small>${r.real} pairings</small></span></div>`).join('') : '<p class="source-note">Ranking evaluation is unavailable.</p>';
  $('barnote').textContent = neg ? `Scale 0–100%. The bridge score did not improve selection (lift ${neg.lift}×). The product therefore orders candidates by their overall paper counts. These counts do not predict future discoveries.` : 'The prototype makes no prediction-performance claim.';
  $('valkv').innerHTML = `<dt>Pairings checked</dt><dd>${fmt(S.scope.cells_checked)}</dd><dt>With ≤2 results</dt><dd>${fmt(S.scope.confirmed_gaps)}</dd><dt>Candidate order</dt><dd>Overall paper count</dd><dt>Historical validation</dt><dd>Pending remeasurement</dd>`;
  $('valcaveat').textContent = v.status === 'pending_remeasurement' ? 'The earlier 2× historical lift was withdrawn after changes to the corpus, axes and gap definition. Corrected historical validation is pending.' : 'See the saved analysis for the applicable validation status.';
}

function briefContent(x){
  const q = queriesFor(x), o = outcome(x);
  return `# ${x.method} × ${x.problem}\n\nResearchBridge · Literature check brief\n\n## Result\n\n${o.label}. The overall PubMed MeSH search returns ${fmt(x.maturity)} papers; restricting it to early detection returns ${fmt(x.gap_papers)}. The candidate threshold is at most ${x.tolerance} early-detection papers.\n\n${o.note}\n\n## Evidence source\n\n${sourceLabel(x)}${x.checked_utc ? '\n\nRecorded check time: '+x.checked_utc : '\n\nThe map snapshot does not record a check time for each pairing. Refresh PubMed for a dated check.'}\n\n## Reproduce the searches\n\nOverall pairing:\n${q.maturity}\n${pubmed(q.maturity)}\n\nEarly detection:\n${q.gap}\n${pubmed(q.gap)}\n\n## What to review next\n\nRead the returned papers and broaden the search with alternative terms, titles and abstracts. Ask a domain specialist whether the low result count reflects a useful question, an indexing gap or a known feasibility constraint.\n\n## Limits\n\nThese are counts of indexed papers, not evidence that a method works. A MeSH query can miss recent or differently indexed work. Low counts do not establish worldwide novelty, feasibility or clinical effectiveness. The early-detection topic is defined as Early Detection of Cancer OR Early Diagnosis. This brief does not include a collaborator recommendation.\n`;
}
function renderBrief(){
  const x = S.selected;
  $('briefToolbar').hidden = !x; $('briefStatus').textContent = '';
  if (!x){
    S.briefMarkdown = '';
    $('brief').className = 'empty-state';
    $('brief').innerHTML = '<p>Choose a saved pairing or complete a PubMed check to build a brief with matching evidence.</p><button class="btn" data-nav="map">Choose a saved pairing →</button>';
    return;
  }
  const o = outcome(x), q = queriesFor(x);
  S.briefMarkdown = briefContent(x);
  $('brief').className = 'brief';
  $('brief').innerHTML = `<div class="bh"><span class="el">ResearchBridge · Literature check brief</span><h3>${esc(x.method)} × ${esc(x.problem)}</h3><p class="source-note">${esc(sourceLabel(x))}</p></div><span class="scope-badge">${esc(o.label)}</span><h4>The research question</h4><p>What is known about ${esc(x.method)} for early detection of ${esc(x.problem)}?</p><h4>What the searches return</h4><p><b>${fmt(x.maturity)}</b> papers match the overall disease–method pairing. With the early-detection topic added, the same pairing returns <b>${fmt(x.gap_papers)}</b>. The candidate threshold is at most ${x.tolerance} early-detection papers.</p><p>${esc(o.note)}</p><h4>Reproduce the evidence</h4>${queryLinks(x)}<details class="source-details"><summary>View exact queries</summary><div class="src mono" style="margin-top:10px">${esc(q.maturity)}<br><br>${esc(q.gap)}</div></details><h4>Next research discussion</h4><p>Review the returned papers and broaden the search with synonyms, titles and abstracts. Ask a specialist whether the low count reflects a useful question, an indexing gap or a known feasibility constraint.</p><h4>Scope and limitations</h4><p>These counts show indexed research, not that a method is effective. MeSH indexing and the search definition can miss relevant work. Low counts do not establish worldwide novelty, feasibility or clinical effectiveness.</p><p>The topic uses <i>Early Detection of Cancer</i> or <i>Early Diagnosis</i>. ${x.source === 'map' ? 'These are saved map counts; refresh PubMed for a dated check.' : 'The recorded check time is '+esc(x.checked_utc || 'unavailable')+'.'}</p>`;
}
$('downloadBrief').addEventListener('click', () => {
  if (!S.selected) return;
  const url = URL.createObjectURL(new Blob([S.briefMarkdown], {type:'text/markdown;charset=utf-8'}));
  const a = Object.assign(document.createElement('a'), {href:url, download:'researchbridge-'+S.selected.problem.toLowerCase().replace(/[^a-z0-9]+/g,'-')+'.md'});
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  $('briefStatus').textContent = 'Markdown brief downloaded.';
});
$('printBrief').addEventListener('click', () => window.print());

async function runCheck(fresh = false){
  cancelCheck();
  const problem = $('ckProblem').value.trim(), method = $('ckMethod').value.trim();
  if (problem.length < 2 || method.length < 2){
    $('ckOut').innerHTML = '<div class="err">Enter both a disease and a method, or choose a saved example below.</div>'; return;
  }
  S.selected = null; renderSelection();
  const request = S.request, controller = new AbortController(); S.controller = controller;
  const timeout = setTimeout(() => controller.abort(),25000);
  $('ckRun').disabled = true; $('ckRun').textContent = 'Checking…';
  $('ckOut').setAttribute('aria-busy','true');
  $('ckOut').innerHTML = '<p class="loading">Checking PubMed. A new query can take a few seconds…</p>';
  try {
    const response = await fetch('/api/gap/check?' + new URLSearchParams({problem,method,fresh:String(fresh)}), {signal:controller.signal});
    const data = await response.json();
    if (request !== S.request) return;
    if (!response.ok){
      const detail = data.detail;
      const message = typeof detail === 'string' ? detail : detail?.error || 'This pairing could not be checked.';
      throw new Error(message + (detail?.detail ? ' '+detail.detail : ''));
    }
    selectPair(data,'check');
  } catch(e){
    if (request !== S.request) return;
    const message = e.name === 'AbortError' ? 'PubMed is taking longer than expected. Try again, or explore the saved pairings.' : e.message;
    $('ckOut').innerHTML = `<div class="err">${esc(message)}<div class="actions"><button class="btn ghost" data-nav="map">Explore saved pairings →</button></div></div>`;
  } finally {
    clearTimeout(timeout);
    if (request === S.request){$('ckRun').disabled = false; $('ckRun').textContent = 'Check PubMed'; $('ckOut').removeAttribute('aria-busy'); S.controller = null;}
  }
}
$('ckRun').addEventListener('click', () => runCheck());
for (const id of ['ckProblem','ckMethod']){
  $(id).addEventListener('keydown', e => {if(e.key === 'Enter'){e.preventDefault(); runCheck();}});
  $(id).addEventListener('input', () => {cancelCheck(); S.selected = null; $('ckOut').innerHTML = ''; renderSelection();});
}
document.addEventListener('click', e => {
  const nav = e.target.closest('[data-nav]');
  if (nav) {showDest(nav.dataset.nav); window.scrollTo({top:0,behavior:reducedMotion() ? 'instant':'smooth'});}
  const pick = e.target.closest('[data-pick]');
  if (pick && S.gaps[+pick.dataset.pick]){
    selectPair(S.gaps[+pick.dataset.pick],'map');
    if (!pick.closest('#checkExamples')) $('p3').scrollIntoView({behavior:reducedMotion() ? 'instant':'smooth',block:'start'});
  }
  if (e.target.closest('[data-fresh]')) runCheck(true);
});
for (const id of ['gFilter','gAll']) $(id).addEventListener('input', renderGrid);
$('map').addEventListener('click', e => {
  const cell = e.target.closest('.cell'); if (!cell) return;
  const row = S.gaps.find(x => x.problem === cell.dataset.problem && x.method === cell.dataset.method);
  if (cell.dataset.f === '1' && row){selectPair(row,'map'); $('p3').scrollIntoView({behavior:reducedMotion() ? 'instant':'smooth',block:'start'});}
  else {clearSelection(); $('ckProblem').value = cell.dataset.problem; $('ckMethod').value = cell.dataset.method; showDest('check'); $('ckRun').focus();}
  $('tip').style.opacity = '0';
});
function showTip(cell){
  const r = cell.getBoundingClientRect();
  $('tip').innerHTML = `<strong>${esc(cell.dataset.problem)}</strong><br>× ${esc(cell.dataset.method)}<br>${cell.dataset.f === '1' ? `${fmt(cell.dataset.mat)} overall papers<br>${cell.dataset.gp} early-detection results · saved PubMed check` : `${fmt(cell.dataset.n)} papers in the early-detection corpus`}`;
  $('tip').style.opacity = '1';
  $('tip').style.left = Math.max(8,Math.min(r.left+r.width/2-115,innerWidth-246))+'px';
  const above = r.top > 110;
  $('tip').style.top = (above ? r.top-8 : r.bottom+8)+'px';
  $('tip').style.transform = above ? 'translateY(-100%)':'none';
}
for (const event of ['mouseover','focusin']) $('map').addEventListener(event,e => {const c=e.target.closest('.cell'); if(c) showTip(c);});
for (const event of ['mouseout','focusout']) $('map').addEventListener(event,() => $('tip').style.opacity='0');

// Explicitly illustrative. Timers affect only these fixed example elements.
const claims = [...document.querySelectorAll('#claims .claim')];
let walkthroughTimers = [];
function resetWalkthrough(){
  walkthroughTimers.forEach(clearTimeout); walkthroughTimers = [];
  claims.forEach(c => {c.dataset.state='pending'; c.querySelector('.mk').textContent='·'; c.querySelector('.why').textContent='';});
  $('verdict').hidden = true; $('runv').disabled = false;
  const mark = document.querySelector('#srcbox mark'); if(mark) mark.outerHTML='<span data-hl>'+mark.innerHTML+'</span>';
}
$('runv').addEventListener('click', () => {
  resetWalkthrough(); $('runv').disabled = true;
  claims.forEach((c,i) => walkthroughTimers.push(setTimeout(() => {
    const pass = c.dataset.v === 'pass'; c.dataset.state=pass?'pass':'fail';
    c.querySelector('.mk').textContent=pass?'✓':'✕';
    c.querySelector('.why').textContent=pass?'Scripted example: supporting text shown':'Scripted example: no supporting text';
    const highlight = document.querySelector('#srcbox [data-hl]');
    if(i===0 && highlight) highlight.outerHTML='<mark>'+highlight.innerHTML+'</mark>';
    if(i===claims.length-1){$('verdict').hidden=false; $('runv').disabled=false;}
  },reducedMotion()?0:420*(i+1))));
});
$('resetv').addEventListener('click', resetWalkthrough);
$('gotoGate').addEventListener('click', () => $('p4').scrollIntoView({behavior:reducedMotion()?'instant':'smooth',block:'start'}));

async function boot(){
  try {
    const [grid,gaps,rejected,val,scope] = await Promise.all([
      get('/api/gap/grid'), get('/api/gap/gaps?limit=500&min_maturity=0'),
      get('/api/gap/gaps/rejected?limit=20').catch(() => ({rejected:[]})),
      get('/api/gap/validation').catch(() => ({status:'unavailable'})), get('/api/gap/scope'),
    ]);
    S.grid=grid; S.gaps=gaps.gaps; S.rejects=rejected.rejected; S.val=val; S.scope=scope;
    renderCorpus(); renderSelection(); renderValidation();
    const examples = [['Obesity','Polymerase Chain Reaction'],['Sepsis','Metabolomics'],['Parkinson Disease','Mass Spectrometry']];
    let indices = examples.map(([p,m]) => S.gaps.findIndex(x => x.problem===p && x.method===m)).filter(i => i>=0);
    if (!indices.length) indices=curated().slice(0,3).map(x=>x.index);
    $('checkExamples').innerHTML = '<span class="source-note" style="margin:0;align-self:center">Try saved evidence:</span>'+indices.map(i=>`<button data-pick="${i}">${esc(S.gaps[i].problem)} × ${esc(S.gaps[i].method)}</button>`).join('');
    const options = (id,terms) => $(id).innerHTML=terms.map(x=>`<option value="${esc(x.name)}"></option>`).join('');
    options('dlProblems',grid.problems); options('dlMethods',grid.methods);
  } catch(e){
    const message = `<div class="err">${esc(e.message)} Refresh the page to retry. New PubMed checks and the Library may still be available.</div>`;
    $('shortlist').innerHTML=message; $('gapcard').innerHTML=message; $('plog').innerHTML='<li>Saved corpus unavailable.</li>';
    renderBrief();
  }
}
showDest(location.hash === '#explorer' ? 'library' : location.hash.slice(1),true);
renderBrief(); boot();
