/* AETHERIA LIVE UI ADAPTER
   The UI is a presentation layer over the existing Aetheria engine.
   No news, market values, timestamps, or intelligence are hardcoded here.
*/
(() => {
  'use strict';

  const ROUTES = ['Home','Latest','India','World','Business','Markets','Sports','Technology','Legal','Geopolitical','Entertainment','Follow-up','Upcoming Events','Aetheria Read','Search'];
  const TOPIC_MAP = { Market: 'Markets', Markets: 'Markets', Geopolitical: 'Geopolitics' };
  const state = {
    route: 'Home', bootstrap: null, articles: [], stackIndex: 0, stackPaused: false,
    stackTimer: null, refreshTimer: null, followUp: null, searchQuery: '', searchSuggestTimer: null,
    requestSeq: 0, storyRequestSeq: 0, storyOpener: null, telemetrySeen: new Set(), telemetryObserver: null
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
    const value=Number(ts);
    if (!Number.isFinite(value) || value<=0) return '—';
    const date=new Date(value*1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  }
  function formatDate(ts) {
    const value=Number(ts);
    if (!Number.isFinite(value) || value<=0) return '';
    const date=new Date(value*1000);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString([], {day:'2-digit', month:'short'});
  }
  function formatScheduleDate(ts) {
    const value=Number(ts);
    if (!Number.isFinite(value) || value<=0) return '';
    const date=new Date(value*1000);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString([], {day:'2-digit', month:'short', year:'numeric'});
  }
  function clockMarkup(published, observed, className='latest-time') {
    const publishedTs=Number(published)||0, observedTs=Number(observed)||0;
    const timestamp=publishedTs||observedTs;
    if (!timestamp) return `<time class="${className}" aria-label="Publication time unavailable">—</time>`;
    const observedOnly=!publishedTs, label=observedOnly?'Observed':'Published';
    const dateTime=formatPublished(timestamp);
    return `<time class="${className}${observedOnly?' observed':''}" aria-label="${label} ${esc(dateTime)}" title="${label} ${esc(dateTime)}"><span>${esc(formatTime(timestamp))}</span><small>${esc(formatDate(timestamp))}</small>${observedOnly?'<em>Observed</em>':''}</time>`;
  }
  function formatAge(ts) {
    const value=Number(ts);
    if (!Number.isFinite(value) || value<=0) return '';
    const sec = Math.max(0, Math.floor(Date.now()/1000 - value));
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec/60);
    if (min < 60) return `${min}m ago`;
    const hrs = Math.floor(min/60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs/24)}d ago`;
  }
  function articleSource(a) {
    return a?.source?.name || a?.domain || a?.source_name || '';
  }
  function articleTime(a) {
    if (a?.published) return formatAge(a.published);
    return a?.fetched ? `Observed ${formatAge(a.fetched)}` : '';
  }
  function articleMeta(a) { return [articleSource(a), articleTime(a)].filter(Boolean).join(' · '); }
  function formatPublished(ts) {
    if (!ts) return '';
    const d = new Date(Number(ts) * 1000);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString([], {day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});
  }
  function publicationMarkup(published, observed) {
    const hasPublished=Number.isFinite(Number(published)) && Number(published)>0;
    const timestamp=hasPublished?Number(published):Number(observed);
    if (!Number.isFinite(timestamp) || timestamp<=0) return '';
    const label=hasPublished?'Published':'Observed';
    const formatted=formatPublished(timestamp);
    return formatted?`<span class="news-published">${label} ${esc(formatted)}</span>`:'';
  }
  function eventTime(e) {
    const published=e?.latest_published || e?.published;
    if (published) return formatAge(published);
    return e?.last_seen ? `Observed ${formatAge(e.last_seen)}` : '';
  }
  function languageFor(item, text='') {
    if (/\p{Script=Devanagari}/u.test(String(text || ''))) return 'hi';
    const language=String(item?.language || item?.languages?.[0] || '').trim();
    return /^[a-z]{2,3}(?:-[a-z0-9]+)*$/i.test(language) ? language : '';
  }
  function langAttr(item, text='') {
    const language=languageFor(item,text);
    return language ? `lang="${esc(language)}"` : '';
  }
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
    const stored=state.followUp?.followed_ids;
    if (Array.isArray(stored)) return new Set(stored.map(String));
    const rows = [...(state.followUp?.active || []), ...(state.followUp?.quiet || []), ...(state.followUp?.revived || []), ...(state.followUp?.followed || [])];
    return new Set(rows.map(x => String(x.id || x.event_id || '')).filter(Boolean));
  }
  function actionTools(item) {
    const itemId=String(item?.id || '');
    const isSchedule=Boolean(item?.start_ts && item?.kind);
    const eid = String(item?.event_id || item?.event?.id || (itemId.startsWith('evt_') || isSchedule ? itemId : '') || '');
    if (!eid) return '';
    const stateKnown=Boolean(state.followUp);
    const following = stateKnown && followedIds().has(eid);
    const followLabel=stateKnown?(following?'Following':'Follow'):'Unavailable';
    const followStateLabel=stateKnown?(following?'Following this story':'Follow this story'):'Follow-Up status unavailable';
    return `<span class="news-card-actions" role="group" aria-label="Story actions">
      <span class="signature-action"><button type="button" class="news-card-action ${following?'following':''} ${stateKnown?'':'unavailable'}" ${stateKnown?`data-follow-event="${esc(eid)}"`:'disabled'} aria-label="${followStateLabel}" title="${followStateLabel}"><span class="news-card-action-icon">${stateKnown?(following?'✓':'+'):'—'}</span></button><span class="news-card-action-label">${followLabel}</span></span>
      ${isSchedule?'':`<span class="signature-action"><button type="button" class="news-card-action related" data-related-event="${esc(eid)}" aria-label="See related coverage" title="See related coverage"><span class="news-card-action-icon">◎</span></button><span class="news-card-action-label">Related</span></span>`}
    </span>`;
  }

  let actionNoticeTimer=null;
  function announceAction(message) {
    let notice=$('actionNotice');
    if (!notice) {
      notice=document.createElement('div');
      notice.id='actionNotice';
      notice.className='action-notice';
      notice.setAttribute('role','status');
      notice.setAttribute('aria-live','polite');
      document.body.append(notice);
    }
    notice.textContent=message;
    notice.classList.add('visible');
    if (actionNoticeTimer) clearTimeout(actionNoticeTimer);
    actionNoticeTimer=setTimeout(()=>notice.classList.remove('visible'),3200);
  }
  function recordTelemetry(eventId, action) {
    if (!eventId || !action) return;
    fetch('/api/telemetry',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({session:followSession(),event_id:String(eventId),action,at:Date.now()/1000}),keepalive:true}).catch(()=>{});
  }
  function observeStoryExposure() {
    if (!('IntersectionObserver' in window)) return;
    if (!state.telemetryObserver) state.telemetryObserver=new IntersectionObserver(entries=>{
      entries.forEach(entry=>{
        if (!entry.isIntersecting || entry.intersectionRatio<.55) return;
        const button=entry.target, eventId=button.dataset.followEvent;
        state.telemetryObserver.unobserve(button);
        if (!eventId || state.telemetrySeen.has(eventId)) return;
        state.telemetrySeen.add(eventId);
        recordTelemetry(eventId,'seen');
      });
    },{threshold:[.55]});
    document.querySelectorAll('[data-follow-event]').forEach(button=>{
      const eventId=button.dataset.followEvent;
      if (eventId && !state.telemetrySeen.has(eventId) && !button.dataset.telemetryObserved) {
        button.dataset.telemetryObserved='1';
        state.telemetryObserver.observe(button);
      }
    });
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
    state.storyRequestSeq++;
    const modal=$('storyModal');
    modal?.classList.remove('open');
    modal?.setAttribute('aria-hidden','true');
    const opener=state.storyOpener;
    state.storyOpener=null;
    if(opener?.isConnected && opener!==document.body) opener.focus();
    else $('mainView')?.focus();
  }
  async function openStory(eventId, articleId = '') {
    if (!eventId && !articleId) return;
    const requestSeq=++state.storyRequestSeq;
    if (eventId) recordTelemetry(eventId,'open');
    const modal = $('storyModal');
    if (!modal) return;
    if (!modal.classList.contains('open')) state.storyOpener=document.activeElement;
    modal.classList.add('open'); modal.setAttribute('aria-hidden','false');
    $('storyClose')?.focus();
    $('storyModalCat').textContent = 'AETHERIA';
    $('storyModalTitle').textContent = 'Loading story evidence…';
    $('storyModalBody').textContent = 'Retrieving the underlying reporting and evidence.';
    $('storyModalMeta').textContent = '';
    const intel = $('storyModalIntel');
    if (intel) { intel.hidden = true; intel.innerHTML = ''; }
    try {
      const d = await getJSON(`/api/event/${encodeURIComponent(eventId)}`);
      if (requestSeq!==state.storyRequestSeq || !modal.classList.contains('open')) return;
      const e = d.event || {};
      $('storyModalCat').textContent = e.topic || 'AETHERIA';
      $('storyModalTitle').textContent = e.title || 'Story';
      $('storyModalTitle').setAttribute('lang',languageFor(e,e.title));
      const evidence = d.evidence || {};
      const ai = d.local_ai || {};
      $('storyModalBody').textContent = ai.summary || d.primary_description || e.summary || (d.context?.why || []).join(' · ') || 'Current source reporting is available for this story.';
      const latest = (d.sources || []).slice().sort((a,b) => Number(b.published||0)-Number(a.published||0))[0];
      const latestUrl = safeSourceUrl(e.latest_url || latest?.canonical_url || '');
      const reportCount=Number(evidence.reports ?? d.sources?.length ?? 0);
      const independentCount=Number(evidence.independent_sources ?? e.source_count ?? 0);
      const verificationState=evidence.verification_state || 'REPORTED';
      const evidenceLabel=verificationState==='CONFIRMED'?'CONFIRMED':verificationState==='CORROBORATED'?'CORROBORATED':verificationState==='DISPUTED'?'DISPUTED':'REPORTED';
      const independentLabel=`${independentCount} independent source${independentCount===1?'':'s'}`;
      const modalPublished=latest?.published || e.latest_published || e.primary_published;
      $('storyModalMeta').textContent = [evidenceLabel,independentLabel,`${reportCount} distinct report${reportCount===1?'':'s'}`,evidence.official?`${evidence.official} official source${evidence.official===1?'':'s'}`:'',modalPublished?formatPublished(modalPublished):e.last_seen?`Observed ${formatPublished(e.last_seen)}`:''].filter(Boolean).join(' · ');
      if (intel) {
        const impact = Number((e.intelligence || {}).impact ?? e.significance);
        const channels = (d.impact_channels || []).slice(0,3);
        const analysis=ai.why || (d.context?.why || []).filter(Boolean).join(' · ');
        const timeline=(d.timeline || []).slice(0,6).reverse();
        intel.hidden = false;
        intel.innerHTML = `
          <div class="story-modal-intel-head">
            <span class="story-modal-intel-label">AETHERIA ANALYSIS</span>
            <span class="story-modal-intel-score">${Number.isFinite(impact) ? `Impact ${Math.round(impact*100)}/100` : ''}</span>
          </div>
          ${analysis ? `<div class="story-modal-intel-text">${esc(analysis)}</div>` : ''}
          ${d.context?.latest_change ? `<div class="story-modal-related-title">LATEST OBSERVED CHANGE</div><div class="story-modal-intel-text">${esc(d.context.latest_change)}</div>` : ''}
          ${timeline.length ? `<div class="story-modal-related-title">OBSERVED TIMELINE</div><ol class="story-modal-timeline">${timeline.map(x=>`<li><time>${esc(formatPublished(x.observed_at))}</time><span>${esc(x.change_type || '')}</span><p>${esc(x.note || '')}</p></li>`).join('')}</ol>` : ''}
          ${!analysis&&!d.context?.latest_change&&!timeline.length ? `<div class="story-modal-intel-text">Additional analysis is unavailable from the current event evidence.</div>` : ''}
          ${channels.length ? `<div class="story-modal-related-title">TRANSMISSION SIGNALS</div><div class="story-modal-intel-text">${channels.map(x => `${esc(x.channel)} · ${Math.round(Number(x.strength||0)*100)}`).join(' · ')}</div>` : ''}
          ${latestUrl ? `<div class="story-modal-intel-text"><button type="button" class="btn-primary" data-modal-source="${esc(latestUrl)}">Read original source →</button></div>` : ''}
          <div class="story-modal-related-title">RELATED NEWS</div>
          <div class="related-list">${(d.related || []).slice(0,6).map(r => {
            const ru=safeSourceUrl(r.url || '');
            const relationEvidence=(r.relationship_evidence || []).join(' · ');
            return `<div class="related-item"><div><h4 ${langAttr(r,r.title)}>${esc(r.title || '')}</h4><p>${esc([r.domain, r.published ? formatPublished(r.published) : r.last_seen ? `Observed ${formatPublished(r.last_seen)}` : ''].filter(Boolean).join(' · '))}</p>${relationEvidence?`<small class="related-evidence">${esc(relationEvidence)}</small>`:''}</div><button type="button" class="news-card-action related" data-modal-related="${esc(r.id || '')}" aria-label="Open related event" title="Open related event" ${ru ? `data-related-source="${esc(ru)}"` : ''}>↗</button></div>`;
          }).join('') || '<p class="story-modal-intel-text">No additional related reporting is currently available.</p>'}</div>`;
      }
      if (eventId) modal.dataset.eventId = eventId;
      wireDynamicInteractions();
    } catch {
      if (requestSeq!==state.storyRequestSeq || !modal.classList.contains('open')) return;
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
      host.innerHTML = '<div class="market-item"><div><div class="market-name">MARKET PULSE</div><div class="market-value">Waiting for active market data…</div></div></div>';
      return;
    }
    host.innerHTML = items.slice(0, 8).map(x => {
      const price = Number(x.price);
      const changeNum = x.change_num != null ? Number(x.change_num) : null;
      const pct = x.change != null ? Number(x.change) * 100 : null;
      const movement = Number.isFinite(changeNum) ? changeNum : Number.isFinite(pct) ? pct : null;
      const cls = movement == null || !Number.isFinite(movement) ? 'flat' : movement > 0 ? 'up' : movement < 0 ? 'down' : 'flat';
      const sign = movement > 0 ? '+' : '';
      const value = Number.isFinite(price) ? price.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}) : '—';
      const abs = changeNum != null && Number.isFinite(changeNum) ? `${sign}${changeNum.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}` : '';
      const ptxt = pct != null && Number.isFinite(pct) ? `${sign}${pct.toFixed(2)}%` : '';
      const direction = cls === 'up' ? 'Rising' : cls === 'down' ? 'Falling' : movement == null || !Number.isFinite(movement) ? 'Change unavailable' : 'Unchanged';
      const change = abs || ptxt ? `<span class="change-value">${esc(abs || '—')}</span>${ptxt ? `<span class="change-pct">${esc(ptxt)}</span>` : ''}<span class="market-arrow" aria-hidden="true">${cls === 'down' ? '▼' : cls === 'up' ? '▲' : '='}</span>` : '<span class="change-value">—</span>';
      return `<div class="market-item"><div class="market-name">${esc(x.label || x.symbol || x.group || 'MARKET')}</div><div class="market-data"><div class="market-value">${esc(value)}</div><div class="market-change ${cls}" role="img" aria-label="${esc(direction)}${abs ? `, ${esc(abs)}` : ''}${ptxt ? `, ${esc(ptxt)}` : ''}">${change}</div></div></div>`;
    }).join('');
  }

  function renderBanner() {
    const b = state.bootstrap?.home || {};
    const lead = b.lead || (b.stack || [])[0] || (state.bootstrap?.latest || [])[0];
    $('relatedBannerTitle').textContent = lead?.title || 'Waiting for active reporting…';
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
    if (!items.length) return '<div class="hero-card hero-feature"><div class="feature-visual"><div class="visual-label">AETHERIA</div><div class="visual-grid"></div><div class="visual-caption">WAITING FOR NETWORK</div></div><div class="story-card"><div class="story-top"><span class="category-label">AETHERIA</span></div><h1 class="story-title">No active story is available yet.</h1><p class="story-summary">The live engine has not supplied a current story. Aetheria will not fabricate one.</p></div></div>';
    const i = ((state.stackIndex % items.length) + items.length) % items.length;
    const s = items[i];
    const source = s.domain || (s.source_domains || [])[0] || '';
    const url = sourceUrl(s);
    const image = s.image_url ? `<img class="feature-image" src="${esc(s.image_url)}" alt="" loading="eager" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
    const visualClass = image ? 'feature-visual has-image' : 'feature-visual';
    const pub = s.latest_published || s.published;
    const sourceMeta=[source,eventTime(s)].filter(Boolean).join(' · ');
    const status=String(s.status || '').trim();
    return `<article class="hero-card hero-feature"><div class="${visualClass}">${image}<div class="feature-image-overlay"></div><div class="visual-label">${esc([s.topic,status].filter(Boolean).join(' · ').toUpperCase())}</div><div class="orb orb-a"></div><div class="orb orb-b"></div><div class="orb orb-c"></div><div class="visual-grid"></div><div class="visual-caption">${esc(status || s.topic || '')}</div></div><div class="story-card"><div class="story-top"><span class="category-label">${esc((s.topic || 'WORLD').toUpperCase())}</span><span class="story-time">${esc(eventTime(s))}</span></div><h1 class="story-title" ${langAttr(s,s.title)} ${url ? `data-source-url="${esc(url)}"` : `data-open-story="${esc(s.id || '')}"`}>${esc(s.title)}</h1><p class="story-summary" ${langAttr(s,s.description)}>${esc(s.description || s.reason || '')}</p><div class="story-source">${sourceMeta?'<span class="source-dot"></span>':''}<span class="stack-source">${esc(sourceMeta)}</span></div><div class="news-published">${pub?`Published ${esc(formatPublished(pub))}`:s.last_seen?`Observed ${esc(formatPublished(s.last_seen))}`:''}</div><div class="hero-action-row">${actionTools(s)}${url ? `<button class="btn-primary" type="button" data-source-url="${esc(url)}">Read source →</button>` : `<button class="btn-primary" type="button" data-open-story="${esc(s.id || '')}">Read story →</button>`}</div><div class="story-stack-controls" aria-label="News stack controls"><button type="button" data-home-prev>← Back</button><button type="button" data-home-pause>${state.stackPaused ? 'Resume' : 'Pause'}</button><button type="button" data-home-next>Forward →</button><span class="story-stack-count" aria-live="polite">${i+1} / ${items.length}</span></div></div></article>`;
  }

  function developingHTML(items) {
    const rows = (items || []).slice(0, 5);
    if (!rows.length) return '<div class="empty-state">No active developing stories are available.</div>';
    return rows.map(e => {
      const url = sourceUrl(e);
      const action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(e.id || '')}"`;
      const domain=e.domain || (e.source_domains || [])[0] || '';
      return `<div class="dev-row" ${action}>${clockMarkup(e.latest_published || e.published,e.last_seen,'dev-time')}<div class="dev-content"><div class="dev-cat ${topicClass(e.topic)}">${esc((e.topic || 'WORLD').toUpperCase())}</div><div class="dev-title" ${langAttr(e,e.title)}>${esc(e.title)}</div><div class="dev-source">${esc([domain,eventTime(e)].filter(Boolean).join(' · '))}</div></div>${actionTools(e)}</div>`;
    }).join('');
  }
  function lowerCard(title, rows, renderer) {
    return `<article class="info-card"><div class="card-head"><b>${esc(title)}</b><a data-route="${esc(title === 'INDIA DESK' ? 'India' : title === 'IMPACT' ? 'Aetheria Read' : title === 'UPCOMING EVENTS' ? 'Upcoming Events' : 'Aetheria Read')}">View all →</a></div>${rows || '<div class="empty-state">No active information available.</div>'}</article>`;
  }

  function renderHome() {
    const h = state.bootstrap?.home || {};
    const developing = Array.isArray(h.happening) ? h.happening : [];
    const india = h.india_lens || [];
    const impact = h.impact || [];
    const future = h.upcoming_events || state.bootstrap?.future || [];
    const read = h.read_next || [];
    const latest = state.articles.length ? state.articles.slice(0,4) : (state.bootstrap?.latest || []).slice(0,4);

    const leadKey = h.lead ? String(h.lead.article_id || h.lead.id || sourceUrl(h.lead)) : '';
    const leadUrl = sourceUrl(h.lead);
    const changedCandidates = (h.emerging || []).filter(Boolean);
    const changed = [];
    const seen = new Set();
    for (const x of changedCandidates) {
      const key = String(x.article_id || x.id || sourceUrl(x) || x.title || '');
      const url = sourceUrl(x);
      if (!key || seen.has(key) || (leadKey && key === leadKey) || (leadUrl && url === leadUrl)) continue;
      seen.add(key); changed.push(x);
      if (changed.length >= 3) break;
    }

    const indiaRows = india.slice(0,2).map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const pub=x.latest_published || x.published;
      const footer=`<div class="india-item-footer"><span class="india-item-time">${publicationMarkup(pub,x.last_seen)}</span><div class="india-item-actions">${actionTools(x)}</div></div>`;
      const status=x.status?`<div class="india-live">${esc(x.status.toUpperCase())}</div>`:'';
      const image=safeSourceUrl(x.image_url);
      const imageMarkup=image?`<img class="india-photo" src="${esc(image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.india-feature')?.classList.add('text-only');this.remove()">`:'';
      return i===0
        ? `<div class="india-feature ${image?'has-image':'text-only'}" ${action}>${imageMarkup}<div class="india-feature-content"><small class="india-item-category">${esc((x.topic || 'INDIA').toUpperCase())}</small>${status}<div class="india-title" ${langAttr(x,x.title)}>${esc(x.title)}</div>${footer}</div></div>`
        : `<div class="list-row india-secondary" ${action}><small class="india-item-category">${esc((x.topic || 'INDIA').toUpperCase())}</small>${status}<span class="india-secondary-title" ${langAttr(x,x.title)}>${esc(x.title)}</span>${footer}</div>`;
    }).join('');

    const impactRows = impact.slice(0,3).map(x => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const score=Number(x?.intelligence?.impact);
      const scoreText=Number.isFinite(score) ? String(Math.round(score*100)) : '';
      const scoreClass = Number.isFinite(score) ? (score >= 0.70 ? 'impact-high' : score >= 0.40 ? 'impact-medium' : 'impact-low') : 'impact-none';
      const indicator = scoreText ? `<div class="impact-icon ${scoreClass}" aria-label="Impact ${esc(scoreText)} out of 100"><span class="impact-inline-score">${esc(scoreText)}</span></div>` : `<div class="impact-icon impact-none" aria-label="Impact score unavailable"><span class="impact-inline-score">—</span></div>`;
      return `<div class="impact-row" ${action}>${indicator}<div class="impact-text"><small>${esc((x.topic || 'IMPACT').toUpperCase())}</small><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3>${publicationMarkup(x.latest_published || x.published,x.last_seen)}</div>${actionTools(x)}</div>`;
    }).join('');

    const futureRows = future.length ? `<div class="future-wrap">${future.slice(0,2).map(x => {
      const url=safeSourceUrl(x.url), action=url?`data-source-url="${esc(url)}"`:'';
      const date=x.time_known?formatPublished(x.start_ts):formatScheduleDate(x.start_ts);
      return `<div class="future-row" ${action}><div class="future-text"><small>${esc(x.horizon || '')}</small><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3><time datetime="${esc(x.start_ts?new Date(x.start_ts*1000).toISOString():'')}">${esc(date)}</time></div>${actionTools(x)}</div>`;
    }).join('')}</div>` : '<div class="empty-state">No active upcoming events are available.</div>';
    const readRows = read.slice(0,1).map(x => {
      const image=safeSourceUrl(x.image_url);
      const source=String(x.domain || x.latest_domain || x.source_domains?.[0] || '').trim();
      const published=x.latest_published || x.published || x.last_seen;
      const timeLabel=published?`${Number(x.latest_published || x.published)>0?'Published':'Observed'} ${formatPublished(published)}`:'';
      const reportCount=Number(x.sources ?? x.source_count);
      const readMeta=[source,timeLabel,x.status,Number.isFinite(reportCount)&&reportCount>0?`${reportCount} reports`: ''].filter(Boolean);
      const context=String(x.description || '').trim();
      const imageMarkup=image?`<div class="read-card-image banner-img" role="img" aria-label="Article image" style="background-image:url('${esc(image)}')"></div>`:'';
      return `<div class="read-card-content ${image?'has-image':'no-image'}">${imageMarkup}<small class="read-card-category">${esc((x.topic || 'AETHERIA READ').toUpperCase())}</small><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3>${!image&&readMeta.length?`<div class="read-card-meta">${readMeta.map(v=>`<span>${esc(v)}</span>`).join('')}</div>`:''}${!image&&context?`<p class="read-card-excerpt" ${langAttr(x,context)}>${esc(context)}</p>`:''}<div class="read-card-actions">${actionTools(x)}</div></div>`;
    }).join('');

    const latestRows = latest.length ? latest.map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.event_id || x.id || '')}"`;
      const image=x.image_url ? `<img src="${esc(x.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      return `<article class="latest-row ${i===0?'featured':''}" ${action}>${clockMarkup(x.published || x.latest_published,x.last_seen)}<div class="latest-thumb-slot ${image?'':'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc((x.topic || 'WORLD').toUpperCase())}</span><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3><p>${esc(articleMeta(x))}</p></div><div class="latest-actions">${actionTools(x)}<button class="latest-arrow" type="button" aria-label="Open source" title="Open source">↗</button></div></article>`;
    }).join('') : '<div class="empty-state">No active articles are available.</div>';

    const changedRows = changed.length ? changed.map((x,i) => {
      const url=sourceUrl(x), action=url ? `data-source-url="${esc(url)}"` : (x.id ? `data-open-event="${esc(x.id)}"` : '');
      const sourceCount=Number(x.sources ?? x.source_count);
      const source=String(x.latest_domain || x.domain || x.source_domains?.[0] || '').trim();
      const detail=[eventTime(x),source,Number.isFinite(sourceCount)?`${sourceCount} reports`:'' ].filter(Boolean).join(' · ');
      const change=x._editorial_selection?.change_evidence || {};
      const changeLabel=change.confidence==='HIGH'?'STRONG CHANGE EVIDENCE':'LIKELY CHANGE';
      const context=String(change.what_is_new || x.description || '').trim();
      const known=String(change.what_was_known || '').trim();
      const changeContext=known&&context?`Previously: ${known} | New evidence: ${context}`:context;
      const keyboardAttrs=action?`tabindex="0" role="group" aria-label="Open story: ${esc(x.title)}" aria-keyshortcuts="Enter"`:'';
      return `<article class="changed-card" ${action} ${keyboardAttrs}><div class="changed-icon">${i===0?'↗':i===1?'◎':'→'}</div><div class="changed-label">${esc(changeLabel)}</div><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3>${changeContext?`<p class="changed-context" ${langAttr(x,changeContext)}>${esc(changeContext)}</p>`:''}<div class="changed-meta"><span class="changed-info">${esc(detail)}</span>${actionTools(x)}</div></article>`;
    }).join('') : '<div class="empty-state">No likely real-world change is supported by current reporting.</div>';

    return `<section class="home"><section class="hero">${renderStack()}<aside class="hero-card developing"><div class="dev-head"><b>DEVELOPING</b><a data-route="Latest">View all →</a></div>${developingHTML(developing)}</aside></section><section class="lower">${lowerCard('INDIA DESK', `<div class="india-wrap">${indiaRows || '<div class="empty-state">No India-relevant active reports are available.</div>'}</div>`)}${lowerCard('IMPACT', impactRows)}${lowerCard('UPCOMING EVENTS', futureRows)}${lowerCard('AETHERIA READ', readRows || '<div class="empty-state">No current reading signal is available.</div>')}</section><section class="intelligence-section"><div class="section-heading"><div><span class="section-kicker">AETHERIA INTELLIGENCE</span><h2>What changed?</h2></div></div><div class="changed-grid">${changedRows}</div></section><section class="latest-section"><div class="section-heading"><div><span class="section-kicker">REAL-TIME STREAM</span><h2>Latest</h2></div><a data-route="Latest">Open full stream →</a></div><div class="latest-card">${latestRows}</div></section><section class="followup-section intelligence-section"><div class="section-heading"><div><span class="section-kicker">CONTINUING WATCH</span><h2>Follow-up</h2></div><a data-route="Follow-up">Open follow-up desk →</a></div>${renderFollowUpPreview()}</section></section>`;
  }

  function renderFollowUpPreview() {
    const list = state.followUp?.active || state.followUp?.followed || [];
    if (!list.length) return '<div class="changed-grid"><article class="changed-card"><div class="changed-icon">→</div><div class="changed-label">FOLLOW-UP</div><h3>No active follow-up signal is available.</h3><p>Aetheria will surface continuing developments when the engine has identified a meaningful update.</p></article></div>';
    return `<div class="changed-grid">${list.slice(0,3).map(x => {
      const scheduled=Number(x.start_ts)>0, url=scheduled?safeSourceUrl(x.url):'';
      const action=url?`data-source-url="${esc(url)}"`:scheduled?'':`data-open-event="${esc(x.id)}"`;
      const description=scheduled?x.description:(x.what_changed || x.why_monitoring || '');
      return `<article class="changed-card" ${action}><div class="changed-icon">→</div><div class="changed-label">${esc(x.lifecycle || 'ACTIVE')}</div><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3>${description?`<p ${langAttr(x,description)}>${esc(description)}</p>`:''}<div class="changed-meta"><span class="changed-info">${esc(x.last_seen ? formatAge(x.last_seen) : '')}</span>${actionTools(x)}<button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id)}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></div></article>`;
    }).join('')}</div>`;
  }

  function articleRows(rows) {
    if (!rows?.length) return '<div class="empty-state">No matching live reports are available.</div>';
    return rows.map((a,i) => {
      const url = sourceUrl(a), action = url ? `data-source-url="${esc(url)}"` : (a.event_id ? `data-open-event="${esc(a.event_id)}"` : '');
      const image = a.image_url ? `<img src="${esc(a.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      const impact=Number(a?.event?.significance), impactBadge=Number.isFinite(impact) && impact>0 ? `<span class="impact-score">Impact ${Math.round(impact*100)}/100</span>` : '';
      return `<article class="latest-row ${i===0?'featured':''}" ${action}>${clockMarkup(a.published,a.fetched)}<div class="latest-thumb-slot ${image?'':'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(a.topic)}">${esc((a.topic || 'WORLD').toUpperCase())}</span><h3 ${langAttr(a,a.title)}>${esc(a.title)}</h3><p>${esc(articleMeta(a))}${impactBadge}</p></div><div class="latest-actions">${actionTools(a)}<button class="latest-arrow" type="button" aria-label="Open source" title="Open source">↗</button></div></article>`;
    }).join('');
  }

  function loadingRows(label='Loading...') {
    return Array(6).fill().map(()=>'<article class="latest-row loading-skeleton" aria-hidden="true"><div class="latest-time skeleton-block" style="width:40px;height:12px;"></div><div class="latest-thumb-slot empty skeleton-block" style="background:var(--surface-2)"></div><div class="latest-main"><div class="skeleton-block" style="width:30%;height:10px;margin-bottom:8px"></div><div class="skeleton-block" style="width:90%;height:16px;margin-bottom:6px"></div><div class="skeleton-block" style="width:70%;height:16px"></div></div></article>').join('');
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
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">LIVE STREAM</span><h1>${esc(routeLabel(route))}</h1><p class="route-sub">${esc(routeDescription(route))}</p></div></div><div class="latest-card">${loadingRows()}</div></section>`;
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
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">CONTINUING WATCH</span><h1>Follow-up</h1><p class="route-sub">Continuing developments connected to stories already being monitored.</p></div></div><div class="latest-card">${loadingRows('Loading follow-up intelligence...')}</div></section>`;
    try {
      const d = await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
      state.followUp = d;
      const list = d.active || d.followed || d.suggested || [];
      host.querySelector('.latest-card').innerHTML = list.length ? list.map(x => {
        const isSchedule=Number(x.start_ts)>0;
        const pub=x.latest_published || x.published;
        const url=safeSourceUrl(x.latest_url || x.url || '');
        const action=url?`data-source-url="${esc(url)}"`:isSchedule?'':`data-open-event="${esc(x.id || '')}"`;
        const date=isSchedule?formatScheduleDate(x.start_ts):'';
        const clock=isSchedule
          ? `<time class="latest-time scheduled" aria-label="Scheduled ${esc(date)}"><span>${x.time_known?esc(formatTime(x.start_ts)):''}</span><small>${esc(date)}</small><em>Scheduled</em></time>`
          : clockMarkup(pub,x.last_seen);
        const description=isSchedule?(x.description || ''):(x.what_changed || x.why_monitoring || x.previous_state || '');
        const related=isSchedule&&Array.isArray(x.related)&&x.related.length?`<div class="schedule-followed-updates"><strong>RELATED REPORTS</strong>${x.related.slice(0,3).map(r=>`<button type="button" class="schedule-related-link" data-open-event="${esc(r.id || '')}"><span>${esc(r.title || '')}</span><small>${esc((r.relationship_evidence || []).slice(0,2).join(' · '))}</small></button>`).join('')}</div>`:'';
        return `<article class="latest-row follow-up-row" ${action}>${clock}<div class="latest-thumb-slot empty"></div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc(isSchedule?x.lifecycle || x.kind || 'SCHEDULED':x.topic || 'FOLLOW-UP')}</span><h3 ${langAttr(x,x.title)}>${esc(x.title)}</h3><p ${langAttr(x,description)}>${esc(description)}</p>${related}</div><div class="latest-actions">${actionTools(x)}<button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id || '')}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></div></article>`;
      }).join('') : '<div class="empty-state">No follow-up stories are currently available.</div>';
      wireDynamicInteractions();
    } catch {
      host.querySelector('.latest-card').innerHTML = '<div class="empty-state">Follow-up intelligence is temporarily unavailable.</div>';
    }
  }

  function renderReadPage() {
    const rows = state.bootstrap?.home?.read_next || [];
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">AETHERIA READ</span><h1>Aetheria Read</h1><p class="route-sub">Context and explanation attached to current active developments.</p></div></div><div class="latest-card">${articleRows(rows.map(x => ({...x,event_id:x.id,source:{name:x.domain},published:x.latest_published || x.published})))}</div></section>`;
    wireDynamicInteractions();
  }

  async function renderUpcomingPage() {
    const host=$('mainView');
    host.innerHTML=`<section class="route-page"><div class="section-heading"><div><span class="section-kicker">SCHEDULED WATCH</span><h1>Upcoming Events</h1><p class="route-sub">Stored upcoming events from Aetheria’s schedule, with follow controls.</p></div></div><div class="latest-card">${loadingRows('Loading upcoming events...')}</div></section>`;
    const seq=++state.requestSeq;
    try {
      const d=await getJSON('/api/future');
      if(seq!==state.requestSeq)return;
      const rows=d.events||[];
      host.querySelector('.latest-card').innerHTML=rows.length?rows.map(x=>{
        const date=formatScheduleDate(x.start_ts);
        const time=x.time_known?formatTime(x.start_ts):'';
        const description=String(x.description||'').trim();
        return `<article class="latest-row schedule-row"><time class="latest-time scheduled" aria-label="Scheduled ${esc(date)}">${time?`<span>${esc(time)}</span>`:''}<small>${esc(date)}</small><em>Scheduled</em></time><div class="latest-thumb-slot empty" aria-hidden="true"></div><div class="latest-main"><span class="latest-cat ${topicClass(x.category||x.kind)}">${esc(x.category||x.kind||'SCHEDULED')}</span><h3 ${langAttr(x,x.title)}>${esc(x.title||'')}</h3>${description?`<p ${langAttr(x,description)}>${esc(description)}</p>`:''}</div><div class="latest-actions">${actionTools(x)}</div></article>`;
      }).join(''):'<div class="empty-state">No upcoming events are currently available in the schedule.</div>';
      wireDynamicInteractions();
    } catch {
      const card=host.querySelector('.latest-card');
      if(card)card.innerHTML='<div class="empty-state">Upcoming events are temporarily unavailable.</div>';
    }
  }

  function renderSearchPage() {
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">DISCOVERY</span><h1>Search</h1><p class="route-sub">Search the current Aetheria story universe.</p></div></div><div class="route-search"><input id="routeSearchInput" type="search" autocomplete="off" placeholder="Search live news, topics or sources…" value="${esc(state.searchQuery || '')}" aria-label="Search live news"><button id="routeSearchButton" class="btn-primary" type="button">Search</button></div><div class="latest-card" id="searchResults">${state.searchQuery ? loadingRows('Searching live reporting...') : '<div class="empty-state">Enter a search term.</div>'}</div></section>`;
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
    resultsHost.innerHTML = loadingRows('Searching live reporting...');
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
      const time=pub?formatPublished(pub):x.last_seen?`Observed ${formatPublished(x.last_seen)}`:'';
      const meta=[x.topic, x.status, time].filter(Boolean).join(' · ');
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
    } else if (state.route === 'Upcoming Events') {
      await renderUpcomingPage();
    } else if (state.route === 'Aetheria Read') {
      renderReadPage();
    } else if (state.route === 'Search') {
      renderSearchPage();
    } else {
      await renderArticleRoute(state.route);
    }
  }

  function resetRouteScroll() {
    const root=document.documentElement;
    const previousBehavior=root.style.scrollBehavior;
    root.style.scrollBehavior='auto';
    window.scrollTo(0,0);
    root.scrollTop=0;
    document.body.scrollTop=0;
    root.style.scrollBehavior=previousBehavior;
  }
  async function navigate(route, options={}) {
    if (!ROUTES.includes(route)) return;
    const changedView = state.route !== route;
    state.route = route;
    closeSearchDock();
    closeCategoryPanels();
    closeAppearance();
    closeStory();
    const hash = route === 'Home' ? 'Home' : route;
    if (options.history===false) history.replaceState({route}, '', `#${encodeURIComponent(hash)}`);
    else if (changedView) history.pushState({route}, '', `#${encodeURIComponent(hash)}`);
    if (!options.noScroll) resetRouteScroll();
    if (changedView || route === 'Search') await renderRoute();
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
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        const hasNestedControls=Boolean(el.querySelector('button,a[href],input,select,textarea,[contenteditable="true"]'));
        if (!el.hasAttribute('role')) el.setAttribute('role',hasNestedControls?'group':'link');
        el.setAttribute('tabindex','0');
        if(hasNestedControls && !el.hasAttribute('aria-label')){
          const title=el.querySelector('.dev-title,.india-title,.impact-text h3,.future-text h3,.latest-main h3,.changed-card h3,.banner-title,.story-title')?.textContent?.trim();
          if(title) el.setAttribute('aria-label',`Open story: ${title}`);
          el.setAttribute('aria-keyshortcuts','Enter');
        }
      }
      if(el.dataset.boundSource) return;
      el.dataset.boundSource='1';
      el.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const eventId=el.closest('.hero-feature,.dev-row,.india-feature,.list-row,.impact-row,.future-row,.latest-row,.changed-card')?.querySelector('[data-follow-event]')?.dataset.followEvent;
        if(eventId) recordTelemetry(eventId,'open');
        openSource(el.dataset.sourceUrl);
      });
    });
    document.querySelectorAll('[data-open-event]').forEach(el => {
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        const hasNestedControls=Boolean(el.querySelector('button,a[href],input,select,textarea,[contenteditable="true"]'));
        if (!el.hasAttribute('role')) el.setAttribute('role',hasNestedControls?'group':'link');
        el.setAttribute('tabindex','0');
        if(hasNestedControls && !el.hasAttribute('aria-label')){
          const title=el.querySelector('.dev-title,.india-title,.impact-text h3,.future-text h3,.latest-main h3,.changed-card h3,.banner-title,.story-title')?.textContent?.trim();
          if(title) el.setAttribute('aria-label',`Open story: ${title}`);
          el.setAttribute('aria-keyshortcuts','Enter');
        }
      }
      if(el.dataset.boundEvent) return;
      el.dataset.boundEvent='1';
      el.onclick = e => { e.preventDefault(); e.stopPropagation(); openStory(el.dataset.openEvent); };
    });
    document.querySelectorAll('[data-open-story]').forEach(el => {
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        el.setAttribute('role','link');
        el.setAttribute('tabindex','0');
      }
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
          if(!d.ok || d.error) throw new Error(d.error || 'Follow action failed');
          const ids=followedIds();
          if(d.following) ids.add(eid); else ids.delete(eid);
          state.followUp={...(state.followUp || {}),followed_ids:[...ids]};
          try { state.followUp=await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`); } catch {}
          await renderRoute();
          announceAction(d.following?'Article successfully added to Follow-Up.':'Article removed from Follow-Up.');
        } catch { btn.disabled=false; announceAction('Follow-Up could not be updated.'); }
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
          if(!d.ok || d.error) throw new Error(d.error || 'Unfollow failed');
          state.followUp=await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
          await renderRoute();
          announceAction('Article removed from Follow-Up.');
        } catch { btn.disabled=false; announceAction('Follow-Up could not be updated.'); }
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
    observeStoryExposure();
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
      const followRequest=state.followUp?Promise.resolve(state.followUp):getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`).catch(()=>null);
      const [d,follow]=await Promise.all([getJSON('/api/bootstrap', {timeout:9000}),followRequest]);
      state.bootstrap = d;
      if (follow) state.followUp=follow;
      renderMarkets(d.market || {});
      renderBanner();
      if (d.warming_up && state.route==='Home') {
        $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">STARTING AETHERIA</span><h1>Preparing live reporting</h1><p class="route-sub">${d.startup_error ? 'Startup needs attention; see the server console for details.' : 'The local database and current story snapshot are loading.'}</p></div></div><div class="latest-card">${loadingRows('Preparing the live story universe...')}</div></section>`;
        return;
      }
      if (state.route === 'Home' || forceRender) await renderRoute();
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
    window.addEventListener('popstate', () => { const r=decodeURIComponent(location.hash.replace(/^#/,'') || 'Home'); if(ROUTES.includes(r))navigate(r,{history:false}); });
    document.addEventListener('keydown', e => {
      if(e.key==='Escape'){
        closeCategoryPanels(); closeAppearance(); closeSearchDock();
        if(storyModalOpen()) closeStory();
        return;
      }
      if(storyModalOpen() && e.key==='Tab'){
        const modal=$('storyModal');
        const focusable=[...modal.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')]
          .filter(el=>el.getClientRects().length>0);
        if(!focusable.length){e.preventDefault();$('storyClose')?.focus();return;}
        const first=focusable[0], last=focusable[focusable.length-1], active=document.activeElement;
        if(e.shiftKey && (active===first || !modal.contains(active))){e.preventDefault();last.focus();}
        else if(!e.shiftKey && (active===last || !modal.contains(active))){e.preventDefault();first.focus();}
        return;
      }
      if(e.key!=='Enter') return;
      if(e.target.closest('button,a,input,select,textarea,[contenteditable="true"]')) return;
      const row=e.target.closest('[data-source-url][tabindex="0"],[data-open-event][tabindex="0"],[data-open-story][tabindex="0"]');
      if(row){e.preventDefault();row.click();}
    });
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
    state.refreshTimer=setInterval(()=>{
      refreshBootstrap(false);
      if(state.bootstrap?.ready){clearInterval(state.refreshTimer);state.refreshTimer=setInterval(()=>refreshBootstrap(false),10000);}
    },1000);
    setInterval(()=>{ if(state.route!=='Home') return; renderBanner(); },15000);
  }
  init();
})();
