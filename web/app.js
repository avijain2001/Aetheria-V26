/* AETHERIA LIVE UI ADAPTER
   The UI is a presentation layer over the existing Aetheria engine.
   No news, market values, timestamps, or intelligence are hardcoded here.
*/
(() => {
  'use strict';

  const ROUTES = ['Home','Latest','India','World','Business','Markets','Sports','Technology','Legal','Geopolitical','Entertainment','Follow-up','Aetheria Read','Search'];
  const TOPIC_MAP = { Market: 'Markets', Markets: 'Markets', Geopolitical: 'Geopolitics' };
  const state = {
    route: 'Home', bootstrap: null, articles: [], stackIndex: 0, stackPaused: false,
    stackTimer: null, refreshTimer: null, followUp: null, searchQuery: '', searchSuggestTimer: null, requestSeq: 0
  };

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const num = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const topicClass = value => String(value || 'world').toLowerCase().replace(/[^a-z]/g,'');

  function getJSON(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 8000);
    const signal = options.signal;
    if (signal) signal.addEventListener('abort', () => controller.abort(), {once:true});
    return fetch(url, {cache:'no-store', signal:controller.signal, headers:{'Accept':'application/json'}})
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .finally(() => clearTimeout(timeout));
  }

  function formatTime(ts) {
    if (!ts) return '—';
    return new Date(Number(ts) * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  }
  function formatAge(ts) {
    if (!ts) return '';
    const sec = Math.max(0, Math.floor(Date.now()/1000 - Number(ts)));
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec/60);
    if (min < 60) return `${min}m ago`;
    const hrs = Math.floor(min/60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs/24)}d ago`;
  }
  function articleSource(a) {
    return a?.source?.name || a?.domain || a?.source_name || 'Source';
  }
  function articleTime(a) { return formatAge(a?.published); }
  function formatPublished(ts) {
    if (!ts) return '';
    const d = new Date(Number(ts) * 1000);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString([], {day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});
  }
  function eventTime(e) { return formatAge(e?.latest_published || e?.published); }
  function eventUrl(e) { return e?.latest_url || e?.url || e?.canonical_url || ''; }
  function safeSourceUrl(value) {
    const u = String(value || '').trim();
    if (!/^https?:\/\//i.test(u)) return '';
    try {
      const parsed = new URL(u, window.location.href);
      const path = (parsed.pathname || '').toLowerCase();
      if (parsed.origin === window.location.origin && (path.startsWith('/api/') || path.endsWith('.json'))) return '';
      return parsed.href;
    } catch { return ''; }
  }
  function sourceUrl(item) {
    return safeSourceUrl(item?.latest_url) || safeSourceUrl(item?.url) || safeSourceUrl(item?.canonical_url) ||
           safeSourceUrl(item?.source_url) || safeSourceUrl(item?.original_url) || '';
  }
  function openSource(url) {
    const u = safeSourceUrl(url);
    if (!u) return false;
    window.open(u, '_blank', 'noopener,noreferrer');
    return true;
  }
  function followSession() {
    let id = '';
    try { id = localStorage.getItem('aetheria-follow-session') || ''; } catch {}
    if (!id) {
      id = (window.crypto?.randomUUID?.() || `aetheria-${Date.now()}-${Math.random().toString(36).slice(2)}`);
      try { localStorage.setItem('aetheria-follow-session', id); } catch {}
    }
    return id;
  }
  function followedIds() {
    const rows = state.followUp?.active || state.followUp?.followed || [];
    return new Set(rows.map(x => String(x.id || x.event_id || '')).filter(Boolean));
  }
  function actionTools(item) {
    const eid = String(item?.event_id || item?.event?.id || item?.id || '');
    if (!eid) return '';
    const following = followedIds().has(eid);
    return `<span class="news-card-actions">
      <button type="button" class="news-card-action ${following?'following':''}" data-follow-event="${esc(eid)}" aria-label="${following?'Following':'Follow this story'}" title="${following?'Following':'Follow this story'}">${following?'✓':'+'}</button>
      <button type="button" class="news-card-action related" data-related-event="${esc(eid)}" aria-label="Related news" title="Related news">◎</button>
    </span>`;
  }

  function routeLabel(route) { return route === 'Markets' ? 'Market' : route; }
  function routeTopic(route) { return TOPIC_MAP[route] || route; }

  function closeAppearance() {
    $('appearancePanel')?.classList.remove('open');
  }
  function openAppearance() { closeSearchDock(); $('appearancePanel')?.classList.add('open'); }

  function closeCategoryPanels() {
    document.querySelectorAll('.category-panel').forEach(p => { p.classList.remove('open'); p.setAttribute('aria-hidden','true'); });
    document.querySelectorAll('[data-category-trigger]').forEach(b => b.setAttribute('aria-expanded','false'));
  }
  function positionCategoryPanel(panel, trigger, kind) {
    if (!panel || !trigger) return;
    const r = trigger.getBoundingClientRect();
    panel.style.position = 'fixed';
    if (kind === 'top') {
      panel.style.left = `${Math.max(12, Math.min(window.innerWidth - panel.offsetWidth - 12, r.right - panel.offsetWidth))}px`;
      panel.style.top = `${r.bottom + 10}px`;
      panel.style.bottom = 'auto';
    } else {
      panel.style.left = `${Math.max(12, Math.min(window.innerWidth - panel.offsetWidth - 12, r.right - panel.offsetWidth))}px`;
      panel.style.bottom = `${Math.max(78, window.innerHeight - r.top + 10)}px`;
      panel.style.top = 'auto';
    }
  }
  function openCategory(kind) {
    closeAppearance();
    closeSearchDock();
    closeCategoryPanels();
    const panel = $(kind === 'top' ? 'topCategoryPanel' : 'bottomCategoryPanel');
    const trigger = document.querySelector(`[data-category-trigger="${kind}"]`);
    if (!panel || !trigger) return;
    panel.classList.add('open'); panel.setAttribute('aria-hidden','false'); trigger.setAttribute('aria-expanded','true');
    requestAnimationFrame(() => positionCategoryPanel(panel, trigger, kind));
  }

  function setActiveNav() {
    document.querySelectorAll('[data-route]').forEach(b => {
      if (b.dataset.categoryTrigger) return;
      const route = b.dataset.route;
      const active = route === state.route || (state.route === 'Home' && route === 'Home') || (state.route === 'Markets' && route === 'Markets');
      b.classList.toggle('active', active);
    });
  }

  function storyModalOpen() { return $('storyModal')?.classList.contains('open'); }
  function closeStory() {
    $('storyModal')?.classList.remove('open');
    $('storyModal')?.setAttribute('aria-hidden','true');
  }
  async function openStory(eventId, articleId = '') {
    if (!eventId && !articleId) return;
    const modal = $('storyModal');
    if (!modal) return;
    modal.classList.add('open'); modal.setAttribute('aria-hidden','false');
    $('storyModalCat').textContent = 'AETHERIA';
    $('storyModalTitle').textContent = 'Loading verified story…';
    $('storyModalBody').textContent = 'Retrieving the underlying reporting and evidence.';
    $('storyModalMeta').textContent = '';
    const intel = $('storyModalIntel');
    if (intel) { intel.hidden = true; intel.innerHTML = ''; }
    try {
      const d = await getJSON(`/api/event/${encodeURIComponent(eventId)}`);
      const e = d.event || {};
      $('storyModalCat').textContent = e.topic || 'AETHERIA';
      $('storyModalTitle').textContent = e.title || 'Story';
      const evidence = d.evidence || {};
      const ai = d.local_ai || {};
      $('storyModalBody').textContent = ai.summary || d.primary_description || e.summary || (d.context?.why || []).join(' · ') || 'Verified reporting is available for this story.';
      const latest = (d.sources || []).slice().sort((a,b) => Number(b.published||0)-Number(a.published||0))[0];
      const latestUrl = safeSourceUrl(e.latest_url || latest?.canonical_url || '');
      $('storyModalMeta').textContent = `${e.status || 'LIVE'} · ${e.source_count || d.sources?.length || 0} report${(e.source_count || d.sources?.length || 0) === 1 ? '' : 's'} · ${formatPublished(latest?.published || e.latest_published || e.primary_published)}`;
      if (intel) {
        const impact = Number((e.intelligence || {}).impact ?? e.significance);
        const channels = (d.impact_channels || []).slice(0,3);
        intel.hidden = false;
        intel.innerHTML = `
          <div class="story-modal-intel-head">
            <span class="story-modal-intel-label">AETHERIA ANALYSIS</span>
            <span class="story-modal-intel-score">${Number.isFinite(impact) ? `Impact ${Math.round(impact*100)}/100` : ''}</span>
          </div>
          <div class="story-modal-intel-text">${esc(ai.why || (d.context?.why || []).join(' · ') || evidence.state || '')}</div>
          ${channels.length ? `<div class="story-modal-related-title">TRANSMISSION SIGNALS</div><div class="story-modal-intel-text">${channels.map(x => `${esc(x.channel)} · ${Math.round(Number(x.strength||0)*100)}`).join(' · ')}</div>` : ''}
          ${latestUrl ? `<div class="story-modal-intel-text"><button type="button" class="btn-primary" data-modal-source="${esc(latestUrl)}">Read original source →</button></div>` : ''}
          <div class="story-modal-related-title">RELATED NEWS</div>
          <div class="related-list">${(d.related || []).slice(0,6).map(r => {
            const ru=safeSourceUrl(r.url || '');
            return `<div class="related-item"><div><h4>${esc(r.title || '')}</h4><p>${esc(r.domain || 'Source')} · ${esc(formatPublished(r.published))}</p></div><button type="button" class="news-card-action related" data-modal-related="${esc(r.id || '')}" ${ru ? `data-related-source="${esc(ru)}"` : ''}>↗</button></div>`;
          }).join('') || '<p class="story-modal-intel-text">No additional related reporting is currently available.</p>'}</div>`;
      }
      if (eventId) modal.dataset.eventId = eventId;
      wireDynamicInteractions();
    } catch {
      $('storyModalTitle').textContent = 'Story details unavailable';
      $('storyModalBody').textContent = 'The underlying story endpoint is temporarily unavailable. No substitute content has been generated.';
    }
  }

  function renderMarkets(market) {
    const host = $('markets'); if (!host) return;
    const groups = (market?.groups || []);
    const items = groups.flatMap(g => (g.items || []).map(x => ({...x, group:g.label})))
      .filter(x => x.available !== false && x.price != null);
    if (!items.length) {
      host.innerHTML = '<div class="market-item"><div><div class="market-name">MARKET PULSE</div><div class="market-value">Waiting for verified market data…</div></div></div>';
      return;
    }
    host.innerHTML = items.slice(0, 8).map(x => {
      const price = Number(x.price);
      const changeNum = x.change_num != null ? Number(x.change_num) : null;
      const pct = x.change != null ? Number(x.change) * 100 : null;
      const sign = (changeNum ?? pct ?? 0) >= 0 ? '+' : '';
      const cls = (changeNum ?? pct ?? 0) >= 0 ? 'up' : 'down';
      const value = Number.isFinite(price) ? price.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}) : '—';
      const abs = changeNum != null ? `${sign}${changeNum.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}` : '';
      const ptxt = pct != null ? `${sign}${pct.toFixed(2)}%` : '';
      const change = abs || ptxt ? `<span class="change-value">${esc(abs || '—')}</span>${ptxt ? `<span class="change-pct">${esc(ptxt)}</span>` : ''}<span class="market-arrow" aria-hidden="true">${cls === 'down' ? '▼' : '▲'}</span>` : '<span class="change-value">—</span>';
      return `<div class="market-item"><div class="market-name">${esc(x.label || x.symbol || x.group || 'MARKET')}</div><div class="market-data"><div class="market-value">${esc(value)}</div><div class="market-change ${cls}">${change}</div></div></div>`;
    }).join('');
  }

  function renderBanner() {
    const b = state.bootstrap?.home || {};
    const lead = b.lead || (b.stack || [])[0] || (state.bootstrap?.latest || [])[0];
    $('relatedBannerTitle').textContent = lead?.title || 'Waiting for verified reporting…';
    $('relatedBannerDesc').textContent = lead?.description || lead?.reason || (lead ? `${articleSource(lead)} · ${eventTime(lead)}` : 'Aetheria is waiting for the live news engine.');
    const banner=$('relatedBanner');
    const img=$('relatedBannerImage');
    const url=sourceUrl(lead);
    const arrow=$('relatedBannerArrow');
    if(banner){
      if(url) banner.dataset.sourceUrl=url; else delete banner.dataset.sourceUrl;
    }
    if(arrow){
      if(url) arrow.dataset.sourceUrl=url; else delete arrow.dataset.sourceUrl;
    }
    if(img){
      if(lead?.image_url){
        img.style.backgroundImage=`url("${String(lead.image_url).replace(/"/g,'&quot;')}")`;
        img.classList.add('has-live-image');
      }else{
        img.style.backgroundImage='';
        img.classList.remove('has-live-image');
      }
    }
  }
  function storyStackItems() {
    const stack = state.bootstrap?.home?.stack || [];
    return stack.filter(x => x && x.id).slice(0, Math.max(10, stack.length));
  }

  function renderStack() {
    const items = storyStackItems();
    if (!items.length) return '<div class="hero-card hero-feature"><div class="feature-visual"><div class="visual-label">WORLD STATE · LIVE</div><div class="visual-grid"></div><div class="visual-caption">WAITING FOR VERIFIED REPORTS</div></div><div class="story-card"><div class="story-top"><span class="category-label">AETHERIA</span></div><h1 class="story-title">No verified story is available yet.</h1><p class="story-summary">The live engine has not supplied a current story. Aetheria will not fabricate one.</p></div></div>';
    const i = ((state.stackIndex % items.length) + items.length) % items.length;
    const s = items[i];
    const source = s.domain || (s.source_domains || [])[0] || 'Source';
    const url = sourceUrl(s);
    const image = s.image_url ? `<img class="feature-image" src="${esc(s.image_url)}" alt="" loading="eager" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
    const visualClass = image ? 'feature-visual has-image' : 'feature-visual';
    const pub = s.latest_published || s.published;
    return `<article class="hero-card hero-feature"><div class="${visualClass}">${image}<div class="feature-image-overlay"></div><div class="visual-label">${esc((s.topic || 'WORLD').toUpperCase())} · LIVE</div><div class="orb orb-a"></div><div class="orb orb-b"></div><div class="orb orb-c"></div><div class="visual-grid"></div><div class="visual-caption">WORLD STATE · LIVE</div></div><div class="story-card"><div class="story-top"><span class="category-label">${esc((s.topic || 'WORLD').toUpperCase())}</span><span class="story-time">${esc(eventTime(s))}</span></div><h1 class="story-title" ${url ? `data-source-url="${esc(url)}"` : `data-open-story="${esc(s.id || '')}"`}>${esc(s.title)}</h1><p class="story-summary">${esc(s.description || s.reason || 'Verified reporting is being connected to the current story.')}</p><div class="story-source"><span class="source-dot"></span><span class="stack-source">${esc(source)} · ${esc(eventTime(s))}</span>${actionTools(s)}${url ? `<button class="btn-primary" type="button" data-source-url="${esc(url)}">Read source →</button>` : `<button class="btn-primary" type="button" data-open-story="${esc(s.id || '')}">Read story →</button>`}</div><div class="news-published">Published ${esc(formatPublished(pub))}</div><div class="story-stack-controls" aria-label="News stack controls"><button type="button" data-home-prev>← Back</button><button type="button" data-home-pause>${state.stackPaused ? 'Resume' : 'Pause'}</button><button type="button" data-home-next>Forward →</button><span class="story-stack-count" aria-live="polite">${i+1} / ${items.length}</span></div></div></article>`;
  }

  function developingHTML(items) {
    const rows = (items || []).slice(0, 5);
    if (!rows.length) return '<div class="empty-state">No verified developing stories are available.</div>';
    return rows.map(e => {
      const url = sourceUrl(e);
      const action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(e.id || '')}"`;
      return `<div class="dev-row" ${action}><div class="dev-time">${esc(formatTime(e.latest_published || e.published))}<small>${esc((e.published ? new Date(e.published*1000).toLocaleDateString([], {day:'2-digit',month:'short'}) : ''))}</small></div><div><div class="dev-cat ${topicClass(e.topic)}">${esc((e.topic || 'WORLD').toUpperCase())}</div><div class="dev-title">${esc(e.title)}</div><div class="dev-source">${esc(e.domain || (e.source_domains || [])[0] || 'Source')} · ${esc(eventTime(e))}</div></div></div>`;
    }).join('');
  }
  function lowerCard(title, rows, renderer) {
    return `<article class="info-card"><div class="card-head"><b>${esc(title)}</b><a data-route="${esc(title === 'INDIA DESK' ? 'India' : title === 'IMPACT' ? 'Aetheria Read' : title === 'UPCOMING EVENTS' ? 'Follow-up' : 'Aetheria Read')}">View all →</a></div>${rows || '<div class="empty-state">No verified information available.</div>'}</article>`;
  }

  function renderHome() {
    const h = state.bootstrap?.home || {};
    const india = h.india_lens || [];
    const impact = h.impact || [];
    const future = state.bootstrap?.future || [];
    const read = h.read_next || [];
    const latest = state.articles.length ? state.articles.slice(0,4) : (state.bootstrap?.latest || []).slice(0,4);

    const leadKey = h.lead ? String(h.lead.article_id || h.lead.id || sourceUrl(h.lead)) : '';
    const leadUrl = sourceUrl(h.lead);
    const changedCandidates = [...(h.flash || []), ...(h.important || []), ...(h.emerging || []), ...(h.impact || []), ...(h.india_lens || []), ...(h.read_next || [])].filter(Boolean);
    const changed = [];
    const seen = new Set();
    for (const x of changedCandidates) {
      const key = String(x.article_id || x.id || sourceUrl(x) || x.title || '');
      const url = sourceUrl(x);
      if (!key || seen.has(key) || (leadKey && key === leadKey) || (leadUrl && url === leadUrl)) continue;
      seen.add(key); changed.push(x);
      if (changed.length >= 3) break;
    }

    const indiaRows = india.slice(0,3).map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const pub=x.latest_published || x.published;
      const meta=`<span class="india-item-meta"><span class="news-published">${esc(formatPublished(pub))}</span>${actionTools(x)}</span>`;
      return i===0
        ? `<div class="india-feature" ${action}><div class="india-photo" style="background-image:url('${esc(x.image_url || '')}')"></div><div><div class="india-live">● LIVE</div><div class="india-title">${esc(x.title)}</div>${meta}</div></div>`
        : `<div class="list-row" ${action}><span>${esc(x.title)}</span>${meta}</div>`;
    }).join('');

    const impactRows = impact.slice(0,3).map(x => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const score=Number(x?.intelligence?.impact);
      const scoreText=Number.isFinite(score) ? String(Math.round(score*100)) : '';
      const scoreClass = Number.isFinite(score) ? (score >= 0.70 ? 'impact-high' : score >= 0.40 ? 'impact-medium' : 'impact-low') : 'impact-none';
      const indicator = scoreText ? `<div class="impact-icon ${scoreClass}" aria-label="Impact ${esc(scoreText)} out of 100"><span class="impact-inline-score">${esc(scoreText)}</span></div>` : `<div class="impact-icon impact-none" aria-label="Impact score unavailable"><span class="impact-inline-score">—</span></div>`;
      return `<div class="impact-row" ${action}>${indicator}<div class="impact-text"><small>${esc((x.topic || 'IMPACT').toUpperCase())}</small><h3>${esc(x.title)}</h3><span class="news-published">${esc(formatPublished(x.latest_published || x.published))}</span></div>${actionTools(x)}</div>`;
    }).join('');

    const futureRows = future.slice(0,3).map(x => `<div class="impact-row"><div class="impact-icon" style="font-size:12px;font-weight:bold;">${esc(new Date(x.start_ts*1000).getDate())}</div><div class="impact-text"><small>${esc(new Date(x.start_ts*1000).toLocaleDateString([], {month:'short'}).toUpperCase())}</small><h3>${esc(x.title)}</h3></div></div>`).join('');
    const readRows = read.slice(0,1).map(x => `<div style="padding:16px;"><div class="banner-img" style="height:100px;margin-bottom:12px;background-image:url('${esc(x.image_url || '')}')"></div><h3 style="font-family:'Newsreader',serif;font-size:16px;margin-bottom:6px;">${esc(x.title)}</h3><p style="font-size:11px;color:var(--ink-muted);">${esc(x.description || x.reason || 'Connected reporting and context from the Aetheria engine.')}</p></div>`).join('');

    const latestRows = latest.length ? latest.map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.event_id || x.id || '')}"`;
      const image=x.image_url ? `<img src="${esc(x.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      return `<article class="latest-row ${i===0?'featured':''}" ${action}><time class="latest-time">${esc(formatTime(x.published || x.latest_published))}<small>${esc(x.published ? new Date(x.published*1000).toLocaleDateString([], {day:'2-digit',month:'short'}) : '')}</small></time><div class="latest-thumb-slot ${image?'':'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc((x.topic || 'WORLD').toUpperCase())}</span><h3>${esc(x.title)}</h3><p>${esc(articleSource(x))} · ${esc(articleTime(x))}${actionTools(x)}</p></div><button class="latest-arrow" type="button" aria-label="Open source">↗</button></article>`;
    }).join('') : '<div class="empty-state">No verified articles are available.</div>';

    const changedRows = changed.length ? changed.map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : (x.id ? `data-open-event="${esc(x.id)}"` : '');
      return `<article class="changed-card" ${action} tabindex="0" role="link"><div class="changed-icon">${i===0?'↗':i===1?'◎':'→'}</div><div class="changed-label">${i===0?'NEW DEVELOPMENT':i===1?'INDIA IMPACT':'WATCH NEXT'}</div><h3>${esc(x.title)}</h3><p>${esc(x.description || x.reason || 'The engine will add context when evidence supports it.')}</p><div class="changed-meta">${esc(eventTime(x))} <span>•</span> ${esc(x.sources || x.source_count || 1)} reports ${actionTools(x)}</div></article>`;
    }).join('') : '<div class="empty-state">No new verified change is available.</div>';

    return `<section class="home"><section class="hero">${renderStack()}<aside class="hero-card developing"><div class="dev-head"><b>DEVELOPING</b><a data-route="Latest">View all →</a></div>${developingHTML(h.happening || h.flash || h.important)}</aside></section><section class="lower">${lowerCard('INDIA DESK', `<div class="india-wrap">${indiaRows || '<div class="empty-state">No India-relevant verified reports are available.</div>'}</div>`)}${lowerCard('IMPACT', impactRows)}${lowerCard('UPCOMING EVENTS', futureRows)}${lowerCard('AETHERIA READ', readRows || '<div class="empty-state">No current reading signal is available.</div>')}</section><section class="intelligence-section"><div class="section-heading"><div><span class="section-kicker">AETHERIA INTELLIGENCE</span><h2>What changed?</h2></div></div><div class="changed-grid">${changedRows}</div></section><section class="latest-section"><div class="section-heading"><div><span class="section-kicker">REAL-TIME STREAM</span><h2>Latest</h2></div><a data-route="Latest">Open full stream →</a></div><div class="latest-card">${latestRows}</div></section><section class="followup-section intelligence-section"><div class="section-heading"><div><span class="section-kicker">CONTINUING WATCH</span><h2>Follow-up</h2></div><a data-route="Follow-up">Open follow-up desk →</a></div>${renderFollowUpPreview()}</section></section>`;
  }

  function renderFollowUpPreview() {
    const list = state.followUp?.active || state.followUp?.followed || [];
    if (!list.length) return '<div class="changed-grid"><article class="changed-card"><div class="changed-icon">→</div><div class="changed-label">FOLLOW-UP</div><h3>No active follow-up signal is available.</h3><p>Aetheria will surface continuing developments when the engine has verified a meaningful update.</p></article></div>';
    return `<div class="changed-grid">${list.slice(0,3).map(x => `<article class="changed-card" data-open-event="${esc(x.id)}"><div class="changed-icon">→</div><div class="changed-label">${esc(x.lifecycle || 'ACTIVE')}</div><h3>${esc(x.title)}</h3><p>${esc(x.what_changed || x.why_monitoring || 'Continuing monitoring is active.')}</p><div class="changed-meta">${esc(x.last_seen ? formatAge(x.last_seen) : '')}<button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id)}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></div></article>`).join('')}</div>`;
  }

  function articleRows(rows) {
    if (!rows?.length) return '<div class="empty-state">No verified articles are available for this section.</div>';
    return rows.map((a,i) => {
      const url = sourceUrl(a), action = url ? `data-source-url="${esc(url)}"` : (a.event_id ? `data-open-event="${esc(a.event_id)}"` : '');
      const image = a.image_url ? `<img src="${esc(a.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      const impact=Number(a?.event?.significance), impactBadge=Number.isFinite(impact) && impact>0 ? `<span class="impact-score">Impact ${Math.round(impact*100)}/100</span>` : '';
      return `<article class="latest-row ${i===0?'featured':''}" ${action}><time class="latest-time">${esc(formatTime(a.published))}<small>${esc(a.published ? new Date(a.published*1000).toLocaleDateString([], {day:'2-digit',month:'short'}) : '')}</small></time><div class="latest-thumb-slot ${image?'':'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(a.topic)}">${esc((a.topic || 'WORLD').toUpperCase())}</span><h3>${esc(a.title)}</h3><p>${esc(articleSource(a))} · ${esc(articleTime(a))}${impactBadge}${actionTools(a)}</p></div><button class="latest-arrow" type="button" aria-label="Open source">↗</button></article>`;
    }).join('');
  }

  function routeDescription(route) {
    return ({
      India:'India-first reporting and developments relevant to India, while retaining important global developments that affect the country.',
      World:'International reporting across regions and topics, prioritised by actual publication time and significance.',
      Business:'Company, trade and industry reporting from the live Aetheria source universe.',
      Markets:'Observed market and financial developments connected to the live news universe.',
      Sports:'Current sports reporting from the live source universe.',
      Technology:'Technology, AI and digital developments from the live source universe.',
      Legal:'Legal and regulatory developments from verified reporting.',
      Geopolitical:'Diplomatic, strategic and geopolitical developments from verified reporting.',
      Entertainment:'Entertainment, culture and media developments from the live source universe.'
    })[route] || 'Current Aetheria reporting.';
  }

  async function renderArticleRoute(route) {
    const host = $('mainView');
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">LIVE STREAM</span><h1>${esc(routeLabel(route))}</h1><p class="route-sub">${esc(routeDescription(route))}</p></div></div><div class="latest-card"><div class="empty-state">Loading verified reports…</div></div></section>`;
    const seq = ++state.requestSeq;
    try {
      const params = new URLSearchParams({limit:'80'});
      if (route === 'India') params.set('india','1');
      else if (route === 'World') params.set('world','1');
      else if (!['Latest'].includes(route)) params.set('topic', routeTopic(route));
      const d = await getJSON(`/api/articles?${params.toString()}`);
      if (seq !== state.requestSeq) return;
      state.articles = d.articles || [];
      host.querySelector('.latest-card').innerHTML = articleRows(state.articles);
      wireDynamicInteractions();
    } catch {
      host.querySelector('.latest-card').innerHTML = '<div class="empty-state">Live article data is temporarily unavailable. No substitute content has been generated.</div>';
    }
  }

  async function renderFollowUpPage() {
    const host = $('mainView');
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">CONTINUING WATCH</span><h1>Follow-up</h1><p class="route-sub">Continuing developments connected to stories already being monitored.</p></div></div><div class="latest-card"><div class="empty-state">Loading follow-up intelligence…</div></div></section>`;
    try {
      const d = await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
      state.followUp = d;
      const list = d.active || d.followed || d.suggested || [];
      host.querySelector('.latest-card').innerHTML = list.length ? list.map(x => {
        const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
        const pub=x.latest_published || x.published || x.last_seen;
        return `<article class="latest-row" ${action}><time class="latest-time">${esc(formatTime(pub))}<small>${esc(pub ? new Date(pub*1000).toLocaleDateString([], {day:'2-digit',month:'short'}) : '')}</small></time><div class="latest-thumb-slot empty"></div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc((x.topic || 'FOLLOW-UP').toUpperCase())}</span><h3>${esc(x.title)}</h3><p>${esc(x.what_changed || x.why_monitoring || x.previous_state || 'Continuing monitoring.')}${actionTools(x)}</p></div><button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id || '')}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></article>`;
      }).join('') : '<div class="empty-state">No follow-up stories are currently available.</div>';
      wireDynamicInteractions();
    } catch {
      host.querySelector('.latest-card').innerHTML = '<div class="empty-state">Follow-up intelligence is temporarily unavailable.</div>';
    }
  }

  function renderReadPage() {
    const rows = state.bootstrap?.home?.read_next || [];
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">AETHERIA READ</span><h1>Aetheria Read</h1><p class="route-sub">Context and explanation attached to current verified developments.</p></div></div><div class="latest-card">${articleRows(rows.map(x => ({...x,event_id:x.id,source:{name:x.domain},published:x.latest_published || x.published})))}</div></section>`;
    wireDynamicInteractions();
  }

  function renderSearchPage() {
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">DISCOVERY</span><h1>Search</h1><p class="route-sub">Search the current Aetheria story universe.</p></div></div><div class="route-search"><input id="routeSearchInput" type="search" autocomplete="off" placeholder="Search live news, topics or sources…" value="${esc(state.searchQuery || '')}" aria-label="Search live news"><button id="routeSearchButton" class="btn-primary" type="button">Search</button></div><div class="latest-card" id="searchResults"><div class="empty-state">${state.searchQuery ? 'Searching verified reporting…' : 'Enter a search term.'}</div></div></section>`;
    $('routeSearchButton').onclick = () => runRouteSearch();
    $('routeSearchInput').addEventListener('keydown', e => { if (e.key === 'Enter') runRouteSearch(); });
    requestAnimationFrame(() => {
      const input = $('routeSearchInput');
      if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
      if (state.searchQuery) runRouteSearch(state.searchQuery);
    });
  }
  async function runRouteSearch(queryOverride='') {
    const q = String(queryOverride || $('routeSearchInput')?.value || '').trim();
    if (!q) return;
    state.searchQuery = q;
    const input=$('routeSearchInput'); if(input) input.value=q;
    const resultsHost=$('searchResults'); if(!resultsHost) return;
    resultsHost.innerHTML = '<div class="empty-state">Searching verified reporting…</div>';
    try {
      const d = await getJSON(`/api/search?q=${encodeURIComponent(q)}`);
      resultsHost.innerHTML = articleRows(d.results || []);
      wireDynamicInteractions();
    } catch {
      resultsHost.innerHTML = '<div class="empty-state">Search is temporarily unavailable.</div>';
    }
  }

  function renderSearchSuggestions(items) {
    const host=$('searchSuggestions'); if(!host) return;
    if(!items?.length){ host.innerHTML=''; host.classList.remove('open'); return; }
    host.innerHTML=items.slice(0,8).map(x=>{
      const pub=x.latest_published || x.published;
      const meta=[x.topic || 'LIVE', x.status || 'CURRENT', formatPublished(pub)].filter(Boolean).join(' · ');
      return `<button type="button" class="search-suggestion" data-suggestion-id="${esc(x.id || '')}"><span><b>${esc(x.title || '')}</b><small>${esc(meta)}</small></span><span aria-hidden="true">↗</span></button>`;
    }).join('');
    host.classList.add('open');
    host.querySelectorAll('[data-suggestion-id]').forEach(btn=>btn.addEventListener('click',()=>{ const q=btn.querySelector('b')?.textContent?.trim() || ''; const input=$('searchDockInput'); if(input) input.value=q; state.searchQuery=q; closeSearchDock(); navigate('Search'); }));
  }
  async function updateSearchSuggestions() {
    const q=($('searchDockInput')?.value || '').trim();
    if(q.length<2){ renderSearchSuggestions([]); return; }
    try { const d=await getJSON(`/api/suggest?q=${encodeURIComponent(q)}`,{timeout:4000}); renderSearchSuggestions(d.results || []); } catch { renderSearchSuggestions([]); }
  }
  function openSearchDock() {
    closeCategoryPanels(); closeAppearance();
    const dock=$('searchDock'); if(!dock) return;
    dock.classList.add('open'); dock.setAttribute('aria-hidden','false');
    requestAnimationFrame(() => { const input=$('searchDockInput'); if(input){ input.value=state.searchQuery||''; input.focus(); input.select(); if(input.value.trim().length>=2) updateSearchSuggestions(); }});
  }
  function closeSearchDock() {
    const dock=$('searchDock'); if(!dock) return;
    dock.classList.remove('open'); dock.setAttribute('aria-hidden','true');
    renderSearchSuggestions([]);
    if(state.searchSuggestTimer) clearTimeout(state.searchSuggestTimer);
  }
  function submitTopSearch() {
    const q=($('searchDockInput')?.value || '').trim();
    if(!q){ closeSearchDock(); return; }
    state.searchQuery=q;
    closeSearchDock();
    navigate('Search');
  }

  async function renderRoute() {
    clearStackTimer();
    closeCategoryPanels();
    setActiveNav();
    if (state.route === 'Home') {
      if (!state.bootstrap) { $('mainView').innerHTML = '<section class="route-page"><div class="empty-state">Loading the live Aetheria world model…</div></section>'; return; }
      $('mainView').innerHTML = renderHome();
      bindHome();
      startStackTimer();
    } else if (state.route === 'Follow-up') {
      await renderFollowUpPage();
    } else if (state.route === 'Aetheria Read') {
      renderReadPage();
    } else if (state.route === 'Search') {
      renderSearchPage();
    } else {
      await renderArticleRoute(state.route);
    }
  }

  function navigate(route) {
    if (!ROUTES.includes(route)) return;
    state.route = route;
    closeSearchDock();
    const hash = route === 'Home' ? 'Home' : route;
    history.replaceState({route}, '', `#${encodeURIComponent(hash)}`);
    renderRoute();
  }

  function bindHome() {
    document.querySelectorAll('[data-open-story],[data-open-event]').forEach(el => el.addEventListener('click', e => {
      e.preventDefault(); e.stopPropagation();
      const url=el.dataset.sourceUrl || '';
      if(url && openSource(url)) return;
      openStory(el.dataset.openStory || el.dataset.openEvent);
    }));
    document.querySelectorAll('[data-home-prev]').forEach(b => b.onclick = () => moveStack(-1));
    document.querySelectorAll('[data-home-next]').forEach(b => b.onclick = () => moveStack(1));
    document.querySelectorAll('[data-home-pause]').forEach(b => b.onclick = e => { e.preventDefault(); e.stopPropagation(); state.stackPaused = !state.stackPaused; if (state.stackPaused) clearStackTimer(); else startStackTimer(); renderRoute(); });
    wireDynamicInteractions();
  }
  function wireDynamicInteractions() {
    document.querySelectorAll('[data-source-url]').forEach(el => {
      if(el.dataset.boundSource) return;
      el.dataset.boundSource='1';
      el.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openSource(el.dataset.sourceUrl); });
    });
    document.querySelectorAll('[data-open-event]').forEach(el => {
      if(el.dataset.boundEvent) return;
      el.dataset.boundEvent='1';
      el.onclick = e => { e.preventDefault(); e.stopPropagation(); openStory(el.dataset.openEvent); };
    });
    document.querySelectorAll('[data-route]').forEach(b => {
      if (!b.dataset.categoryTrigger && !b.dataset.boundRoute) {
        b.dataset.boundRoute='1';
        b.onclick = e => { e.preventDefault(); e.stopPropagation(); navigate(b.dataset.route); };
      }
    });
    document.querySelectorAll('[data-follow-event]').forEach(btn => {
      if(btn.dataset.boundFollow) return;
      btn.dataset.boundFollow='1';
      btn.addEventListener('click', async e => {
        e.preventDefault(); e.stopPropagation();
        const eid=btn.dataset.followEvent; if(!eid) return;
        const following=followedIds().has(eid); btn.disabled=true;
        try {
          const d=await fetch('/api/follow',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({session:followSession(),event_id:eid,action:following?'unfollow':'follow'})}).then(r=>r.json());
          if(!d.ok) throw new Error(d.error || 'Follow action failed');
          state.followUp=await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
          await renderRoute();
        } catch { btn.disabled=false; }
      });
    });
    document.querySelectorAll('[data-unfollow-event]').forEach(btn => {
      if(btn.dataset.boundUnfollow) return;
      btn.dataset.boundUnfollow='1';
      btn.addEventListener('click', async e => {
        e.preventDefault(); e.stopPropagation();
        const eid=btn.dataset.unfollowEvent; if(!eid) return; btn.disabled=true;
        try {
          const d=await fetch('/api/follow',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({session:followSession(),event_id:eid,action:'unfollow'})}).then(r=>r.json());
          if(!d.ok) throw new Error(d.error || 'Unfollow failed');
          state.followUp=await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
          await renderRoute();
        } catch { btn.disabled=false; }
      });
    });
    document.querySelectorAll('[data-related-event]').forEach(btn => {
      if(btn.dataset.boundRelated) return;
      btn.dataset.boundRelated='1';
      btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openStory(btn.dataset.relatedEvent); });
    });
    document.querySelectorAll('[data-modal-source]').forEach(btn => {
      if(btn.dataset.boundModalSource) return;
      btn.dataset.boundModalSource='1';
      btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openSource(btn.dataset.modalSource); });
    });
    document.querySelectorAll('[data-modal-related]').forEach(btn => {
      if(btn.dataset.boundModalRelated) return;
      btn.dataset.boundModalRelated='1';
      btn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const url=btn.dataset.relatedSource || '';
        if(url && openSource(url)) return;
        openStory(btn.dataset.modalRelated);
      });
    });
  }

  function moveStack(delta) {
    const items = storyStackItems(); if (!items.length) return;
    state.stackIndex = (state.stackIndex + delta + items.length) % items.length;
    renderRoute();
  }
  function clearStackTimer() { if (state.stackTimer) clearInterval(state.stackTimer); state.stackTimer = null; }
  function startStackTimer() {
    clearStackTimer();
    if (state.route !== 'Home' || state.stackPaused) return;
    const items = storyStackItems(); if (items.length < 2) return;
    state.stackTimer = setInterval(() => moveStack(1), 9000);
  }

  async function refreshBootstrap(forceRender = false) {
    try {
      const d = await getJSON('/api/bootstrap', {timeout:9000});
      state.bootstrap = d;
      renderMarkets(d.market || {});
      renderBanner();
      if (state.route === 'Home' || forceRender) await renderRoute();
      if (!state.followUp) {
        getJSON('/api/follow-up').then(x => { state.followUp=x; if(state.route==='Home') { const y=window.scrollY; renderRoute(); requestAnimationFrame(()=>window.scrollTo({top:y})); } }).catch(()=>{});
      }
    } catch (err) {
      if (!state.bootstrap) {
        $('mainView').innerHTML = '<section class="route-page"><div class="empty-state">Aetheria is waiting for a live engine response. No substitute news has been generated.</div></section>';
      }
    }
  }

  function initAppearance() {
    const panel = $('appearancePanel');
    $('themeBtn')?.addEventListener('click', e => { e.stopPropagation(); closeCategoryPanels(); panel?.classList.toggle('open'); });
    $('appearanceClose')?.addEventListener('click', closeAppearance);
    document.querySelectorAll('[data-theme]').forEach(b => b.addEventListener('click', () => { document.body.dataset.theme=b.dataset.theme; localStorage.setItem('aetheria-theme',b.dataset.theme); document.querySelectorAll('[data-theme]').forEach(x=>x.classList.toggle('active',x===b)); }));
    document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => { document.body.dataset.mode=b.dataset.mode; localStorage.setItem('aetheria-mode',b.dataset.mode); document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b)); }));
    const theme=localStorage.getItem('aetheria-theme'); if(theme) document.body.dataset.theme=theme;
    const mode=localStorage.getItem('aetheria-mode'); if(mode) document.body.dataset.mode=mode;
  }

  function initNavigation() {
    document.addEventListener('click', e => {
      const trigger=e.target.closest('[data-category-trigger]');
      if (trigger) { e.preventDefault(); e.stopPropagation(); openCategory(trigger.dataset.categoryTrigger); return; }
      const source=e.target.closest('[data-source-url]');
      if (source && !e.target.closest('[data-route]')) { e.preventDefault(); e.stopPropagation(); if(openSource(source.dataset.sourceUrl)) return; }
      const route=e.target.closest('[data-route]');
      if (route && !route.dataset.categoryTrigger) { e.preventDefault(); navigate(route.dataset.route); return; }
      if (!e.target.closest('.category-panel')) closeCategoryPanels();
      if (!e.target.closest('#appearancePanel') && !e.target.closest('#themeBtn')) closeAppearance();
      if (!e.target.closest('#searchDock') && !e.target.closest('#searchBtn')) closeSearchDock();
    });
    window.addEventListener('resize', () => { ['top','bottom'].forEach(kind => { const p=$(kind==='top'?'topCategoryPanel':'bottomCategoryPanel'); const t=document.querySelector(`[data-category-trigger="${kind}"]`); if(p?.classList.contains('open')) positionCategoryPanel(p,t,kind); }); });
    window.addEventListener('popstate', () => { const r=decodeURIComponent(location.hash.replace(/^#/,'') || 'Home'); if(ROUTES.includes(r)){state.route=r;renderRoute();} });
    document.addEventListener('keydown', e => { if(e.key==='Escape'){closeCategoryPanels();closeAppearance();closeSearchDock();if(storyModalOpen())closeStory();} });
    $('storyClose')?.addEventListener('click',closeStory);
    $('storyModal')?.addEventListener('click',e=>{if(e.target===$('storyModal'))closeStory();});
    $('searchBtn')?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();openSearchDock();});
    $('aetheriaBrand')?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();navigate('Home');});
    $('aetheriaBrand')?.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();navigate('Home');}});
    $('searchDockInput')?.addEventListener('input',()=>{ if(state.searchSuggestTimer) clearTimeout(state.searchSuggestTimer); state.searchSuggestTimer=setTimeout(updateSearchSuggestions,160); });
    $('searchDockInput')?.addEventListener('keydown',e=>{
      const host=$('searchSuggestions'); if(!host?.classList.contains('open')) return;
      const rows=[...host.querySelectorAll('.search-suggestion')]; if(!rows.length) return;
      const current=rows.findIndex(x=>x.classList.contains('keyboard-active'));
      if(e.key==='ArrowDown'){e.preventDefault();rows.forEach(x=>x.classList.remove('keyboard-active'));const n=(current+1)%rows.length;rows[n].classList.add('keyboard-active');rows[n].scrollIntoView({block:'nearest'});}
      else if(e.key==='ArrowUp'){e.preventDefault();rows.forEach(x=>x.classList.remove('keyboard-active'));const n=(current<=0?rows.length:current)-1;rows[n].classList.add('keyboard-active');rows[n].scrollIntoView({block:'nearest'});}
      else if(e.key==='Enter' && current>=0){e.preventDefault();rows[current].click();}
    });
    $('searchDockForm')?.addEventListener('submit',e=>{e.preventDefault();submitTopSearch();});
    $('searchDockClose')?.addEventListener('click',closeSearchDock);
    $('topCategoryClose')?.addEventListener('click',closeCategoryPanels);
    $('bottomCategoryClose')?.addEventListener('click',closeCategoryPanels);
    $('marketsLink')?.addEventListener('click',()=>navigate('Markets'));
  }

  function init() {
    initAppearance(); initNavigation();
    const initial=decodeURIComponent(location.hash.replace(/^#/,'') || 'Home');
    state.route=ROUTES.includes(initial)?initial:'Home';
    refreshBootstrap(true);
    state.refreshTimer=setInterval(()=>refreshBootstrap(false),10000);
    setInterval(()=>{ if(state.route!=='Home') return; renderBanner(); },15000);
  }
  init();
})();
