/* Evidence explorer: the ResearchBridge engine behind /api/bridge/*.
 *
 * No framework, no build step, matching index.html. Every API value goes
 * through esc() before reaching innerHTML, and only https: links are rendered.
 * UI strings come from the teammate's i18n table (/api/bridge/meta), so the
 * explorer stays trilingual; paper titles and abstracts keep their source language.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const MAX_SAVED = 4;
  const EXAMPLES = ['example_medication', 'example_care', 'example_privacy', 'example_protein'];
  const WEB_TEXT = {
    en: { empty: 'No matching papers in this starter set. Try a suggested keyword or another query.',
      compare_note: 'Compare up to four saved papers using their titles and abstracts. Your saved list stays available when you search again.' },
    zh: { empty: '此入門資料集中沒有符合的文獻。請嘗試建議關鍵字或其他查詢。',
      compare_note: '依題名及摘要比較最多四篇已儲存文獻。再次搜尋會保留比較清單。' },
    es: { empty: 'No hay artículos coincidentes en este conjunto inicial. Prueba una palabra sugerida u otra consulta.',
      compare_note: 'Compara hasta cuatro artículos guardados por sus títulos y resúmenes. La selección se conserva al buscar de nuevo.' },
  };

  const state = {
    ready: false, lang: 'en', text: {}, meta: null,
    q: '', mode: 'tfidf', method: 'auto', cue: 'all',
    saved: [],            // PMIDs, order preserved, max 4
    titles: {},           // pmid -> title, for lists outside the current results
    lastResults: [],
  };

  /* ---------- helpers ---------- */
  const esc = v => String(v ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safeUrl = u => { try { return new URL(u).protocol === 'https:' ? u : ''; } catch { return ''; } };
  const link = (href, text) => { const u = safeUrl(href); return u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : ''; };

  /** Fill a Python-style template: {name} and {name:.3f}. */
  function t(key, vars = {}) {
    const tpl = state.text[key] ?? key;
    return tpl.replace(/\{(\w+)(?::\.(\d)f)?\}/g, (m, k, d) =>
      k in vars ? (d != null && typeof vars[k] === 'number' ? vars[k].toFixed(+d) : String(vars[k])) : m);
  }

  async function api(path, body) {
    const opts = body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(path, opts);
    if (!r.ok) {
      let detail = `${r.status} ${r.statusText}`;
      try { const j = await r.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
      throw new Error(detail);
    }
    return r;
  }
  const getJSON = async (path, params) => (await api(path + '?' + new URLSearchParams(params))).json();
  const postJSON = async (path, body) => (await api(path, body)).json();

  function setStatus(id, msg, isErr = false) {
    const el = $(id); el.textContent = msg; el.classList.toggle('err', isErr);
  }

  /* ---------- i18n ---------- */
  function applyText() {
    document.querySelectorAll('#view-bridge [data-t]').forEach(el => {
      const v = state.text[el.dataset.t]; if (v) el.textContent = v;
    });
    document.querySelectorAll('#view-bridge [data-tp]').forEach(el => {
      const v = state.text[el.dataset.tp]; if (v) el.placeholder = v;
    });
    document.documentElement.lang = { en: 'en', zh: 'zh-Hant', es: 'es' }[state.lang];
  }

  async function loadMeta(lang) {
    const prev = state.text;
    state.meta = await getJSON('/api/bridge/meta', { lang });
    state.lang = lang; state.text = { ...state.meta.text, ...WEB_TEXT[lang] };
    // Translate a built-in example query; user-authored goals are left untouched.
    const ex = EXAMPLES.find(k => prev[k] && prev[k] === state.q);
    if (ex) { state.q = state.text[ex]; $('b-q').value = state.q; }
    const s = state.meta.stats;
    $('b-stats').textContent = state.lang === 'en'
      ? `${s.papers} records · ${s.abstracts} official abstracts · ${s.institutions} institutions.`
      : `${s.papers} ${t('metric_papers').toLowerCase()} · ${s.abstracts} ${t('metric_abstracts').toLowerCase()} · ${s.institutions} ${t('metric_institutions').toLowerCase()}.`;
    $('b-method').innerHTML = `<option value="auto">${esc(t('auto_method'))}</option>` +
      state.meta.methods.map(m => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join('');
    $('b-method').value = state.method;
    applyText();
  }

  /* ---------- saved / compare list ---------- */
  function toggleSaved(pmid, title) {
    const i = state.saved.indexOf(pmid);
    if (i >= 0) state.saved.splice(i, 1);
    else if (state.saved.length < MAX_SAVED) state.saved.push(pmid);
    if (title) state.titles[pmid] = title;
    refreshSaveButtons();
  }

  function refreshSaveButtons() {
    $('b-count').textContent = `(${state.saved.length})`;
    document.querySelectorAll('#view-bridge [data-save]').forEach(b => {
      const on = state.saved.includes(b.dataset.save);
      b.textContent = t(on ? 'remove' : 'save');
      b.setAttribute('aria-pressed', String(on));
      b.disabled = !on && state.saved.length >= MAX_SAVED;
    });
  }

  /* ---------- paper card ---------- */
  function paperCard(p, rank, { bridge = false } = {}) {
    state.titles[p.pmid] = p.title;
    const on = state.saved.includes(p.pmid);
    const score = p.score == null ? '' : ' · ' + t(bridge ? 'bridge_rank' : 'score', { score: p.score });
    let body = '';
    if (bridge) {
      body += p.method_evidence ? `<div class="ev"><q>${esc(p.method_evidence)}</q><cite>${esc(t('method_evidence'))}</cite></div>` : '';
      body += p.bridge_evidence ? `<div class="ev"><q>${esc(p.bridge_evidence)}</q><cite>${esc(t('cue_evidence'))}</cite></div>` : '';
    } else if (p.excerpt) {
      body = `<div class="ev"><q>${esc(p.excerpt)}</q><cite>${esc(t('excerpt'))} · PMID ${esc(p.pmid)}</cite></div>`;
    } else {
      body = `<p class="meta">${esc(t('no_abstract'))}</p>`;
    }
    const insts = p.institutions.length
      ? `<div class="insts">${esc(t('affiliations', { count: p.institutions.length }))}: ${p.institutions.slice(0, 6)
          .map(i => `<span class="chip n">${esc(i.name)}${i.city ? ' · ' + esc(i.city) : ''}</span>`).join('')}${p.institutions.length > 6 ? ` +${p.institutions.length - 6}` : ''}</div>`
      : '';
    return `<article class="card paper">
      <div class="ph"><h4>${String(rank).padStart(2, '0')} · ${esc(p.title)}</h4>
        <button class="btn ghost sm" data-save="${esc(p.pmid)}" aria-pressed="${on}" ${!on && state.saved.length >= MAX_SAVED ? 'disabled' : ''}>${esc(t(on ? 'remove' : 'save'))}</button></div>
      <p class="meta">${esc(p.journal)} · PMID ${esc(p.pmid)}${esc(score)}</p>
      ${body}${insts}
      <div class="links">${link(p.source_url, t('pubmed'))}${p.doi ? link('https://doi.org/' + encodeURI(p.doi), t('doi')) : ''}</div>
    </article>`;
  }

  function bindSaves(container) {
    container.querySelectorAll('[data-save]').forEach(b =>
      b.addEventListener('click', () => toggleSaved(b.dataset.save, state.titles[b.dataset.save])));
  }

  /* ---------- export ---------- */
  function exportControls(id, kind, params) {
    const box = $(id); box.hidden = false;
    box.innerHTML = `<label class="field"><span>${esc(t('export_format'))}</span>
        <select class="sel"><option value="csv">CSV</option><option value="html">HTML</option><option value="pdf">PDF</option></select></label>
      <button class="btn ghost sm" type="button">${esc(t('export_download', { format: 'CSV' }))}</button>
      <span class="status" style="margin:0"></span>`;
    const sel = box.querySelector('select'), btn = box.querySelector('button'), msg = box.querySelector('.status');
    sel.addEventListener('change', () => btn.textContent = t('export_download', { format: sel.value.toUpperCase() }));
    btn.addEventListener('click', async () => {
      btn.disabled = true; msg.textContent = ''; msg.classList.remove('err');
      try {
        const r = await api('/api/bridge/export', { kind, format: sel.value, lang: state.lang, ...params() });
        const url = URL.createObjectURL(await r.blob());
        const a = Object.assign(document.createElement('a'), { href: url, download: `researchbridge_${kind}_${state.lang}.${sel.value}` });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) { msg.textContent = e.message; msg.classList.add('err'); }
      btn.disabled = false;
    });
  }

  /* ---------- 01 search ---------- */
  async function loadKeywords() {
    const { keywords } = await getJSON('/api/bridge/keywords', { lang: state.lang });
    $('b-keywords').innerHTML = keywords.map(k =>
      `<button class="kbtn" type="button" data-label="${esc(k.label)}">${esc(t('keyword_count', { label: k.label, count: k.count }))}</button>`).join('');
    $('b-keywords').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
      state.q = b.dataset.label; $('b-q').value = state.q; search();
    }));
  }

  let searchRequest = 0;
  async function search() {
    const request = ++searchRequest;
    state.q = $('b-q').value.trim(); state.mode = $('b-mode').value;
    const q = state.q, mode = state.mode;
    state.lastResults = [];
    $('b-search-export').hidden = true;
    $('b-results').innerHTML = '';
    if (!state.q) { setStatus('b-search-status', t('enter_goal')); $('b-results').innerHTML = ''; $('b-search-export').hidden = true; return; }
    setStatus('b-search-status', state.lang === 'en' ? 'Searching the starter set…' : '…');
    try {
      const r = await getJSON('/api/bridge/search', { q, mode, limit: 20 });
      if (request !== searchRequest) return;
      state.lastResults = r.results;
      let msg = r.count ? (state.lang === 'en' ? `${r.count} ${r.count === 1 ? 'paper matches' : 'papers match'}; showing ${r.results.length}.` : t('results', { total: r.count, shown: r.results.length })) : t('empty');
      if (r.lexicon_matches.length || r.effective_query !== r.query) msg += ' ' + t('expansion', { query: r.expanded_query });
      setStatus('b-search-status', msg);
      $('b-results').innerHTML = r.results.map((p, i) => paperCard(p, i + 1)).join('');
      bindSaves($('b-results'));
      if (r.count) exportControls('b-search-export', 'search', () => ({ q, mode }));
      else $('b-search-export').hidden = true;
    } catch (e) { if (request === searchRequest) setStatus('b-search-status', e.message, true); }
  }

  /* ---------- 02 bridges ---------- */
  async function bridges() {
    state.method = $('b-method').value || 'auto';
    setStatus('b-bridge-status', '…');
    try {
      const r = await getJSON('/api/bridge/bridges', { q: state.q, mode: state.mode, method: state.method, cue: state.cue, limit: 10, lang: state.lang });
      $('b-recs').innerHTML = r.recommended_methods.length
        ? r.recommended_methods.map(m => `<button class="kbtn" type="button" data-m="${esc(m.id)}" title="${esc(t('method_support', { count: m.count, score: m.score }))}">${esc(m.label)} · ${m.count}</button>`).join('')
        : `<span class="status" style="margin:0">${esc(t('no_methods'))}</span>`;
      $('b-recs').querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => {
        $('b-method').value = b.dataset.m; state.cue = 'all'; bridges();
      }));
      // Cue options depend on the resolved method; keep 'all' if the old cue no longer applies.
      if (state.cue !== 'all' && !r.cues.some(c => c.id === state.cue)) state.cue = 'all';
      $('b-cue').innerHTML = `<option value="all">${esc(t('all_cues'))}</option>` + r.cues.map(c =>
        `<option value="${esc(c.id)}">${esc(c.label)} — ${esc(t(c.shared ? 'shared_cue' : 'extension_cue'))} (${c.method_count})</option>`).join('');
      $('b-cue').value = state.cue;
      $('b-chain-a').textContent = state.q || '—';
      $('b-chain-b').textContent = r.cue.label || t('all_cues');
      $('b-chain-c').textContent = r.method.label;
      setStatus('b-bridge-status', (r.count ? t('results', { total: r.count, shown: r.results.length }) : t('bridge_empty')) + ' ' + t('bridge_query', { query: r.bridge_query }));
      const rank = Object.fromEntries(r.results.map((p, i) => [p.pmid, i + 1]));
      $('b-pairs').innerHTML = r.pairs.length
        ? `<table class="tbl"><thead><tr><th scope="col">${esc(t('paper_a'))}</th><th scope="col">${esc(t('paper_b'))}</th><th scope="col">${esc(t('bridge_pair_score'))}</th><th scope="col">${esc(t('shared_terms'))}</th></tr></thead><tbody>` +
          r.pairs.map(p => `<tr><td class="num">${String(rank[p.a]).padStart(2, '0')} · ${esc(p.a)}</td><td class="num">${String(rank[p.b]).padStart(2, '0')} · ${esc(p.b)}</td><td class="num">${p.score.toFixed(3)}${p.limited_abstract ? ' *' : ''}</td><td>${esc(p.shared_terms.join(', '))}</td></tr>`).join('') +
          `</tbody></table>${r.pairs.some(p => p.limited_abstract) ? `<p class="meta">* ${esc(t('limited_pair'))}</p>` : ''}`
        : `<p class="status">${esc(t('bridge_pair_minimum'))}</p>`;
      $('b-bridge-results').innerHTML = r.results.map((p, i) => paperCard(p, i + 1, { bridge: true })).join('');
      bindSaves($('b-bridge-results'));
      if (r.count) exportControls('b-bridge-export', 'bridges', () => ({ q: state.q, mode: state.mode, method: state.method, cue: state.cue }));
      else $('b-bridge-export').hidden = true;
    } catch (e) { setStatus('b-bridge-status', e.message, true); }
  }

  /* ---------- 03 compare ---------- */
  async function compare() {
    const box = $('b-compare');
    if (!state.saved.length) { box.innerHTML = `<p class="status" style="margin:0">${esc(t('compare_empty'))}</p>`; return; }
    box.innerHTML = '<p class="status" style="margin:0">…</p>';
    try {
      const r = await postJSON('/api/bridge/compare', { pmids: state.saved, lang: state.lang });
      let h = `<div class="tbl-wrap"><table class="tbl"><thead><tr><th scope="col">PMID</th><th scope="col">${esc(t('paper_title'))}</th><th scope="col">${esc(t('tags'))}</th><th scope="col">${esc(t('fields'))}</th><th scope="col">${esc(t('methods'))}</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead><tbody>` +
        r.papers.map(p => `<tr><td class="num">${link(p.source_url, p.pmid)}</td><td>${esc(p.title)}</td><td>${esc(p.tags)}</td><td>${esc(p.fields)}</td><td>${esc(p.methods)}</td><td><button class="btn ghost sm" data-save="${esc(p.pmid)}" aria-pressed="true">${esc(t('remove'))}</button></td></tr>`).join('') +
        `</tbody></table></div><p class="meta">${esc(t('profile_note'))}</p>`;
      h += `<h3 class="sec" style="margin-top:20px">${esc(t('comparison_score'))}</h3><p class="meta" style="margin:0 0 10px">${esc(t('comparison_formula'))}</p>`;
      h += r.pairs.length ? r.pairs.map(p => `<div class="claim" style="grid-template-columns:72px 1fr"><span class="mk mono">${p.score.toFixed(3)}</span>
          <span>PMID ${esc(p.a)} / PMID ${esc(p.b)}<span class="why">${esc(t('shared_terms'))}: ${esc(p.shared_terms.join(', ') || t('none_shared'))}${p.limited_abstract ? ' · ' + esc(t('limited_pair')) : ''}</span></span></div>`).join('')
        : `<p class="status">${esc(t('pair_minimum'))}</p>`;
      box.innerHTML = h + '<div class="exp" id="b-compare-export"></div>';
      box.querySelectorAll('[data-save]').forEach(b => b.addEventListener('click', () => { toggleSaved(b.dataset.save); compare(); }));
      exportControls('b-compare-export', 'compare', () => ({ pmids: state.saved }));
    } catch (e) { box.innerHTML = `<p class="status err" style="margin:0">${esc(e.message)}</p>`; }
  }

  /* ---------- 04 source check ---------- */
  function renderCheckSources() {
    const ids = [...new Set([...state.saved, ...state.lastResults.slice(0, 10).map(p => p.pmid)])];
    const prev = new Set([...$('b-check-src').querySelectorAll('input:checked')].map(i => i.value));
    const checked = prev.size ? prev : new Set(ids.slice(0, 3));
    $('b-check-src').innerHTML = ids.length
      ? ids.map(id => `<label><input type="checkbox" value="${esc(id)}" ${checked.has(id) ? 'checked' : ''}><span><span class="mono">${esc(id)}</span> · ${esc(state.titles[id] || '')}</span></label>`).join('')
      : `<p class="status" style="margin:0">${esc(t('enter_goal'))}</p>`;
  }

  async function check() {
    const pmids = [...$('b-check-src').querySelectorAll('input:checked')].map(i => i.value);
    const claims = $('b-claims').value;
    const out = $('b-check-out');
    if (!claims.trim() || !pmids.length) { out.innerHTML = `<p class="status">${esc(t('check_empty'))}</p>`; return; }
    try {
      const r = await postJSON('/api/bridge/check', { claims, pmids: pmids.slice(0, 20) });
      // No match means "human review required" (amber ?), never "false".
      out.innerHTML = r.reports.map(c => {
        const ok = c.status === 'literal_match';
        return `<div class="claim" data-state="${ok ? 'pass' : 'review'}"><span class="mk">${ok ? '✓' : '?'}</span>
          <span><span class="txt">${esc(c.claim)}</span><span class="why">${esc(t(c.status))}${c.sources.map(s => ' · ' + link(s.source_url, t('matched_source', { pmid: s.pmid, section: s.section }))).join('')}</span></span></div>`;
      }).join('');
    } catch (e) { out.innerHTML = `<p class="status err">${esc(e.message)}</p>`; }
  }

  /* ---------- 05 brief ---------- */
  /** Minimal, escape-first markdown for make_brief()'s fixed structure. */
  function renderBrief(md) {
    const out = []; let list = [];
    const flush = () => { if (list.length) { out.push('<ul>' + list.join('') + '</ul>'); list = []; } };
    const inline = s => esc(s).replace(/https:\/\/[^\s<]+/g, u => link(u.replace(/&amp;/g, '&'), u.replace(/&amp;/g, '&')));
    for (const line of md.split('\n')) {
      if (line.startsWith('- ')) { list.push('<li>' + inline(line.slice(2)) + '</li>'); continue; }
      flush();
      if (!line.trim()) continue;
      if (line.startsWith('### ')) out.push(`<p><b>${esc(line.slice(4))}</b></p>`);
      else if (line.startsWith('## ')) out.push(`<h4>${esc(line.slice(3))}</h4>`);
      else if (line.startsWith('# ')) out.push(`<div class="bh"><span class="el">ResearchBridge · ${esc(state.meta.scope.corpus)}</span><h3>${esc(line.slice(2))}</h3></div>`);
      else if (line.startsWith('> ')) out.push(`<div class="ev"><q>${esc(line.slice(2))}</q></div>`);
      else out.push(`<p>${inline(line)}</p>`);
    }
    flush();
    return out.join('');
  }

  async function brief() {
    setStatus('b-brief-status', state.saved.length ? t('brief_selection', { count: state.saved.length }) : t('brief_current'));
    const params = { goal: state.q, mode: state.mode, method: state.method, cue: state.cue, pmids: state.saved, lang: state.lang };
    try {
      const r = await postJSON('/api/bridge/brief', params);
      $('b-brief').innerHTML = renderBrief(r.markdown); $('b-brief').hidden = false;
      exportControls('b-brief-export', 'brief', () => ({ q: state.q, mode: state.mode, method: state.method, cue: state.cue, pmids: state.saved }));
    } catch (e) {
      setStatus('b-brief-status', e.message, true); $('b-brief').hidden = true; $('b-brief-export').hidden = true;
    }
  }

  /* ---------- 06 directory ---------- */
  let dirTimer;
  async function directory() {
    const name = $('b-dir-name').value, city = $('b-dir-city').value || '';
    try {
      const r = await getJSON('/api/bridge/directory', { name, city });
      if ($('b-dir-city').options.length <= 1) {
        $('b-dir-city').innerHTML = `<option value="">${esc(t('all_cities'))}</option>` + r.cities.map(c => `<option>${esc(c)}</option>`).join('');
        $('b-dir-city').value = city;
      }
      setStatus('b-dir-status', t('directory_results', { count: r.count }));
      const n = v => Number(v).toLocaleString(state.lang === 'zh' ? 'zh-TW' : state.lang);
      $('b-dir').innerHTML = `<table class="tbl"><thead><tr><th scope="col">${esc(t('institution_name'))}</th><th scope="col">${esc(t('city'))}</th><th scope="col">${esc(t('works'))}</th><th scope="col">${esc(t('citations'))}</th></tr></thead><tbody>` +
        r.institutions.map(i => `<tr><td>${esc(i.name)}</td><td>${esc(i.city)}</td><td class="num">${n(i.works)}</td><td class="num">${n(i.cited_by)}</td></tr>`).join('') + '</tbody></table>';
      exportControls('b-dir-export', 'directory', () => ({ name: $('b-dir-name').value, city: $('b-dir-city').value || '' }));
    } catch (e) { setStatus('b-dir-status', e.message, true); }
  }

  /* ---------- tabs ---------- */
  const steps = [...document.querySelectorAll('#view-bridge .step')];
  const RENDER = { b2: bridges, b3: compare, b4: renderCheckSources, b5: brief, b6: directory };
  let current = 'b1';
  function show(id) {
    current = id;
    steps.forEach(s => s.setAttribute('aria-selected', String(s.dataset.p === id)));
    document.querySelectorAll('#view-bridge .panel').forEach(p => p.classList.toggle('on', p.id === id));
    RENDER[id]?.();
  }
  steps.forEach(s => s.addEventListener('click', () => show(s.dataset.p)));

  /* ---------- wiring ---------- */
  $('b-search-form').addEventListener('submit', e => { e.preventDefault(); search(); });
  $('b-mode').addEventListener('change', search);
  $('b-method').addEventListener('change', () => { state.cue = 'all'; bridges(); });
  $('b-cue').addEventListener('change', () => { state.cue = $('b-cue').value; bridges(); });
  $('b-check').addEventListener('click', check);
  $('b-dir-name').addEventListener('input', () => { clearTimeout(dirTimer); dirTimer = setTimeout(directory, 200); });
  $('b-dir-city').addEventListener('change', directory);
  $('b-lang').addEventListener('change', async () => {
    try {
      await loadMeta($('b-lang').value);
      $('b-dir-city').innerHTML = '';      // relabel "All cities"
      await loadKeywords();
      if (state.q) await search();
      refreshSaveButtons();                // relabel save buttons
      RENDER[current]?.();
    } catch (e) { setStatus('b-search-status', e.message, true); }
  });

  window.Bridge = {
    async init() {
      if (state.ready) return;
      state.ready = true;
      try {
        await loadMeta(state.lang);
        state.q = t('example_medication'); $('b-q').value = state.q;
        await loadKeywords();
        await search();
      } catch (e) {
        state.ready = false;
        setStatus('b-search-status', 'Evidence explorer needs the API server (python -m uvicorn app:app). ' + e.message, true);
      }
    },
  };
  // Opened directly at #explorer: the view was shown before this script loaded.
  if (!$('view-bridge').hidden) window.Bridge.init();
})();
