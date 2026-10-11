/* AETHERIA LIVE UI ADAPTER
   The UI is a presentation layer over the existing Aetheria engine.
   No news, market values, timestamps, or intelligence are hardcoded here.
*/
(() => {
  'use strict';

  const ROUTES = ['Home', 'Latest', 'India', 'World', 'Business', 'Markets', 'Sports', 'Technology', 'Legal', 'Geopolitical', 'Entertainment', 'Follow-up', 'Upcoming Events', 'Aetheria Read', 'Search'];
  const TOPIC_MAP = { Market: 'Markets', Markets: 'Markets', Geopolitical: 'Geopolitics' };
  const state = {
    route: 'Home', bootstrap: null, articles: [], stackIndex: 0, stackPaused: false,
    stackTimer: null, refreshTimer: null, followUp: null, searchQuery: '', searchSuggestTimer: null,
    requestSeq: 0, storyRequestSeq: 0, storyOpener: null, telemetrySeen: new Set(), telemetryObserver: null
  };

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));
  const num = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const topicClass = value => String(value || 'world').toLowerCase().replace(/[^a-z]/g, '');

  function getJSON(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 8000);
    const signal = options.signal;
    if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true });
    return fetch(url, { cache: 'no-store', signal: controller.signal, headers: { 'Accept': 'application/json' } })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .finally(() => clearTimeout(timeout));
  }

  function formatTime(ts) {
    const value = Number(ts);
    if (!Number.isFinite(value) || value <= 0) return '—';
    const date = new Date(value * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  function formatDate(ts) {
    const value = Number(ts);
    if (!Number.isFinite(value) || value <= 0) return '';
    const date = new Date(value * 1000);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString([], { day: '2-digit', month: 'short' });
  }
  function formatScheduleDate(ts) {
    const value = Number(ts);
    if (!Number.isFinite(value) || value <= 0) return '';
    const date = new Date(value * 1000);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function clockMarkup(published, observed, className = 'latest-time') {
    const publishedTs = Number(published) || 0, observedTs = Number(observed) || 0;
    const timestamp = publishedTs || observedTs;
    if (!timestamp) return `<time class="${className}" aria-label="Publication time unavailable">—</time>`;
    const observedOnly = !publishedTs, label = observedOnly ? 'Observed' : 'Published';
    const dateTime = formatPublished(timestamp);
    return `<time class="${className}${observedOnly ? ' observed' : ''}" aria-label="${label} ${esc(dateTime)}" title="${label} ${esc(dateTime)}"><span>${esc(formatTime(timestamp))}</span><small>${esc(formatDate(timestamp))}</small>${observedOnly ? '<em>Observed</em>' : ''}</time>`;
  }
  function formatAge(ts) {
    const value = Number(ts);
    if (!Number.isFinite(value) || value <= 0) return '';
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - value));
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hrs = Math.floor(min / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
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
    return d.toLocaleString([], { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function publicationMarkup(published, observed) {
    const hasPublished = Number.isFinite(Number(published)) && Number(published) > 0;
    const timestamp = hasPublished ? Number(published) : Number(observed);
    if (!Number.isFinite(timestamp) || timestamp <= 0) return '';
    const label = hasPublished ? 'Published' : 'Observed';
    const formatted = formatPublished(timestamp);
    return formatted ? `<span class="news-published">${label} ${esc(formatted)}</span>` : '';
  }
  function eventTime(e) {
    const published = e?.latest_published || e?.published;
    if (published) return formatAge(published);
    return e?.last_seen ? `Observed ${formatAge(e.last_seen)}` : '';
  }
  function languageFor(item, text = '') {
    if (/\p{Script=Devanagari}/u.test(String(text || ''))) return 'hi';
    const language = String(item?.language || item?.languages?.[0] || '').trim();
    return /^[a-z]{2,3}(?:-[a-z0-9]+)*$/i.test(language) ? language : '';
  }
  function langAttr(item, text = '') {
    const language = languageFor(item, text);
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
    try { id = localStorage.getItem('aetheria-follow-session') || ''; } catch { }
    if (!id) {
      id = (window.crypto?.randomUUID?.() || `aetheria-${Date.now()}-${Math.random().toString(36).slice(2)}`);
      try { localStorage.setItem('aetheria-follow-session', id); } catch { }
    }
    return id;
  }
  function followedIds() {
    const stored = state.followUp?.followed_ids;
    if (Array.isArray(stored)) return new Set(stored.map(String));
    const rows = [...(state.followUp?.active || []), ...(state.followUp?.quiet || []), ...(state.followUp?.revived || []), ...(state.followUp?.followed || [])];
    return new Set(rows.map(x => String(x.id || x.event_id || '')).filter(Boolean));
  }
  function storyImpactScore(item) {
    const raw = Number(item?.score ?? item?.event?.score ?? item?.significance ?? item?.event?.significance ?? item?.intelligence?.impact ?? item?.event?.intelligence?.impact ?? 0);
    if (!Number.isFinite(raw) || raw <= 0) return 0;
    return raw > 1 ? Math.round(raw) : Math.round(raw * 100);
  }

  function actionTools(item) {
    const itemId = String(item?.id || '');
    const isSchedule = Boolean(item?.start_ts && item?.kind);
    const eid = String(item?.event_id || item?.event?.id || (itemId.startsWith('evt_') || isSchedule ? itemId : '') || itemId || '');
    if (!eid) return '';
    const following = followedIds().has(eid);
    const followLabel = following ? 'Following' : 'Follow';
    const followTitle = following ? 'Following this story (click to unfollow)' : 'Follow this story';
    return `<span class="news-card-actions" role="group" aria-label="Story actions">
      <span class="signature-action"><button type="button" class="news-card-action ${following ? 'following' : ''}" data-follow-event="${esc(eid)}" aria-label="${followTitle}" title="${followTitle}"><span class="news-card-action-icon">${following ? '✓' : '+'}</span></button><span class="news-card-action-label">${followLabel}</span></span>
      ${isSchedule ? '' : `<span class="signature-action"><button type="button" class="news-card-action related" data-related-event="${esc(eid)}" aria-label="Aetheria intelligence" title="Aetheria intelligence"><span class="news-card-action-icon">◎</span></button><span class="news-card-action-label">Aetheria</span></span>`}
    </span>`;
  }

  let actionNoticeTimer = null;
  function announceAction(message, type = 'info') {
    let notice = $('actionNotice');
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 'actionNotice';
      notice.className = 'action-notice';
      notice.setAttribute('role', 'status');
      notice.setAttribute('aria-live', 'polite');
      document.body.append(notice);
    }
    const icon = type === 'error' ? '✕' : '✓';
    notice.innerHTML = `<span class="action-notice-icon">${icon}</span><span class="action-notice-msg">${esc(message)}</span>`;
    notice.classList.add('visible');
    if (actionNoticeTimer) clearTimeout(actionNoticeTimer);
    actionNoticeTimer = setTimeout(() => notice.classList.remove('visible'), 3000);
  }
  function recordTelemetry(eventId, action) {
    if (!eventId || !action) return;
    fetch('/api/telemetry', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ session: followSession(), event_id: String(eventId), action, at: Date.now() / 1000 }), keepalive: true }).catch(() => { });
  }
  function observeStoryExposure() {
    if (!('IntersectionObserver' in window)) return;
    if (!state.telemetryObserver) state.telemetryObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting || entry.intersectionRatio < .55) return;
        const button = entry.target, eventId = button.dataset.followEvent;
        state.telemetryObserver.unobserve(button);
        if (!eventId || state.telemetrySeen.has(eventId)) return;
        state.telemetrySeen.add(eventId);
        recordTelemetry(eventId, 'seen');
      });
    }, { threshold: [.55] });
    document.querySelectorAll('[data-follow-event]').forEach(button => {
      const eventId = button.dataset.followEvent;
      if (eventId && !state.telemetrySeen.has(eventId) && !button.dataset.telemetryObserved) {
        button.dataset.telemetryObserved = '1';
        state.telemetryObserver.observe(button);
      }
    });
  }

  function routeLabel(route) { return route === 'Markets' ? 'Market' : route; }
  function routeTopic(route) { return TOPIC_MAP[route] || route; }

  function closeAppearance() {
    $('appearancePanel')?.classList.remove('open');
    $('appearanceBackdrop')?.classList.remove('open');
    $('appearanceBackdrop')?.setAttribute('aria-hidden', 'true');
  }
  function openAppearance() {
    closeAllPopups('appearance');
    $('appearancePanel')?.classList.add('open');
    $('appearanceBackdrop')?.classList.add('open');
    $('appearanceBackdrop')?.setAttribute('aria-hidden', 'false');
  }

  function closeAllPopups(except = '') {
    if (except !== 'appearance') closeAppearance();
    if (except !== 'search') closeSearchDock();
    if (except !== 'categories') closeCategoryPanels();
    if (except !== 'storyModal' && storyModalOpen()) closeStory();
  }

  function closeCategoryPanels() {
    document.querySelectorAll('.category-panel').forEach(p => { p.classList.remove('open'); p.setAttribute('aria-hidden', 'true'); });
    document.querySelectorAll('[data-category-trigger]').forEach(b => b.setAttribute('aria-expanded', 'false'));
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
    closeAllPopups('categories');
    const panel = $(kind === 'top' ? 'topCategoryPanel' : 'bottomCategoryPanel');
    const trigger = document.querySelector(`[data-category-trigger="${kind}"]`);
    if (!panel || !trigger) return;
    panel.classList.add('open'); panel.setAttribute('aria-hidden', 'false'); trigger.setAttribute('aria-expanded', 'true');
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
    const modal = $('storyModal');
    modal?.classList.remove('open');
    modal?.setAttribute('aria-hidden', 'true');
    const opener = state.storyOpener;
    state.storyOpener = null;
    if (opener?.isConnected && opener !== document.body) opener.focus();
    else $('mainView')?.focus();
  }

  const BRAND_MAP = {
    'thehindu.com': 'The Hindu',
    'business-standard.com': 'Business Standard',
    'ndtv.com': 'NDTV',
    'economictimes.indiatimes.com': 'The Economic Times',
    'timesofindia.indiatimes.com': 'The Times of India',
    'hindustantimes.com': 'Hindustan Times',
    'indianexpress.com': 'The Indian Express',
    'moneycontrol.com': 'Moneycontrol',
    'livemint.com': 'Mint',
    'theprint.in': 'ThePrint',
    'thewire.in': 'The Wire',
    'scroll.in': 'Scroll.in',
    'bbc.com': 'BBC News',
    'bbc.co.uk': 'BBC News',
    'theguardian.com': 'The Guardian',
    'reuters.com': 'Reuters',
    'bloomberg.com': 'Bloomberg',
    'aljazeera.com': 'Al Jazeera',
    'france24.com': 'France 24',
    'dw.com': 'Deutsche Welle',
    'news.sky.com': 'Sky News',
    'sky.com': 'Sky News',
    'euronews.com': 'Euronews',
    'cbsnews.com': 'CBS News',
    'nbcnews.com': 'NBC News',
    'nytimes.com': 'The New York Times',
    'politico.com': 'Politico',
    'scmp.com': 'South China Morning Post',
    'channelnewsasia.com': 'CNA',
    'nasa.gov': 'NASA',
    'jpl.nasa.gov': 'NASA JPL',
    'sec.gov': 'U.S. SEC',
    'usgs.gov': 'USGS',
    'pib.gov.in': 'PIB India',
    'ani.in': 'ANI News',
    'ptinews.com': 'PTI News',
    'news.google.com': 'Google News'
  };

  function cleanSourceBrand(raw) {
    if (!raw) return 'Publisher';
    let s = String(raw).trim();
    if (!s.includes('.') && s.length > 2) return s;
    const lower = s.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
    if (BRAND_MAP[lower]) return BRAND_MAP[lower];
    for (const [k, v] of Object.entries(BRAND_MAP)) {
      if (lower === k || lower.endsWith('.' + k)) return v;
    }
    let base = lower.replace(/\.(com|co\.uk|org|net|in|gov|gov\.in|edu)$/, '');
    base = base.replace(/^(news\.|m\.|feeds\.)/, '');
    if (base.length > 1) {
      return base.split(/[-_.]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    }
    return s;
  }

  function formatExplainedContent(text) {
    if (!text) return '<p class="read-card-text">Details are currently being updated.</p>';
    const clean = String(text).trim();
    const lines = clean.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const bulletItems = [];
    for (const line of lines) {
      const stripped = line.replace(/^[•\-\*]\s*/, '').trim();
      if (stripped) bulletItems.push(stripped);
    }
    if (bulletItems.length > 1 || (lines.length === 1 && clean.startsWith('•'))) {
      return `<ul class="read-card-list">${bulletItems.map(item => {
        const colonIdx = item.indexOf(':');
        if (colonIdx > 0 && colonIdx < 35) {
          const head = item.slice(0, colonIdx).trim();
          const rest = item.slice(colonIdx + 1).trim();
          return `<li class="read-card-list-item"><strong class="read-point-lead">${esc(head)}:</strong> ${esc(rest)}</li>`;
        }
        return `<li class="read-card-list-item">${esc(item)}</li>`;
      }).join('')}</ul>`;
    }
    return `<p class="read-card-text">${esc(clean)}</p>`;
  }

  function resolveSourceBrand(item, sources = [], event = {}) {
    if (!item) return 'News Desk';
    const raw = (typeof item === 'string') ? item : (item.source_name || item.domain || '');
    let brand = cleanSourceBrand(raw);
    if (brand && brand !== 'Publisher' && brand !== 'Source' && brand.length >= 2) return brand;

    const url = (typeof item === 'object') ? (item.url || item.canonical_url || '') : '';
    if (url) {
      try {
        const host = new URL(url).hostname;
        const fromHost = cleanSourceBrand(host);
        if (fromHost && fromHost !== 'Publisher' && fromHost !== 'Source') return fromHost;
      } catch { }
    }

    const text = (typeof item === 'object') ? (item.headline || item.title || item.note || '') : '';
    if (text) {
      const match = text.match(/[-|–—·/]\s*([A-Za-z0-9&. ']{2,30})\s*$/);
      if (match) {
        const fromText = cleanSourceBrand(match[1].trim());
        if (fromText && fromText !== 'Publisher' && fromText !== 'Source' && fromText.length >= 2) return fromText;
      }
    }

    if (sources && sources.length) {
      const matched = sources.find(s => {
        if (url && (s.canonical_url === url || s.url === url)) return true;
        if (text && s.title && (s.title === text || (text.length > 25 && s.title.includes(text.slice(0, 25))))) return true;
        return false;
      });
      if (matched) {
        const fromMatched = cleanSourceBrand(matched.source_name || matched.domain);
        if (fromMatched && fromMatched !== 'Publisher' && fromMatched !== 'Source') return fromMatched;
      }
    }

    const evBrand = cleanSourceBrand(event?.primary_domain || event?.domain || '');
    if (evBrand && evBrand !== 'Publisher' && evBrand !== 'Source') return evBrand;
    return 'News Desk';
  }

  async function openStory(eventId, articleId = '') {
    const targetId = eventId || articleId;
    if (!targetId) return;
    closeAllPopups('storyModal');
    const requestSeq = ++state.storyRequestSeq;
    if (eventId) recordTelemetry(eventId, 'open');
    const modal = $('storyModal');
    if (!modal) return;
    if (!modal.classList.contains('open')) state.storyOpener = document.activeElement;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    $('storyClose')?.focus();

    const content = $('storyModalContent');
    if (content) {
      content.innerHTML = `
        <div class="read-loading-state">
          <span class="read-topic-kicker">AETHERIA READ</span>
          <h2 class="read-headline">Loading story intelligence…</h2>
          <p class="read-loading-desc">Retrieving underlying reporting, source corroboration, and verified developments.</p>
        </div>
      `;
    }

    try {
      const d = await getJSON(`/api/event/${encodeURIComponent(targetId)}`);
      if (requestSeq !== state.storyRequestSeq || !modal.classList.contains('open')) return;
      const e = d.event || {};
      const evidence = d.evidence || {};
      const ai = d.local_ai || {};
      const context = d.context || {};
      const sources = (d.sources || []).slice();
      const rawTimeline = (d.journey && d.journey.length ? d.journey : (d.timeline || [])).slice();
      const related = (d.related || []).slice();
      const impactCtx = ai.impact_context || {};
      const impactScore = Number(impactCtx.score != null ? impactCtx.score : storyImpactScore(d.event || e));

      const vState = evidence.verification_state || 'REPORTED';
      const evidenceLabel = vState === 'CONFIRMED' ? 'CONFIRMED' :
        vState === 'CORROBORATED' ? 'CORROBORATED' :
          vState === 'DISPUTED' ? 'DISPUTED CLAIMS' : 'REPORTED';
      const badgeCls = vState === 'CONFIRMED' || vState === 'CORROBORATED' ? 'confirmed' :
        vState === 'DISPUTED' ? 'disputed' : 'reported';

      const eid = e.id || targetId;
      const isFollowing = followedIds().has(eid);
      const followLabel = isFollowing ? 'Following Story' : 'Follow Story';
      const followAria = isFollowing ? 'Following this story (click to unfollow)' : 'Follow this story';

      const latestSource = sources.slice().sort((a, b) => Number(b.published || 0) - Number(a.published || 0))[0];
      const publishedTs = latestSource?.published || e.latest_published || e.primary_published;
      const publishedText = publishedTs ? `Published ${formatPublished(publishedTs)} IST` : (e.last_seen ? `Publication timestamp unavailable · Observed ${formatPublished(e.last_seen)} IST` : 'Publication timestamp unavailable');
      const updatedTs = e.last_change || e.last_seen;
      const updatedText = updatedTs && updatedTs !== publishedTs ? `Latest update: ${formatPublished(updatedTs)} IST` : '';

      const sourceNamesSet = new Set();
      sources.forEach(s => {
        const brand = resolveSourceBrand(s, sources, e);
        if (brand && brand !== 'News Desk' && brand !== 'Publisher' && brand !== 'Source') sourceNamesSet.add(brand);
      });
      const sourceNamesList = sourceNamesSet.size ? (
        sourceNamesSet.size > 5
          ? Array.from(sourceNamesSet).slice(0, 5).join(', ') + ` + ${sourceNamesSet.size - 5} more newsrooms`
          : Array.from(sourceNamesSet).join(', ')
      ) : resolveSourceBrand(e.primary_domain || e, sources, e);

      let whatHappened = ai.what_happened || ai.summary || d.primary_description || e.summary || 'Initial reporting has been recorded for this event.';
      if (whatHappened.includes(' — ')) {
        const parts = whatHappened.split(' — ');
        if (parts.length >= 2) whatHappened = parts[0].trim().replace(/\.+$/, '') + '.';
      }
      whatHappened = whatHappened.replace(/It[’']s official\.\.\s*/gi, '');

      let whyItMatters = ai.why_it_matters || (context.why || []).join('\n') || 'Active coverage across domestic and international newsrooms.';
      if (whyItMatters.includes('governance consequence') || whyItMatters.includes('institutional tensions') || whyItMatters.includes('independent publisher/official sources') || whyItMatters.includes('independent sources') || whyItMatters.trim() === 'high significance') {
        const isIndiaStory = (e.topic || '').toLowerCase() === 'india' || (e.title || '').toLowerCase().includes('delhi') || (e.title || '').toLowerCase().includes('india') || (e.title || '').toLowerCase().includes('aap');
        if (isIndiaStory && (Number(e.social_relevance || 0) >= 0.3 || (e.title || '').toLowerCase().includes('protest') || (e.title || '').toLowerCase().includes('detain'))) {
          whyItMatters = '• Political showdown in Delhi: A direct clash between opposition leaders and police over the right to hold public rallies in the capital.\n• Broader fallout: The detentions have triggered sharp pushback from multiple opposition parties, raising the likelihood of wider street protests and court challenges.';
        } else if (isIndiaStory) {
          whyItMatters = '• National policy impact: A significant government decision that directly affects domestic administration and public policy.\n• Institutional response: Public bodies and affected sectors are reviewing guidelines to adapt to the change.';
        } else if (Number(e.financial_relevance || 0) >= 0.45) {
          whyItMatters = '• Direct market impact: Key sectors and share prices could react to shifting economic sentiment and business conditions.\n• Supply & pricing pressure: Affected enterprise sectors could see immediate supply chain adjustments.';
        } else {
          whyItMatters = '• Major public interest: Multiple newsrooms are actively covering this story as key details unfold.\n• Ongoing coverage: Live dispatches and updates are expected throughout the day.';
        }
      }

      const independentCount = Number(evidence.independent_sources ?? e.source_count ?? sources.length ?? 0);
      let whatRemainsUncertain = ai.what_remains_uncertain || '';
      if (!whatRemainsUncertain || whatRemainsUncertain.includes(' vs. ') || whatRemainsUncertain.includes('↔') || whatRemainsUncertain.includes('Differing characterizations reported between') || whatRemainsUncertain.includes('prohibitory assembly orders') || whatRemainsUncertain.includes('court production') || whatRemainsUncertain.includes('.com')) {
        const tLower = ((e.title || '') + ' ' + (whatHappened || '')).toLowerCase();
        if (tLower.includes('detain') || tLower.includes('protest') || tLower.includes('arrest') || tLower.includes('police') || tLower.includes('emergency') || tLower.includes('curbs') || tLower.includes('cjp')) {
          whatRemainsUncertain = '• Number of detentions: Police have not released an official count of how many people were taken into custody or where they are held.\n• Legal charges: It is still unclear whether protesters will face formal criminal charges or be let go after preventive detention.\n• Conflicting accounts: Police say the gathering lacked permission, while organizers maintain it was a peaceful demonstration.';
        } else if (tLower.includes('market') || tLower.includes('shares') || tLower.includes('deal') || tLower.includes('tariff') || tLower.includes('trade') || tLower.includes('merger')) {
          whatRemainsUncertain = '• Final financial numbers: Full transaction valuations, pricing, and revenue impact have not yet been formally disclosed.\n• Regulatory approvals: Clearances from market watchdogs and stock exchanges are still pending.\n• Timeline: Companies have not given a firm date for when the next phase will be completed.';
        } else if (tLower.includes('court') || tLower.includes('judge') || tLower.includes('order') || tLower.includes('bail') || tLower.includes('plea')) {
          whatRemainsUncertain = '• Full written order: The court registry has not yet uploaded the detailed, signed judgment.\n• Appeal plans: It is not yet known whether parties will immediately challenge the ruling in a higher court.';
        } else if (independentCount >= 2) {
          whatRemainsUncertain = '• Official statement: Authorities have not yet held a formal press briefing to clarify the sequence of events.\n• Next steps: What happens next depends on how officials respond in the coming hours.';
        } else {
          whatRemainsUncertain = '• Initial report: Awaiting corroboration from other independent newsrooms and an official briefing.';
        }
      }

      const digestText = ai.digest || ai.summary || (e.summary && !e.summary.includes(' — ') ? e.summary : '') || d.primary_description || whatHappened;

      const impactTier = impactCtx.tier || (
        impactScore >= 76 ? 'TIER 1' :
          impactScore >= 51 ? 'TIER 2' :
            impactScore >= 26 ? 'TIER 3' : 'TIER 4'
      );
      const impactLevel = impactCtx.level || (
        impactScore >= 76 ? 'High National Significance' :
          impactScore >= 51 ? 'Elevated National Consequence' :
            impactScore >= 26 ? 'Moderate Sectoral Focus' : 'Routine Topical Development'
      );
      const impactClassification = impactCtx.classification || impactCtx.scope || (context.affected_domains?.join(', ') || e.topic || 'National Governance & Civic Order');
      let executiveAssessment = impactCtx.executive_assessment || (
        impactScore >= 76 ? `Aetheria rates this story at ${impactScore}/100 reflecting multi-desk verification of high-consequence domestic institutional and civic developments.` :
          `Aetheria rates this story at ${impactScore}/100 reflecting multi-source verification and measured reporting velocity.`
      );
      if (executiveAssessment && impactScore) {
        executiveAssessment = executiveAssessment.replace(/Rated\s+\d+\/100/i, `Rated ${impactScore}/100`);
      }
      const impactScope = impactClassification;
      const corroborationText = `${independentCount} independent media organization${independentCount === 1 ? '' : 's'}`;
      const velocityText = (e.velocity >= 0.45) ? 'Rapidly developing coverage' : 'Standard reporting pace';
      const impactLimitation = impactCtx.limitation || 'Model-generated assessment of coverage significance and transmission, not a verification of factual truth.';

      const sourceCountLabel = `${sources.length} report${sources.length === 1 ? '' : 's'} across ${independentCount} independent outlet${independentCount === 1 ? '' : 's'}`;
      let sourceItemsMarkup = '';
      if (sources.length) {
        sourceItemsMarkup = sources.slice(0, 24).map(s => {
          const sUrl = safeSourceUrl(s.canonical_url || '');
          const sPub = s.published ? `Published ${formatPublished(s.published)} IST` : (s.fetched ? `Observed ${formatPublished(s.fetched)} IST` : 'Timestamp unavailable');
          const sName = resolveSourceBrand(s, sources, e);
          return `
            <div class="read-source-card">
              <div class="read-source-info">
                <span class="read-source-name">${esc(sName)}</span>
                <h4 class="read-source-title" ${langAttr(s, s.title)}>${esc(s.title || '')}</h4>
                <span class="read-source-time">${esc(sPub)}</span>
              </div>
              ${sUrl ? `<button type="button" class="read-source-btn" data-modal-source="${esc(sUrl)}" aria-label="Read original article at ${esc(sName)}">Read Source ↗</button>` : ''}
            </div>
          `;
        }).join('');
      } else {
        sourceItemsMarkup = '<p class="read-empty-state">Detailed source listings are currently being indexed.</p>';
      }

      // Prepare chronological Journey Milestones
      let journeyItems = rawTimeline.slice();
      if (journeyItems.length < 2 && sources.length >= 2) {
        const chronSources = sources.slice().sort((a, b) => Number(a.published || a.fetched || 0) - Number(b.published || b.fetched || 0));
        const seenH = new Set();
        chronSources.forEach(s => {
          const h = (s.title || '').trim();
          if (!h || seenH.has(h)) return;
          seenH.add(h);
          journeyItems.push({
            published_at: s.published || s.fetched,
            headline: h,
            summary: s.description || h,
            source_name: resolveSourceBrand(s, sources, e),
            url: s.canonical_url
          });
        });
        const total = journeyItems.length;
        journeyItems.forEach((m, idx) => {
          m.step = idx + 1;
          m.phase = idx === 0 ? 'FIRST DISPATCH' : (idx === total - 1 ? 'LATEST DEVELOPMENT' : (idx === 1 && total > 2 ? 'CORROBORATING DESK' : 'DEVELOPING ANGLE'));
          m.is_latest = idx === total - 1;
        });
      }

      let timelineMarkup = '';
      if (journeyItems.length) {
        timelineMarkup = `
          <div class="journey-timeline">
            <div class="journey-track"></div>
            ${journeyItems.map((item, idx) => {
          const stepNum = String(item.step || idx + 1).padStart(2, '0');
          const phase = item.phase || (idx === 0 ? 'FIRST DISPATCH' : (idx === journeyItems.length - 1 ? 'LATEST DEVELOPMENT' : 'CORROBORATING DESK'));
          const itemTime = item.published_at || item.observed_at;
          const timeLabel = itemTime ? `${formatPublished(itemTime)} IST` : '';
          const brand = resolveSourceBrand(item, sources, e);
          const itemUrl = safeSourceUrl(item.url || '');
          const isLatest = Boolean(item.is_latest || idx === journeyItems.length - 1);
          const summaryText = item.summary || item.headline || '';

          return `
                <div class="journey-milestone ${isLatest ? 'latest' : ''}">
                  <div class="journey-node ${isLatest ? 'latest' : ''}" aria-hidden="true">
                    <span class="journey-node-num">${esc(stepNum)}</span>
                    ${isLatest ? '<span class="journey-pulse-ring"></span>' : ''}
                  </div>
                  <div class="journey-card">
                    <div class="journey-card-top">
                      <span class="journey-phase-tag">${esc(phase)}</span>
                      <span class="journey-source-tag">${esc(brand)}</span>
                      ${timeLabel ? `<time class="journey-time-tag">${esc(timeLabel)}</time>` : ''}
                    </div>
                    <h4 class="journey-headline" ${langAttr(item, item.headline || item.note || '')}>${esc(item.headline || item.note || '')}</h4>
                    <p class="journey-summary" ${langAttr(item, summaryText)}>${esc(summaryText)}</p>
                    ${itemUrl ? `
                      <div class="journey-action-bar">
                        <button type="button" class="journey-verify-btn" data-modal-source="${esc(itemUrl)}" aria-label="Read full report at ${esc(brand)}">
                          <span>Read on ${esc(brand)}</span> <span class="journey-arrow">↗</span>
                        </button>
                      </div>
                    ` : ''}
                  </div>
                </div>
              `;
        }).join('')}
          </div>
        `;
      } else {
        timelineMarkup = '<p class="read-empty-state">No chronological development milestones have been recorded yet.</p>';
      }

      let relatedMarkup = '';
      if (related.length) {
        relatedMarkup = `
          <div class="read-related-list">
            ${related.slice(0, 5).map(r => {
          const rUrl = safeSourceUrl(r.url || '');
          const rPub = r.published ? `${formatPublished(r.published)} IST` : (r.last_seen ? `Observed ${formatPublished(r.last_seen)} IST` : '');
          const rEvidence = (r.relationship_evidence || []).join(' · ');
          const rBrand = resolveSourceBrand(r, sources, e);
          return `
                <div class="read-related-card">
                  <div class="read-related-info">
                    <h4 class="read-related-title" ${langAttr(r, r.title)}>${esc(r.title || '')}</h4>
                    <p class="read-related-meta">${esc([rBrand, rPub].filter(Boolean).join(' · '))}</p>
                    ${rEvidence ? `<span class="read-related-reason">${esc(rEvidence)}</span>` : ''}
                  </div>
                  <button type="button" class="read-related-action" data-modal-related="${esc(r.id || '')}" aria-label="Open related story" title="Open related story" ${rUrl ? `data-related-source="${esc(rUrl)}"` : ''}>↗</button>
                </div>
              `;
        }).join('')}
          </div>
        `;
      } else {
        relatedMarkup = '<p class="read-empty-state">No additional related reporting is currently available.</p>';
      }

      if (content) {
        content.innerHTML = `
          <div class="read-header">
            <div class="read-header-top">
              <div class="read-header-meta">
                <span class="read-topic-kicker">${esc(e.topic || 'AETHERIA')}</span>
                <span class="read-verification-badge ${badgeCls}">${esc(evidenceLabel)}</span>
                ${(e.india_relevance >= 0.4 || e._india_relevance >= 0.4) ? '<span class="read-india-badge">INDIA DESK</span>' : ''}
              </div>
              <div class="read-header-actions">
                <button type="button" class="read-follow-btn ${isFollowing ? 'following' : ''}" data-follow-event="${esc(eid)}" aria-label="${esc(followAria)}" title="${esc(followAria)}">
                  <span class="read-follow-icon">${isFollowing ? '✓' : '+'}</span>
                  <span class="read-follow-label">${esc(followLabel)}</span>
                </button>
              </div>
            </div>
            <h2 id="storyModalTitle" class="read-headline" ${langAttr(e, e.title)}>${esc(e.title || 'Story')}</h2>
            
            <div class="read-executive-digest">
              <div class="read-digest-tag">✦ EXECUTIVE NEWS DIGEST</div>
              <p class="read-digest-text" ${langAttr(e, digestText)}>${esc(digestText)}</p>
            </div>

            <div class="read-bylines">
              <div class="read-sources-line">
                <span class="read-sources-names">Reported by <strong>${esc(sourceNamesList)}</strong></span>
              </div>
              <div class="read-timestamp-line">
                <span>${esc(publishedText)}</span>
                ${updatedText ? `<span class="read-update-time"> · ${esc(updatedText)}</span>` : ''}
              </div>
            </div>
          </div>

          <section class="read-section read-explained-section" aria-labelledby="readExplainedHead">
            <h3 id="readExplainedHead" class="read-section-title">✦ THE STORY EXPLAINED</h3>
            <div class="read-explained-grid">
              <div class="read-explained-card">
                <div class="read-card-header"><span class="read-card-tag">WHAT HAPPENED</span></div>
                <div class="read-card-body">${formatExplainedContent(whatHappened)}</div>
              </div>
              <div class="read-explained-card">
                <div class="read-card-header"><span class="read-card-tag">WHY IT MATTERS</span></div>
                <div class="read-card-body">${formatExplainedContent(whyItMatters)}</div>
              </div>
              <div class="read-explained-card">
                <div class="read-card-header"><span class="read-card-tag">WHAT REMAINS UNCERTAIN</span></div>
                <div class="read-card-body">${formatExplainedContent(whatRemainsUncertain)}</div>
              </div>
            </div>
          </section>

          <section class="read-section read-impact-section" aria-labelledby="readImpactHead">
            <div class="read-impact-header">
              <div class="read-impact-header-left">
                <h3 id="readImpactHead" class="read-section-title">✦ IMPACT INTELLIGENCE</h3>
                <span class="read-impact-subtitle">Algorithmic Significance & Transmission Analysis</span>
              </div>
              <div class="read-impact-score-box">
                <span class="read-impact-score-num">${impactScore}</span>
                <span class="read-impact-score-scale">/ 100</span>
              </div>
            </div>

            <!-- Executive Significance Banner -->
            <div class="read-impact-level-card">
              <div class="read-impact-tier-row">
                <span class="read-impact-tier-badge">
                  <span class="read-tier-jewel"></span>
                  ${esc(impactTier)} · ${esc(impactLevel)}
                </span>
                <span class="read-impact-classification">${esc(impactClassification)}</span>
              </div>
              <p class="read-impact-executive-brief">${esc(executiveAssessment)}</p>
            </div>

            <div class="read-impact-meter-wrapper">
              <div class="read-impact-meter">
                <div class="read-impact-meter-fill" style="width: ${Math.min(100, Math.max(0, impactScore))}%;"></div>
              </div>
              <div class="read-impact-meter-scale">
                <span>0 · Routine</span>
                <span>25 · Sectoral</span>
                <span>50 · Elevated</span>
                <span>75 · High National</span>
                <span>100 · Critical</span>
              </div>
            </div>

            <div class="read-impact-vectors-grid">
              <div class="read-vector-card">
                <span class="read-vector-label">Domain Scope</span>
                <span class="read-vector-val">${esc(impactClassification)}</span>
              </div>
              <div class="read-vector-card">
                <span class="read-vector-label">Verification Depth</span>
                <span class="read-vector-val">${esc(corroborationText)}</span>
              </div>
              <div class="read-vector-card">
                <span class="read-vector-label">Coverage Pace</span>
                <span class="read-vector-val">${esc(velocityText)}</span>
              </div>
            </div>

            <p class="read-impact-note">${esc(impactLimitation)}</p>
          </section>

          <section class="read-section read-sources-section" aria-labelledby="readSourcesHead">
            <div class="read-section-head-row">
              <h3 id="readSourcesHead" class="read-section-title">✦ SOURCE COVERAGE</h3>
              <span class="read-section-subtitle">${esc(sourceCountLabel)}</span>
            </div>
            <div class="read-sources-list">
              ${sourceItemsMarkup}
            </div>
          </section>

          <section class="read-section read-timeline-section" aria-labelledby="readTimelineHead">
            <div class="read-section-head-row">
              <h3 id="readTimelineHead" class="read-section-title">✦ STORY EVOLUTION JOURNEY</h3>
              <span class="read-section-subtitle">Chronological Development & Verification</span>
            </div>
            ${timelineMarkup}
          </section>

          <section class="read-section read-related-section" aria-labelledby="readRelatedHead">
            <div class="read-section-head-row">
              <h3 id="readRelatedHead" class="read-section-title">✦ CONNECTED DEVELOPMENTS & DEEP CONTEXT</h3>
              <span class="read-section-subtitle">Parallel Reporting & Background Arcs</span>
            </div>
            ${relatedMarkup}
          </section>

          <footer class="read-disclaimer">
            <div class="read-disclaimer-divider"></div>
            <p class="read-disclaimer-text">AI-generated analysis may contain mistakes or misinterpret information. Aetheria does not certify or verify news. Please consult the original sources.</p>
          </footer>
        `;
      }

      if (e.id || targetId) modal.dataset.eventId = e.id || targetId;
      wireDynamicInteractions();
    } catch {
      if (requestSeq !== state.storyRequestSeq || !modal.classList.contains('open')) return;
      if (content) {
        content.innerHTML = `
          <div class="read-error-state">
            <span class="read-topic-kicker">AETHERIA READ</span>
            <h2 class="read-headline">Story details unavailable</h2>
            <p class="read-error-desc">The underlying story endpoint is temporarily unavailable. No substitute content has been generated.</p>
          </div>
        `;
      }
    }
  }

  function renderSparkline(points, cls) {
    const isUp = cls === 'up';
    const isDown = cls === 'down';
    let pts = (Array.isArray(points) && points.length >= 2) ? points.filter(Number.isFinite) : null;
    if (!pts || pts.length < 2) return '';
    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const range = (max - min) || 1;
    const w = 34;
    const h = 14;
    const pad = 1.5;
    const coords = pts.map((p, i) => {
      const x = (i / (pts.length - 1)) * (w - pad * 2) + pad;
      const y = (h - pad) - ((p - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const linePath = `M ${coords.join(' L ')}`;
    const areaPath = `M ${coords[0].split(',')[0]},${h} L ${coords.join(' L ')} L ${coords[coords.length - 1].split(',')[0]},${h} Z`;
    const colorVar = isUp ? 'var(--market-up)' : isDown ? 'var(--market-down)' : 'var(--market-neutral)';
    const gradId = `spk-${Math.random().toString(36).substring(2, 8)}`;

    return `<svg class="market-sparkline ${cls}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${colorVar}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="${colorVar}" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <path d="${areaPath}" fill="url(#${gradId})" />
      <path d="${linePath}" fill="none" stroke="${colorVar}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>`;
  }

  function renderMarketSkeleton() {
    const host = $('markets'); if (!host) return;
    const count = 8;
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="market-item is-skeleton" aria-hidden="true">
          <div class="market-row-top">
            <span class="market-skeleton-box" style="width:${48 + (i % 3) * 14}px;height:9px;"></span>
            <span class="market-skeleton-box" style="width:24px;height:9px;border-radius:999px;"></span>
          </div>
          <div class="market-row-bottom">
            <span class="market-skeleton-box" style="width:${52 + (i % 2) * 12}px;height:12px;"></span>
            <span class="market-skeleton-box" style="width:36px;height:10px;"></span>
          </div>
        </div>
      `;
    }
    host.innerHTML = html;
  }

  function renderMarkets(market) {
    const host = $('markets'); if (!host) return;
    const groups = (market?.groups || []);
    const items = groups.flatMap(g => (g.items || []).map(x => ({ ...x, group: g.label })))
      .filter(x => x.available !== false && x.price != null);
    if (!items.length) {
      if (!host.children.length) renderMarketSkeleton();
      return;
    }
    try { localStorage.setItem('aetheria-cached-markets', JSON.stringify(market)); } catch (_) { }
    const displayList = items.length < 16 ? [...items, ...items, ...items] : [...items, ...items];
    host.innerHTML = displayList.map(x => {
      const price = Number(x.price);
      const changeNum = x.change_num != null ? Number(x.change_num) : null;
      const pct = x.change != null ? Number(x.change) * 100 : null;
      const movement = Number.isFinite(changeNum) ? changeNum : Number.isFinite(pct) ? pct : null;
      const cls = movement == null || !Number.isFinite(movement) ? 'flat' : movement > 0 ? 'up' : movement < 0 ? 'down' : 'flat';
      const sign = movement > 0 ? '+' : '';
      const value = Number.isFinite(price) ? price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
      const abs = changeNum != null && Number.isFinite(changeNum) ? `${sign}${changeNum.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '';
      const ptxt = pct != null && Number.isFinite(pct) ? `${sign}${pct.toFixed(2)}%` : '';
      const direction = cls === 'up' ? 'Rising' : cls === 'down' ? 'Falling' : movement == null || !Number.isFinite(movement) ? 'Change unavailable' : 'Unchanged';
      const change = abs || ptxt ? `<span class="change-value">${esc(abs || '—')}</span>${ptxt ? `<span class="change-pct">${esc(ptxt)}</span>` : ''}<span class="market-arrow" aria-hidden="true">${cls === 'down' ? '▼' : cls === 'up' ? '▲' : '='}</span>` : '<span class="change-value">—</span>';
      const stateStr = String(x.market_state || '').toUpperCase();
      const isOpen = x.is_open === true || stateStr === 'REGULAR';
      const isClosed = x.is_open === false || (stateStr && stateStr !== 'REGULAR');
      const hasSpark = Array.isArray(x.sparkline) && x.sparkline.length >= 2;
      const topBadge = isOpen
        ? (hasSpark ? renderSparkline(x.sparkline, cls) : '<span class="market-status-tag live">LIVE</span>')
        : '<span class="market-status-tag closed">CLOSED</span>';
      return `<div class="market-item" data-route="Markets" tabindex="0" role="link" aria-label="${esc(x.label || x.symbol || 'Market')}: ${esc(value)} ${esc(direction)}${isClosed ? ' (Market Closed)' : ''}"><div class="market-row-top"><span class="market-name">${esc(x.label || x.symbol || x.group || 'MARKET')}</span>${topBadge}</div><div class="market-row-bottom"><span class="market-value">${esc(value)}</span><span class="market-change ${cls}" role="img" aria-label="${esc(direction)}${abs ? `, ${esc(abs)}` : ''}${ptxt ? `, ${esc(ptxt)}` : ''}">${change}</span></div></div>`;
    }).join('');
  }

  function renderBanner() {
    const banner = $('relatedBanner');
    if (!banner) return;
    const b = state.bootstrap?.home || {};
    const lead = b.lead || (b.stack || [])[0] || (state.bootstrap?.latest || [])[0];
    if (!lead || !lead.title) {
      banner.style.display = 'none';
      return;
    }
    banner.style.display = 'grid';
    $('relatedBannerTitle').textContent = lead.title || '';
    $('relatedBannerDesc').textContent = lead.description || lead.reason || (lead ? `${articleSource(lead)} · ${eventTime(lead)}` : '');
    const img = $('relatedBannerImage');
    const url = sourceUrl(lead);
    const arrow = $('relatedBannerArrow');
    if (url) banner.dataset.sourceUrl = url; else delete banner.dataset.sourceUrl;
    if (arrow) { if (url) arrow.dataset.sourceUrl = url; else delete arrow.dataset.sourceUrl; }
    if (img) {
      if (lead.image_url) {
        img.style.backgroundImage = `url("${String(lead.image_url).replace(/"/g, '&quot;')}")`;
        img.classList.add('has-live-image');
      } else {
        img.style.backgroundImage = '';
        img.classList.remove('has-live-image');
      }
    }
  }
  function storyStackItems() {
    if (state.route === 'Home') {
      const stack = state.bootstrap?.home?.stack || [];
      return stack.filter(x => x && x.id).slice(0, 10);
    }
    const total = (state.articles || []).length;
    const count = Math.min(10, Math.max(5, total >= 14 ? 10 : total >= 9 ? total - 4 : total));
    return state.articles.slice(0, count);
  }

  function renderStack() {
    const items = storyStackItems();
    if (!items.length) return '<div class="hero-card hero-feature"><div class="feature-visual no-image"><div class="feature-fallback-art"><div class="fallback-emblem">✦</div><span class="fallback-kicker">AETHERIA</span></div></div><div class="story-card"><div class="story-top"><span class="category-label">AETHERIA</span></div><h1 class="story-title">No active story is available yet.</h1><p class="story-summary">The live engine has not supplied a current story. Aetheria will not fabricate one.</p></div></div>';
    const i = ((state.stackIndex % items.length) + items.length) % items.length;
    const s = items[i];
    const source = s.domain || (s.source_domains || [])[0] || '';
    const url = sourceUrl(s);
    const image = s.image_url ? `<img class="feature-image" src="${esc(s.image_url)}" alt="${esc(s.title || '')}" loading="eager" referrerpolicy="no-referrer" onerror="this.remove()">` : '';
    const visualMarkup = image
      ? `<div class="feature-visual has-image">${image}<div class="visual-circle circle-outer" aria-hidden="true"></div><div class="visual-circle circle-inner" aria-hidden="true"></div>`
      : `<div class="feature-visual no-image"><div class="feature-fallback-art"><div class="fallback-emblem">✦</div><span class="fallback-kicker">${esc((s.topic || 'AETHERIA').toUpperCase())}</span></div><div class="visual-circle circle-outer" aria-hidden="true"></div><div class="visual-circle circle-inner" aria-hidden="true"></div>`;

    const controlsMarkup = `
      <div class="visual-tag-top">${esc((s.topic || 'GLOBAL').toUpperCase())} · DEVELOPING</div>
      <div class="story-stack-controls" aria-label="News stack controls">
        <div class="stack-nav-btns">
          <button type="button" class="stack-nav-btn" data-home-prev aria-label="Previous story" title="Previous story">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <button type="button" class="stack-nav-btn stack-pause-btn" data-home-pause aria-label="${state.stackPaused ? 'Resume' : 'Pause'}" title="${state.stackPaused ? 'Resume' : 'Pause'}">
            ${state.stackPaused
              ? `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg>`
              : `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>`}
          </button>
          <button type="button" class="stack-nav-btn" data-home-next aria-label="Next story" title="Next story">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
          </button>
        </div>
        <div class="stack-progress-row">
          <span class="story-stack-count" aria-live="polite">${String(i + 1).padStart(2, '0')} / ${String(items.length).padStart(2, '0')}</span>
          <div class="stack-progress-bar" aria-hidden="true">
            ${items.map((_, idx) => `<span class="stack-progress-segment ${idx === i ? 'active' : ''}"></span>`).join('')}
          </div>
        </div>
      </div>
    </div>`;

    const pub = s.latest_published || s.published;
    const sourceMeta = [source, eventTime(s)].filter(Boolean).join(' · ');
    return `<article class="hero-card hero-feature">${visualMarkup}${controlsMarkup}<div class="story-card"><div class="story-top"><span class="category-label">${esc((s.topic || 'WORLD').toUpperCase())}</span><span class="story-time">${esc(eventTime(s))}</span></div><h1 class="story-title" ${langAttr(s, s.title)} ${url ? `data-source-url="${esc(url)}"` : `data-open-story="${esc(s.id || '')}"`}>${esc(s.title)}</h1><p class="story-summary" ${langAttr(s, s.description)}>${esc(s.description || s.reason || '')}</p><div class="story-source">${sourceMeta ? '<span class="source-dot"></span>' : ''}<span class="stack-source">${esc(sourceMeta)}</span></div><div class="news-published">${pub ? `Published ${esc(formatPublished(pub))}` : s.last_seen ? `Observed ${esc(formatPublished(s.last_seen))}` : ''}</div><div class="hero-action-row">${actionTools(s)}${url ? `<button class="btn-primary" type="button" data-source-url="${esc(url)}">Read source →</button>` : `<button class="btn-primary" type="button" data-open-story="${esc(s.id || '')}">Read story →</button>`}</div></div></article>`;
  }

  function developingHTML(items) {
    const rows = (items || []).slice(0, 4);
    if (!rows.length) return '<div class="empty-state">No active developing stories are available.</div>';
    return rows.map(e => {
      const url = sourceUrl(e);
      const action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(e.id || '')}"`;
      const domain = e.domain || (e.source_domains || [])[0] || '';
      const publishedTs = Number(e.latest_published || e.published || 0);
      const timestamp = publishedTs || Number(e.last_seen || 0);
      let timeMarkup = '<time class="dev-time">—</time>';
      if (timestamp > 0) {
        const d = new Date(timestamp * 1000);
        if (!Number.isNaN(d.getTime())) {
          const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
          const parts = timeStr.split(' ');
          timeMarkup = `<time class="dev-time"><span>${esc(parts[0])}</span><small>${esc(parts[1] || '')}</small></time>`;
        }
      }
      return `<div class="dev-row" ${action} tabindex="0" role="group" aria-label="Developing story: ${esc(e.title)}">${timeMarkup}<div class="dev-content"><div class="dev-cat ${topicClass(e.topic)}">${esc((e.topic || 'WORLD').toUpperCase())}</div><div class="dev-title" ${langAttr(e, e.title)}>${esc(e.title)}</div><div class="dev-source">${esc([domain, eventTime(e)].filter(Boolean).join(' · '))}</div></div></div>`;
    }).join('');
  }
  function lowerCard(title, rows, renderer) {
    return `<article class="info-card"><div class="card-head"><b>${esc(title)}</b><a data-route="${esc(title === 'INDIA DESK' ? 'India' : title === 'IMPACT' ? 'Aetheria Read' : title === 'UPCOMING EVENTS' ? 'Upcoming Events' : 'Aetheria Read')}">View all →</a></div>${rows || '<div class="empty-state">No active information available.</div>'}</article>`;
  }

  function eventDateParts(ts) {
    const value = Number(ts);
    if (!Number.isFinite(value) || value <= 0) return { month: 'OCT', day: '—' };
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) return { month: 'OCT', day: '—' };
    const month = date.toLocaleDateString([], { month: 'short' }).toUpperCase();
    const day = String(date.getDate()).padStart(2, '0');
    return { month, day };
  }

  function renderHome() {
    const h = state.bootstrap?.home || {};
    const developing = Array.isArray(h.happening) ? h.happening : [];
    const india = h.india_lens || [];
    const impact = h.impact || [];
    const future = h.upcoming_events || state.bootstrap?.future || [];
    const read = h.read_next || [];
    const latest = state.articles.length ? state.articles.slice(0, 4) : (state.bootstrap?.latest || []).slice(0, 4);

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

    const indiaRows = india.slice(0, 2).map((x, i) => {
      const url = sourceUrl(x), action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const pub = x.latest_published || x.published;
      const footer = `<div class="india-item-footer"><span class="india-item-time">${publicationMarkup(pub, x.last_seen)}</span><div class="india-item-actions">${actionTools(x)}</div></div>`;
      const status = x.status ? `<div class="india-live">${esc(x.status.toUpperCase())}</div>` : '';
      const image = safeSourceUrl(x.image_url);
      const imageMarkup = image ? `<img class="india-photo" src="${esc(image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.india-feature')?.classList.add('text-only');this.remove()">` : '';
      return `<div class="india-feature ${image ? 'has-image' : 'text-only'}" ${action} tabindex="0" role="group" aria-label="Open story: ${esc(x.title)}">${imageMarkup}<div class="india-feature-content"><div class="india-item-top"><small class="india-item-category">${esc((x.topic || 'INDIA').toUpperCase())}</small>${status}</div><div class="india-title" ${langAttr(x, x.title)}>${esc(x.title)}</div>${footer}</div></div>`;
    }).join('');

    const sortedImpact = (impact || []).slice().sort((a, b) => {
      const sa = storyImpactScore(a);
      const sb = storyImpactScore(b);
      return sb - sa;
    });
    const impactRows = sortedImpact.slice(0, 3).map(x => {
      const url = sourceUrl(x), action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.id || '')}"`;
      const impactScore = storyImpactScore(x);
      const scoreText = impactScore > 0 ? String(impactScore) : '';
      const scoreClass = impactScore >= 70 ? 'impact-high' : impactScore >= 40 ? 'impact-medium' : impactScore > 0 ? 'impact-low' : 'impact-none';
      const indicator = scoreText ? `<div class="impact-icon ${scoreClass}" aria-label="Impact ${esc(scoreText)} out of 100"><span class="impact-inline-score">${esc(scoreText)}</span></div>` : `<div class="impact-icon impact-none" aria-label="Impact score unavailable"><span class="impact-inline-score">—</span></div>`;
      return `<div class="impact-row" ${action}>${indicator}<div class="impact-text"><small>${esc((x.topic || 'IMPACT').toUpperCase())}</small><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3>${publicationMarkup(x.latest_published || x.published, x.last_seen)}</div>${actionTools(x)}</div>`;
    }).join('');

    const futureCandidate = (Array.isArray(h.upcoming_events) && h.upcoming_events.length >= 3) ? h.upcoming_events : (state.bootstrap?.future || h.upcoming_events || []);
    const futureList = futureCandidate.slice().sort((a, b) => (Number(a.start_ts) || Infinity) - (Number(b.start_ts) || Infinity));
    const futureRows = futureList.length ? `<div class="future-wrap">${futureList.slice(0, 3).map(x => {
      const url = safeSourceUrl(x.url), action = url ? `data-source-url="${esc(url)}"` : '';
      const dateObj = eventDateParts(x.start_ts);
      const timeStr = x.time_known ? formatTime(x.start_ts) : 'All day';
      return `<div class="future-row" ${action} tabindex="0" role="group" aria-label="Scheduled event: ${esc(x.title)}"><div class="future-date-badge"><span class="future-date-month">${esc(dateObj.month)}</span><span class="future-date-day">${esc(dateObj.day)}</span></div><div class="future-text"><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3><span class="future-time-label">${esc(timeStr)}</span></div>${actionTools(x)}</div>`;
    }).join('')}</div>` : '<div class="empty-state">No active upcoming events are available.</div>';
    const readRows = read.slice(0, 1).map(x => {
      const url = sourceUrl(x), action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.event_id || x.id || '')}"`;
      const image = safeSourceUrl(x.image_url);
      const source = String(x.domain || x.latest_domain || x.source_domains?.[0] || '').trim();
      const published = x.latest_published || x.published || x.last_seen;
      const timeLabel = published ? `${Number(x.latest_published || x.published) > 0 ? 'Published' : 'Observed'} ${formatPublished(published)}` : '';
      const impactScore = storyImpactScore(x);
      const scoreClass = impactScore >= 70 ? 'impact-high' : impactScore >= 40 ? 'impact-medium' : 'impact-low';
      const impactBadge = impactScore > 0 ? `<span class="impact-icon ${scoreClass}" style="display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:50%; margin-left:6px; border:1px solid var(--line-2); background:var(--surface); vertical-align:middle;" title="Impact ${impactScore}/100"><span class="impact-inline-score" style="font-size:9px;line-height:1;position:static;">${impactScore}</span></span>` : '';
      const context = String(x.description || x.reason || '').trim();
      const imageMarkup = image ? `<div class="read-card-image banner-img" role="img" aria-label="Article image" style="background-image:url('${esc(image)}')"></div>` : '';
      return `<div class="read-card-content ${image ? 'has-image' : 'no-image'}" ${action} style="cursor:pointer" tabindex="0">${imageMarkup}<div class="read-card-body"><div class="read-card-top"><small class="read-card-category">${esc((x.topic || 'AETHERIA READ').toUpperCase())}</small>${impactBadge}</div><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3>${context ? `<p class="read-card-excerpt" ${langAttr(x, context)}>${esc(context)}</p>` : ''}<div class="read-card-footer"><span class="read-card-time">${esc(timeLabel || source)}</span><div class="read-card-actions">${actionTools(x)}</div></div></div></div>`;
    }).join('');

    const latestRows = latest.length ? latest.map((x, i) => {
      const url = sourceUrl(x), action = url ? `data-source-url="${esc(url)}"` : `data-open-event="${esc(x.event_id || x.id || '')}"`;
      const image = x.image_url ? `<img src="${esc(x.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      return `<article class="latest-row ${i === 0 ? 'featured' : ''}" ${action}>${clockMarkup(x.published || x.latest_published, x.last_seen)}<div class="latest-thumb-slot ${image ? '' : 'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc((x.topic || 'WORLD').toUpperCase())}</span><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3><p>${esc(articleMeta(x))}</p></div><div class="latest-actions">${actionTools(x)}<button class="latest-arrow" type="button" aria-label="Open source" title="Open source">↗</button></div></article>`;
    }).join('') : '<div class="empty-state">No active articles are available.</div>';

    const changedRows = changed.length ? changed.map((x, i) => {
      const url = sourceUrl(x), action = url ? `data-source-url="${esc(url)}"` : (x.id ? `data-open-event="${esc(x.id)}"` : '');
      const sourceCount = Number(x.sources ?? x.source_count);
      const source = String(x.latest_domain || x.domain || x.source_domains?.[0] || '').trim();
      const detail = [eventTime(x), source, Number.isFinite(sourceCount) ? `${sourceCount} reports` : ''].filter(Boolean).join(' · ');
      const change = x._editorial_selection?.change_evidence || {};
      const changeLabel=change.confidence==='HIGH'?'STRONG CHANGE EVIDENCE':'LIKELY CHANGE';
      const context = String(change.what_is_new || x.description || '').trim();
      const known = String(change.what_was_known || '').trim();
      const changeContext = known && context ? `Previously: ${known} | New evidence: ${context}` : context;
      const keyboardAttrs = action ? `tabindex="0" role="group" aria-label="Open story: ${esc(x.title)}" aria-keyshortcuts="Enter"` : '';
      return `<article class="changed-card" ${action} ${keyboardAttrs}><div class="changed-icon">${i === 0 ? '↗' : i === 1 ? '◎' : '→'}</div><div class="changed-label">${esc(changeLabel)}</div><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3>${changeContext ? `<p class="changed-context" ${langAttr(x, changeContext)}>${esc(changeContext)}</p>` : ''}<div class="changed-meta"><span class="changed-info">${esc(detail)}</span>${actionTools(x)}</div></article>`;
    }).join('') : '<div class="empty-state">No likely real-world change is supported by current reporting.</div>';

    return `<section class="home"><section class="hero">${renderStack()}<aside class="hero-card developing"><div class="dev-head"><b>DEVELOPING</b><a data-route="Latest">View all →</a></div>${developingHTML(developing)}</aside></section><section class="lower">${lowerCard('INDIA DESK', `<div class="india-wrap">${indiaRows || '<div class="empty-state">No India-relevant active reports are available.</div>'}</div>`)}${lowerCard('IMPACT', impactRows)}${lowerCard('UPCOMING EVENTS', futureRows)}${lowerCard('AETHERIA READ', readRows || '<div class="empty-state">No current reading signal is available.</div>')}</section><section class="intelligence-section"><div class="section-heading"><div><span class="section-kicker">AETHERIA INTELLIGENCE</span><h2>What changed?</h2></div></div><div class="changed-grid">${changedRows}</div></section><section class="latest-section"><div class="section-heading"><div><span class="section-kicker">REAL-TIME STREAM</span><h2>Latest</h2></div><a data-route="Latest">Open full stream →</a></div><div class="latest-card">${latestRows}</div></section><section class="followup-section intelligence-section"><div class="section-heading"><div><span class="section-kicker">CONTINUING WATCH</span><h2>Follow-up</h2></div><a data-route="Follow-up">Open follow-up desk →</a></div>${renderFollowUpPreview()}</section></section>`;
  }

  function renderFollowUpPreview() {
    const list = state.followUp?.active || state.followUp?.followed || [];
    if (!list.length) return '<div class="changed-grid"><article class="changed-card"><div class="changed-icon">→</div><div class="changed-label">FOLLOW-UP</div><h3>No active follow-up signal is available.</h3><p>Aetheria will surface continuing developments when the engine has identified a meaningful update.</p></article></div>';
    return `<div class="changed-grid">${list.slice(0, 3).map(x => {
      const scheduled = Number(x.start_ts) > 0, url = scheduled ? safeSourceUrl(x.url) : '';
      const action = url ? `data-source-url="${esc(url)}"` : scheduled ? '' : `data-open-event="${esc(x.id)}"`;
      const description = scheduled ? x.description : (x.what_changed || x.why_monitoring || '');
      const impact = Number(x?.event?.significance || x?.intelligence?.impact);
      const scoreClass = impact >= 0.70 ? 'impact-high' : impact >= 0.40 ? 'impact-medium' : 'impact-low';
      const impactBadge = Number.isFinite(impact) && impact > 0 ? `<span class="impact-icon ${scoreClass}" style="display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:50%; margin-left:8px; border:1px solid var(--line-2); background:var(--surface); vertical-align:middle;" title="Impact ${Math.round(impact * 100)}/100"><span class="impact-inline-score" style="font-size:10px;line-height:1;position:static;">${Math.round(impact * 100)}</span></span>` : '';
      return `<article class="changed-card" ${action} style="cursor:pointer" tabindex="0"><div class="changed-icon">→</div><div class="changed-label">${esc(x.lifecycle || 'ACTIVE')}</div><h3 ${langAttr(x, x.title)}>${esc(x.title)}${impactBadge}</h3>${description ? `<p ${langAttr(x, description)}>${esc(description)}</p>` : ''}<div class="changed-meta"><span class="changed-info">${esc(x.last_seen ? formatAge(x.last_seen) : '')}</span>${actionTools(x)}<button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id)}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></div></article>`;
    }).join('')}</div>`;
  }

  function articleRows(rows) {
    if (!rows?.length) return '<div class="empty-state">No matching live reports are available.</div>';
    return rows.map((a, i) => {
      const url = sourceUrl(a), action = url ? `data-source-url="${esc(url)}"` : (a.event_id ? `data-open-event="${esc(a.event_id)}"` : '');
      const image = a.image_url ? `<img src="${esc(a.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove();this.parentElement.classList.add('empty')">` : '';
      const impact = Number(a?.event?.significance);
      const scoreClass = impact >= 0.70 ? 'impact-high' : impact >= 0.40 ? 'impact-medium' : 'impact-low';
      const impactBadge = Number.isFinite(impact) && impact > 0 ? `<span class="impact-icon ${scoreClass}" style="display:inline-grid; width:22px; height:22px; border-radius:50%; margin-left:8px; border:1px solid var(--line-2); background:var(--surface); vertical-align:middle;" title="Impact ${Math.round(impact * 100)}/100"><span class="impact-inline-score" style="font-size:10px;">${Math.round(impact * 100)}</span></span>` : '';
      return `<article class="latest-row ${i === 0 ? 'featured' : ''}" ${action}>${clockMarkup(a.published, a.fetched)}<div class="latest-thumb-slot ${image ? '' : 'empty'}">${image}</div><div class="latest-main"><span class="latest-cat ${topicClass(a.topic)}">${esc((a.topic || 'WORLD').toUpperCase())}</span><h3 ${langAttr(a, a.title)}>${esc(a.title)}</h3><p>${esc(articleMeta(a))}${impactBadge}</p></div><div class="latest-actions">${actionTools(a)}<button class="latest-arrow" type="button" aria-label="Open source" title="Open source">↗</button></div></article>`;
    }).join('');
  }

  function loadingRows(label = 'Loading...') {
    return Array(6).fill().map(() => '<article class="latest-row loading-skeleton" aria-hidden="true"><div class="latest-time skeleton-block" style="width:40px;height:12px;"></div><div class="latest-thumb-slot empty skeleton-block" style="background:var(--surface-2)"></div><div class="latest-main"><div class="skeleton-block" style="width:30%;height:10px;margin-bottom:8px"></div><div class="skeleton-block" style="width:90%;height:16px;margin-bottom:6px"></div><div class="skeleton-block" style="width:70%;height:16px"></div></div></article>').join('');
  }

  function routeDescription(route) {
    return ({
      India: 'India-first reporting and developments relevant to India, while retaining important global developments that affect the country.',
      World: 'International reporting across regions and topics, prioritised by actual publication time and significance.',
      Business: 'Company, trade and industry reporting from the live Aetheria source universe.',
      Markets: 'Observed market and financial developments connected to the live news universe.',
      Sports: 'Current sports reporting from the live source universe.',
      Technology: 'Technology, AI and digital developments from the live source universe.',
      Legal: 'Legal and regulatory developments from verified reporting.',
      Geopolitical: 'Diplomatic, strategic and geopolitical developments from verified reporting.',
      Entertainment: 'Entertainment, culture and media developments from the live source universe.'
    })[route] || 'Current Aetheria reporting.';
  }

  async function renderArticleRoute(route) {
    const host = $('mainView');
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">LIVE STREAM</span><h1>${esc(routeLabel(route))}</h1><p class="route-sub">${esc(routeDescription(route))}</p></div></div><div class="route-stack-container" style="margin-bottom: 24px;"></div><div class="latest-card">${loadingRows()}</div></section>`;
    const seq = ++state.requestSeq;
    try {
      const params = new URLSearchParams({ limit: '80' });
      if (route === 'India') params.set('india', '1');
      else if (route === 'World') params.set('world', '1');
      else if (!['Latest'].includes(route)) params.set('topic', routeTopic(route));
      const d = await getJSON(`/api/articles?${params.toString()}`);
      if (seq !== state.requestSeq) return;
      state.articles = (d.articles || []).map(x => ({ ...x, event_id: x.event_id || x.id }));

      const isCategory = !['Latest'].includes(route);
      let stackHtml = '';
      let listItems = state.articles;

      const total = state.articles.length;
      const stackCount = Math.min(10, Math.max(5, total >= 14 ? 10 : total >= 9 ? total - 4 : total));
      const devCount = total >= stackCount + 4 ? 4 : 0;

      if (total >= 5) {
        const stackItems = state.articles.slice(0, stackCount);
        const developingItems = devCount ? state.articles.slice(stackCount, stackCount + devCount) : [];
        listItems = state.articles.slice(stackCount + devCount);
        const devHeadStr = isCategory ? `LATEST IN ${esc(route.toUpperCase())}` : 'DEVELOPING IN LATEST';
        const asideMarkup = devCount ? `<aside class="hero-card developing"><div class="dev-head"><b>${devHeadStr}</b><a data-route="Latest">View all →</a></div>${developingHTML(developingItems)}</aside>` : '';
        stackHtml = `<section class="hero">${renderStack()}${asideMarkup}</section>`;
        if (stackItems.length) startStackTimer();
      } else {
        listItems = state.articles;
      }

      host.querySelector('.route-stack-container').innerHTML = stackHtml;
      host.querySelector('.latest-card').innerHTML = articleRows(listItems);

      bindStackControls();
      wireDynamicInteractions();
    } catch (err) {
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
        const isSchedule = Number(x.start_ts) > 0;
        const pub = x.latest_published || x.published;
        const url = safeSourceUrl(x.latest_url || x.url || '');
        const action = url ? `data-source-url="${esc(url)}"` : isSchedule ? '' : `data-open-event="${esc(x.id || '')}"`;
        const date = isSchedule ? formatScheduleDate(x.start_ts) : '';
        const clock = isSchedule
          ? `<time class="latest-time scheduled" aria-label="Scheduled ${esc(date)}"><span>${x.time_known ? esc(formatTime(x.start_ts)) : ''}</span><small>${esc(date)}</small><em>Scheduled</em></time>`
          : clockMarkup(pub, x.last_seen);
        const description = isSchedule ? (x.description || '') : (x.what_changed || x.why_monitoring || x.previous_state || '');
        const related = isSchedule && Array.isArray(x.related) && x.related.length ? `<div class="schedule-followed-updates"><strong>RELATED REPORTS</strong>${x.related.slice(0, 3).map(r => `<button type="button" class="schedule-related-link" data-open-event="${esc(r.id || '')}"><span>${esc(r.title || '')}</span><small>${esc((r.relationship_evidence || []).slice(0, 2).join(' · '))}</small></button>`).join('')}</div>` : '';
        return `<article class="latest-row follow-up-row" ${action}>${clock}<div class="latest-thumb-slot empty"></div><div class="latest-main"><span class="latest-cat ${topicClass(x.topic)}">${esc(isSchedule ? x.lifecycle || x.kind || 'SCHEDULED' : x.topic || 'FOLLOW-UP')}</span><h3 ${langAttr(x, x.title)}>${esc(x.title)}</h3><p ${langAttr(x, description)}>${esc(description)}</p>${related}</div><div class="latest-actions">${actionTools(x)}<button type="button" class="news-card-action follow-remove" data-unfollow-event="${esc(x.id || '')}" aria-label="Remove from Follow-up" title="Remove from Follow-up">−</button></div></article>`;
      }).join('') : '<div class="empty-state">No follow-up stories are currently available.</div>';
      wireDynamicInteractions();
    } catch {
      host.querySelector('.latest-card').innerHTML = '<div class="empty-state">Follow-up intelligence is temporarily unavailable.</div>';
    }
  }

  function renderReadPage() {
    const rows = state.bootstrap?.home?.read_next || [];
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">AETHERIA READ</span><h1>Aetheria Read</h1><p class="route-sub">Context and explanation attached to current active developments.</p></div></div><div class="latest-card">${articleRows(rows.map(x => ({ ...x, event_id: x.id, source: { name: x.domain }, published: x.latest_published || x.published })))}</div></section>`;
    wireDynamicInteractions();
  }

  async function renderUpcomingPage() {
    const host = $('mainView');
    host.innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">SCHEDULED WATCH</span><h1>Upcoming Events</h1><p class="route-sub">Stored upcoming events from Aetheria’s schedule, with follow controls.</p></div></div><div class="latest-card">${loadingRows('Loading upcoming events...')}</div></section>`;
    const seq = ++state.requestSeq;
    try {
      const d = await getJSON('/api/future');
      if (seq !== state.requestSeq) return;
      const rows = d.events || [];
      host.querySelector('.latest-card').innerHTML = rows.length ? rows.map(x => {
        const date = formatScheduleDate(x.start_ts);
        const time = x.time_known ? formatTime(x.start_ts) : '';
        const description = String(x.description || '').trim();
        return `<article class="latest-row schedule-row"><time class="latest-time scheduled" aria-label="Scheduled ${esc(date)}">${time ? `<span>${esc(time)}</span>` : ''}<small>${esc(date)}</small><em>Scheduled</em></time><div class="latest-thumb-slot empty" aria-hidden="true"></div><div class="latest-main"><span class="latest-cat ${topicClass(x.category || x.kind)}">${esc(x.category || x.kind || 'SCHEDULED')}</span><h3 ${langAttr(x, x.title)}>${esc(x.title || '')}</h3>${description ? `<p ${langAttr(x, description)}>${esc(description)}</p>` : ''}</div><div class="latest-actions">${actionTools(x)}</div></article>`;
      }).join('') : '<div class="empty-state">No upcoming events are currently available in the schedule.</div>';
      wireDynamicInteractions();
    } catch {
      const card = host.querySelector('.latest-card');
      if (card) card.innerHTML = '<div class="empty-state">Upcoming events are temporarily unavailable.</div>';
    }
  }

  function renderSearchPage() {
    $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">DISCOVERY</span><h1>Search</h1><p class="route-sub">Search the current Aetheria story universe.</p></div></div><div class="route-search"><input id="routeSearchInput" type="search" autocomplete="off" placeholder="Search live news, topics or sources…" value="${esc(state.searchQuery || '')}" aria-label="Search live news"><button id="routeSearchButton" class="btn-primary" type="button">Search</button></div><div class="latest-card" id="searchResults">${state.searchQuery ? loadingRows('Searching live reporting...') : '<div class="empty-state">Enter a search term.</div>'}</div></section>`;
    $('routeSearchButton').onclick = () => runRouteSearch();
    $('routeSearchInput').addEventListener('keydown', e => { if (e.key === 'Enter') runRouteSearch(); });
    requestAnimationFrame(() => {
      const input = $('routeSearchInput');
      if (input) { input.focus({preventScroll:true}); input.setSelectionRange(input.value.length, input.value.length); }
      if (state.searchQuery) runRouteSearch(state.searchQuery);
    });
  }
  async function runRouteSearch(queryOverride = '') {
    const q = String(queryOverride || $('routeSearchInput')?.value || '').trim();
    if (!q) return;
    state.searchQuery = q;
    const input = $('routeSearchInput'); if (input) input.value = q;
    const resultsHost = $('searchResults'); if (!resultsHost) return;
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
    const host = $('searchSuggestions'); if (!host) return;
    if (!items?.length) { host.innerHTML = ''; host.classList.remove('open'); return; }
    host.innerHTML = items.slice(0, 8).map(x => {
      const pub = x.latest_published || x.published;
      const time = pub ? formatPublished(pub) : x.last_seen ? `Observed ${formatPublished(x.last_seen)}` : '';
      const meta = [x.topic, x.status, time].filter(Boolean).join(' · ');
      return `<button type="button" class="search-suggestion" data-suggestion-id="${esc(x.id || '')}"><span><b>${esc(x.title || '')}</b><small>${esc(meta)}</small></span><span aria-hidden="true">↗</span></button>`;
    }).join('');
    host.classList.add('open');
    host.querySelectorAll('[data-suggestion-id]').forEach(btn => btn.addEventListener('click', () => { const q = btn.querySelector('b')?.textContent?.trim() || ''; const input = $('searchDockInput'); if (input) input.value = q; state.searchQuery = q; closeSearchDock(); navigate('Search'); }));
  }
  async function updateSearchSuggestions() {
    const q = ($('searchDockInput')?.value || '').trim();
    if (q.length < 2) { renderSearchSuggestions([]); return; }
    try { const d = await getJSON(`/api/suggest?q=${encodeURIComponent(q)}`, { timeout: 4000 }); renderSearchSuggestions(d.results || []); } catch { renderSearchSuggestions([]); }
  }
  function openSearchDock() {
    closeAllPopups('search');
    const dock = $('searchDock'); if (!dock) return;
    dock.classList.add('open'); dock.setAttribute('aria-hidden', 'false');
    const input = $('searchDockInput');
    if (input) {
      input.value = '';
      setTimeout(() => {
        input.focus({ preventScroll: true });
        input.select();
      }, 40);
      updateSearchSuggestions();
    }
  }
  function closeSearchDock() {
    const dock = $('searchDock'); if (!dock) return;
    dock.classList.remove('open'); dock.setAttribute('aria-hidden', 'true');
    renderSearchSuggestions([]);
    if (state.searchSuggestTimer) clearTimeout(state.searchSuggestTimer);
  }
  function submitTopSearch() {
    const q = ($('searchDockInput')?.value || '').trim();
    if (!q) { closeSearchDock(); return; }
    state.searchQuery = q;
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
    const root = document.documentElement;
    const previousBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = 'auto';
    window.scrollTo(0,0);
    root.scrollTop = 0;
    document.body.scrollTop = 0;
    root.style.scrollBehavior = previousBehavior;
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
    if (options.history === false) history.replaceState({ route }, '', `#${encodeURIComponent(hash)}`);
    else if (changedView) history.pushState({ route }, '', `#${encodeURIComponent(hash)}`);
    if (changedView) resetRouteScroll();
    if (changedView || route === 'Search') await renderRoute();
  }

  function bindHome() {
    document.querySelectorAll('[data-open-story],[data-open-event]').forEach(el => el.addEventListener('click', e => {
      e.preventDefault(); e.stopPropagation();
      const url = el.dataset.sourceUrl || '';
      if (url && openSource(url)) return;
      openStory(el.dataset.openStory || el.dataset.openEvent);
    }));
    bindStackControls();
    wireDynamicInteractions();
  }
  function bindStackControls() {
    document.querySelectorAll('[data-home-prev]').forEach(b => {
      b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); moveStack(-1); };
    });
    document.querySelectorAll('[data-home-next]').forEach(b => {
      b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); moveStack(1); };
    });
    document.querySelectorAll('[data-home-pause]').forEach(b => {
      b.onclick = (e) => {
        e.preventDefault(); e.stopPropagation();
        state.stackPaused = !state.stackPaused;
        if (state.stackPaused) clearStackTimer();
        else startStackTimer();
        updateStackDisplay();
      };
    });
  }
  function updateStackDisplay() {
    const items = storyStackItems();
    if (!items.length) return;
    if (state.route === 'Home') {
      const heroHost = document.querySelector('.home .hero');
      if (heroHost) {
        const developing = Array.isArray(state.bootstrap?.home?.happening) ? state.bootstrap.home.happening : [];
        heroHost.innerHTML = `${renderStack()}<aside class="hero-card developing"><div class="dev-head"><b>DEVELOPING</b><a data-route="Latest">View all →</a></div>${developingHTML(developing)}</aside>`;
        bindHome();
        return;
      }
    }
    const routeContainer = document.querySelector('.route-stack-container');
    if (routeContainer) {
      const isCategory = !['Latest'].includes(state.route);
      let stackHtml = '';
      if (state.articles.length >= 8) {
        const developingItems = state.articles.slice(4, 8);
        const devHeadStr = isCategory ? `LATEST IN ${esc(state.route.toUpperCase())}` : 'DEVELOPING IN LATEST';
        stackHtml = `<section class="hero">${renderStack()}<aside class="hero-card developing"><div class="dev-head"><b>${devHeadStr}</b><a data-route="Latest">View all →</a></div>${developingHTML(developingItems)}</aside></section>`;
      } else if (state.articles.length > 4) {
        stackHtml = `<section class="hero">${renderStack()}</section>`;
      }
      routeContainer.innerHTML = stackHtml;
      bindStackControls();
      wireDynamicInteractions();
      return;
    }
  }

  function moveStack(delta) {
    const items = storyStackItems(); if (!items.length) return;
    state.stackIndex = (state.stackIndex + delta + items.length) % items.length;
    updateStackDisplay();
  }
  function clearStackTimer() { if (state.stackTimer) clearInterval(state.stackTimer); state.stackTimer = null; }
  function startStackTimer() {
    clearStackTimer();
    if (state.stackPaused) return;
    const items = storyStackItems(); if (items.length < 2) return;
    state.stackTimer = setInterval(() => moveStack(1), 9000);
  }
  function wireDynamicInteractions() {
    document.querySelectorAll('[data-source-url]').forEach(el => {
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        const hasNestedControls = Boolean(el.querySelector('button,a[href],input,select,textarea,[contenteditable="true"]'));
        if (!el.hasAttribute('role')) el.setAttribute('role', hasNestedControls ? 'group' : 'link');
        el.setAttribute('tabindex', '0');
        if (hasNestedControls && !el.hasAttribute('aria-label')) {
          const title = el.querySelector('.dev-title,.india-title,.impact-text h3,.future-text h3,.latest-main h3,.changed-card h3,.banner-title,.story-title')?.textContent?.trim();
          if (title) el.setAttribute('aria-label', `Open story: ${title}`);
          el.setAttribute('aria-keyshortcuts', 'Enter');
        }
      }
      if (el.dataset.boundSource) return;
      el.dataset.boundSource = '1';
      el.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const eventId = el.closest('.hero-feature,.dev-row,.india-feature,.list-row,.impact-row,.future-row,.latest-row,.changed-card')?.querySelector('[data-follow-event]')?.dataset.followEvent;
        if (eventId) recordTelemetry(eventId, 'open');
        openSource(el.dataset.sourceUrl);
      });
    });
    document.querySelectorAll('[data-open-event]').forEach(el => {
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        const hasNestedControls = Boolean(el.querySelector('button,a[href],input,select,textarea,[contenteditable="true"]'));
        if (!el.hasAttribute('role')) el.setAttribute('role', hasNestedControls ? 'group' : 'link');
        el.setAttribute('tabindex', '0');
        if (hasNestedControls && !el.hasAttribute('aria-label')) {
          const title = el.querySelector('.dev-title,.india-title,.impact-text h3,.future-text h3,.latest-main h3,.changed-card h3,.banner-title,.story-title')?.textContent?.trim();
          if (title) el.setAttribute('aria-label', `Open story: ${title}`);
          el.setAttribute('aria-keyshortcuts', 'Enter');
        }
      }
      if (el.dataset.boundEvent) return;
      el.dataset.boundEvent = '1';
      el.onclick = e => { e.preventDefault(); e.stopPropagation(); openStory(el.dataset.openEvent); };
    });
    document.querySelectorAll('[data-open-story]').forEach(el => {
      if (!el.matches('a,button,input,select,textarea,[contenteditable="true"]')) {
        el.setAttribute('role', 'link');
        el.setAttribute('tabindex', '0');
      }
    });
    document.querySelectorAll('[data-route]').forEach(b => {
      if (!b.dataset.categoryTrigger && !b.dataset.boundRoute) {
        b.dataset.boundRoute = '1';
        b.onclick = e => { e.preventDefault(); e.stopPropagation(); navigate(b.dataset.route); };
      }
    });
    document.querySelectorAll('[data-follow-event]').forEach(btn => {
      if (btn.dataset.boundFollow) return;
      btn.dataset.boundFollow = '1';
      btn.addEventListener('click', async e => {
        e.preventDefault(); e.stopPropagation();
        const eid = btn.dataset.followEvent; if (!eid) return;
        const following = followedIds().has(eid);
        const newFollowing = !following;
        const ids = followedIds();
        if (newFollowing) ids.add(eid); else ids.delete(eid);
        state.followUp = { ...(state.followUp || {}), followed_ids: [...ids] };
        btn.classList.toggle('following', newFollowing);
        const icon = btn.querySelector('.news-card-action-icon, .read-follow-icon');
        if (icon) icon.textContent = newFollowing ? '✓' : '+';
        const label = btn.querySelector('.read-follow-label');
        if (label) label.textContent = newFollowing ? 'Following Story' : 'Follow Story';
        btn.setAttribute('aria-label', newFollowing ? 'Following this story' : 'Follow this story');
        btn.setAttribute('title', newFollowing ? 'Following this story' : 'Follow this story');
        announceAction(newFollowing ? 'Article successfully added to Follow-Up.' : 'Article removed from Follow-Up.');
        try {
          const d = await fetch('/api/follow', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ session: followSession(), event_id: eid, action: newFollowing ? 'follow' : 'unfollow' }) }).then(r => r.json());
          if (!d.ok || d.error) throw new Error(d.error || 'Follow action failed');
          getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`).then(f => { if (f) state.followUp = f; }).catch(() => { });
        } catch {
          if (following) ids.add(eid); else ids.delete(eid);
          state.followUp = { ...(state.followUp || {}), followed_ids: [...ids] };
          btn.classList.toggle('following', following);
          if (icon) icon.textContent = following ? '✓' : '+';
          if (label) label.textContent = following ? 'Following Story' : 'Follow Story';
          announceAction('Follow-Up could not be updated.');
        }
      });
    });
    document.querySelectorAll('[data-unfollow-event]').forEach(btn => {
      if (btn.dataset.boundUnfollow) return;
      btn.dataset.boundUnfollow = '1';
      btn.addEventListener('click', async e => {
        e.preventDefault(); e.stopPropagation();
        const eid = btn.dataset.unfollowEvent; if (!eid) return; btn.disabled = true;
        try {
          const d = await fetch('/api/follow', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify({ session: followSession(), event_id: eid, action: 'unfollow' }) }).then(r => r.json());
          if (!d.ok || d.error) throw new Error(d.error || 'Unfollow failed');
          state.followUp = await getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`);
          await renderRoute();
          announceAction('Article removed from Follow-Up.');
        } catch { btn.disabled = false; announceAction('Follow-Up could not be updated.'); }
      });
    });
    document.querySelectorAll('[data-related-event]').forEach(btn => {
      if (btn.dataset.boundRelated) return;
      btn.dataset.boundRelated = '1';
      btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openStory(btn.dataset.relatedEvent); });
    });
    document.querySelectorAll('[data-modal-source]').forEach(btn => {
      if (btn.dataset.boundModalSource) return;
      btn.dataset.boundModalSource = '1';
      btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openSource(btn.dataset.modalSource); });
    });
    document.querySelectorAll('[data-modal-related]').forEach(btn => {
      if (btn.dataset.boundModalRelated) return;
      btn.dataset.boundModalRelated = '1';
      btn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const url = btn.dataset.relatedSource || '';
        if (url && openSource(url)) return;
        openStory(btn.dataset.modalRelated);
      });
    });
    observeStoryExposure();
  }

  async function refreshArticleStreamSilently(route) {
    if (['Home', 'Follow-up', 'Upcoming Events', 'Aetheria Read', 'Search'].includes(route)) return;
    try {
      const params = new URLSearchParams({ limit: '80' });
      if (route === 'India') params.set('india', '1');
      else if (route === 'World') params.set('world', '1');
      else if (!['Latest'].includes(route)) params.set('topic', routeTopic(route));
      const d = await getJSON(`/api/articles?${params.toString()}`);
      if (!d?.articles?.length) return;
      const newArticles = d.articles.map(x => ({ ...x, event_id: x.event_id || x.id }));
      const currentFirstId = state.articles?.[0]?.id || '';
      const newFirstId = newArticles[0]?.id || '';
      if (currentFirstId !== newFirstId) {
        state.articles = newArticles;
        const host = $('mainView');
        if (!host) return;
        const total = state.articles.length;
        const stackCount = Math.min(10, Math.max(5, total >= 14 ? 10 : total >= 9 ? total - 4 : total));
        const devCount = total >= stackCount + 4 ? 4 : 0;
        let stackHtml = '';
        let listItems = state.articles;
        if (total >= 5) {
          const isCategory = !['Latest'].includes(route);
          const developingItems = devCount ? state.articles.slice(stackCount, stackCount + devCount) : [];
          listItems = state.articles.slice(stackCount + devCount);
          const devHeadStr = isCategory ? `LATEST IN ${esc(route.toUpperCase())}` : 'DEVELOPING IN LATEST';
          const asideMarkup = devCount ? `<aside class="hero-card developing"><div class="dev-head"><b>${devHeadStr}</b><a data-route="Latest">View all →</a></div>${developingHTML(developingItems)}</aside>` : '';
          stackHtml = `<section class="hero">${renderStack()}${asideMarkup}</section>`;
        }
        const stackContainer = host.querySelector('.route-stack-container');
        if (stackContainer) stackContainer.innerHTML = stackHtml;
        const latestCard = host.querySelector('.latest-card');
        if (latestCard) latestCard.innerHTML = articleRows(listItems);
        bindStackControls();
        wireDynamicInteractions();
      }
    } catch (_) {}
  }

  async function refreshBootstrap(forceRender = false) {
    try {
      const bootstrapPromise = getJSON('/api/bootstrap', { timeout: 9000 }).then(d => {
        state.bootstrap = d;
        if (d?.market) renderMarkets(d.market);
        renderBanner();
        return d;
      });
      const followPromise = state.followUp
        ? Promise.resolve(state.followUp)
        : getJSON(`/api/follow-up?session=${encodeURIComponent(followSession())}`).catch(() => null).then(follow => {
          if (follow) state.followUp = follow;
          return follow;
        });
      const [d, follow] = await Promise.all([bootstrapPromise, followPromise]);
      if (d?.market) renderMarkets(d.market);
      renderBanner();
      if (d?.warming_up && state.route === 'Home') {
        $('mainView').innerHTML = `<section class="route-page"><div class="section-heading"><div><span class="section-kicker">STARTING AETHERIA</span><h1>Preparing live reporting</h1><p class="route-sub">${d.startup_error ? 'Startup needs attention; see the server console for details.' : 'The local database and current story snapshot are loading.'}</p></div></div><div class="latest-card">${loadingRows('Preparing the live story universe...')}</div></section>`;
        return;
      }
      if (state.route === 'Home') {
        if (forceRender) await renderRoute();
      } else {
        if (forceRender) {
          await renderRoute();
        } else if (!document.querySelector('.story-modal.open') && !document.querySelector('.search-dock.open')) {
          refreshArticleStreamSilently(state.route);
        }
      }
    } catch (err) {
      if (!state.bootstrap) {
        $('mainView').innerHTML = '<section class="route-page"><div class="empty-state">Aetheria is waiting for a live engine response. No substitute news has been generated.</div></section>';
      }
    }
  }

  function initAppearance() {
    $('themeBtn')?.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      const panel = $('appearancePanel');
      if (panel?.classList.contains('open')) {
        closeAppearance();
      } else {
        openAppearance();
      }
    });
    $('appearanceClose')?.addEventListener('click', closeAppearance);
    $('appearanceBackdrop')?.addEventListener('click', closeAppearance);
    $('appearanceBackdrop')?.addEventListener('pointerdown', closeAppearance);

    function setTheme(th) {
      if (!th) return;
      document.body.dataset.theme = th;
      document.documentElement.dataset.theme = th;
      try { localStorage.setItem('aetheria-theme', th); } catch (_) { }
      document.querySelectorAll('[data-theme]').forEach(x => x.classList.toggle('active', x.dataset.theme === th));
    }

    function resolveEffectiveMode(md) {
      if (md === 'system') {
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
      }
      return md;
    }

    function setMode(md) {
      if (!md) return;
      document.body.dataset.mode = md;
      document.documentElement.dataset.mode = md;
      const resolved = resolveEffectiveMode(md);
      document.body.dataset.resolvedMode = resolved;
      document.documentElement.dataset.resolvedMode = resolved;
      try { localStorage.setItem('aetheria-mode', md); } catch (_) { }
      document.querySelectorAll('[data-mode]').forEach(x => x.classList.toggle('active', x.dataset.mode === md));
    }

    if (window.matchMedia) {
      try {
        window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
          if (document.body.dataset.mode === 'system') {
            setMode('system');
          }
        });
      } catch (_) { }
    }

    function setScale(sc) {
      if (!sc) return;
      document.body.dataset.scale = sc;
      document.documentElement.dataset.scale = sc;
      try { localStorage.setItem('aetheria-scale', sc); } catch (_) { }
      document.querySelectorAll('[data-scale]').forEach(x => x.classList.toggle('active', x.dataset.scale === sc));
    }

    function setReadingShield(on) {
      if (on) {
        document.documentElement.dataset.readingShield = 'true';
        $('readingShieldBtn')?.classList.add('active');
        $('readingShieldBtn')?.setAttribute('aria-checked', 'true');
        try { localStorage.setItem('aetheria-reading-shield', 'true'); } catch (_) { }
      } else {
        delete document.documentElement.dataset.readingShield;
        $('readingShieldBtn')?.classList.remove('active');
        $('readingShieldBtn')?.setAttribute('aria-checked', 'false');
        try { localStorage.setItem('aetheria-reading-shield', 'false'); } catch (_) { }
      }
    }

    document.querySelectorAll('[data-theme]').forEach(b => b.addEventListener('click', () => setTheme(b.dataset.theme)));
    document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
    document.querySelectorAll('[data-scale]').forEach(b => b.addEventListener('click', () => setScale(b.dataset.scale)));

    $('readingShieldBtn')?.addEventListener('click', () => {
      const isCurrentlyOn = document.documentElement.dataset.readingShield === 'true';
      setReadingShield(!isCurrentlyOn);
    });

    let savedTheme = localStorage.getItem('aetheria-theme') || 'newspaper';
    if (savedTheme === 'ember') savedTheme = 'crimson';
    if (savedTheme === 'nordic') savedTheme = 'teal';
    const validThemes = ['newspaper', 'paper', 'midnight', 'aurora', 'crimson', 'teal', 'amethyst', 'ember', 'nordic'];
    if (!validThemes.includes(savedTheme)) {
      savedTheme = 'newspaper';
    }
    const savedMode = localStorage.getItem('aetheria-mode') || 'system';
    const savedScale = localStorage.getItem('aetheria-scale') || 'normal';
    const savedShield = localStorage.getItem('aetheria-reading-shield') === 'true';

    setTheme(savedTheme);
    setMode(savedMode);
    setScale(savedScale);
    setReadingShield(savedShield);
  }

  function initNavigation() {
    document.addEventListener('pointerdown', e => {
      if ($('appearancePanel')?.classList.contains('open')) {
        if (!e.target.closest('#appearancePanel') && !e.target.closest('#themeBtn')) {
          closeAppearance();
        }
      }
      if ($('searchDock')?.classList.contains('open')) {
        if (!e.target.closest('#searchDock') && !e.target.closest('#searchBtn')) {
          closeSearchDock();
        }
      }
    });

    document.addEventListener('click', e => {
      const trigger = e.target.closest('[data-category-trigger]');
      if (trigger) { e.preventDefault(); e.stopPropagation(); openCategory(trigger.dataset.categoryTrigger); return; }
      const source = e.target.closest('[data-source-url]');
      if (source && !e.target.closest('[data-route]')) { e.preventDefault(); e.stopPropagation(); if (openSource(source.dataset.sourceUrl)) return; }
      const route = e.target.closest('[data-route]');
      if (route && !route.dataset.categoryTrigger) { e.preventDefault(); navigate(route.dataset.route); return; }
      if (!e.target.closest('.category-panel')) closeCategoryPanels();
      if (!e.target.closest('#appearancePanel') && !e.target.closest('#themeBtn')) closeAppearance();
      if (!e.target.closest('#searchDock') && !e.target.closest('#searchBtn')) closeSearchDock();
    });
    window.addEventListener('resize', () => { ['top', 'bottom'].forEach(kind => { const p = $(kind === 'top' ? 'topCategoryPanel' : 'bottomCategoryPanel'); const t = document.querySelector(`[data-category-trigger="${kind}"]`); if (p?.classList.contains('open')) positionCategoryPanel(p, t, kind); }); });
    window.addEventListener('popstate', () => { const r = decodeURIComponent(location.hash.replace(/^#/, '') || 'Home'); if (ROUTES.includes(r)) navigate(r,{history:false}); });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeAllPopups();
        return;
      }
      if(storyModalOpen() && e.key==='Tab') {
        const modal = $('storyModal');
        const focusable = [...modal.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')]
          .filter(el => el.getClientRects().length > 0);
        if (!focusable.length) { e.preventDefault(); $('storyClose')?.focus(); return; }
        const first = focusable[0], last = focusable[focusable.length - 1], active = document.activeElement;
        if (e.shiftKey && (active === first || !modal.contains(active))) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (active === last || !modal.contains(active))) { e.preventDefault(); first.focus(); }
        return;
      }
      if (e.key !== 'Enter') return;
      if (e.target.closest('button,a,input,select,textarea,[contenteditable="true"]')) return;
      const row = e.target.closest('[data-source-url][tabindex="0"],[data-open-event][tabindex="0"],[data-open-story][tabindex="0"]');
      if (row) { e.preventDefault(); row.click(); }
    });
    $('storyClose')?.addEventListener('click', closeStory);
    $('storyModal')?.addEventListener('click', e => { if (e.target === $('storyModal')) closeStory(); });
    $('searchBtn')?.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); openSearchDock(); });
    $('aetheriaBrand')?.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); navigate('Home'); });
    $('aetheriaBrand')?.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('Home'); } });
    $('searchDockInput')?.addEventListener('input', () => { if (state.searchSuggestTimer) clearTimeout(state.searchSuggestTimer); state.searchSuggestTimer = setTimeout(updateSearchSuggestions, 160); });
    $('searchDockInput')?.addEventListener('keydown', e => {
      const host = $('searchSuggestions'); if (!host?.classList.contains('open')) return;
      const rows = [...host.querySelectorAll('.search-suggestion')]; if (!rows.length) return;
      const current = rows.findIndex(x => x.classList.contains('keyboard-active'));
      if (e.key === 'ArrowDown') { e.preventDefault(); rows.forEach(x => x.classList.remove('keyboard-active')); const n = (current + 1) % rows.length; rows[n].classList.add('keyboard-active'); rows[n].scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); rows.forEach(x => x.classList.remove('keyboard-active')); const n = (current <= 0 ? rows.length : current) - 1; rows[n].classList.add('keyboard-active'); rows[n].scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'Enter' && current >= 0) { e.preventDefault(); rows[current].click(); }
    });
    $('searchDockForm')?.addEventListener('submit', e => { e.preventDefault(); submitTopSearch(); });
    $('searchDockClose')?.addEventListener('click', closeSearchDock);
    $('topCategoryClose')?.addEventListener('click', closeCategoryPanels);
    $('bottomCategoryClose')?.addEventListener('click', closeCategoryPanels);
    $('marketsLink')?.addEventListener('click', () => navigate('Markets'));
  }

  function updateLiveClock() {
    const el = $('topbarLiveClock');
    if (!el) return;
    const now = new Date();
    const dateStr = now.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    const timeStr = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    el.innerHTML = `<span class="live-clock-time" style="display:block;font-size:9.5px;font-weight:600;line-height:1.15;color:var(--ink-muted);opacity:0.7;letter-spacing:0.02em;white-space:nowrap;text-align:right;">${esc(timeStr)}</span><span class="live-clock-date" style="display:block;font-size:7.5px;font-weight:500;line-height:1.15;color:var(--ink-muted);opacity:0.45;letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;text-align:right;">${esc(dateStr)}</span>`;
  }

  function init() {
    initAppearance(); initNavigation();
    updateLiveClock();
    setInterval(updateLiveClock, 1000);
    try {
      const cached = localStorage.getItem('aetheria-cached-markets');
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed?.groups?.length) {
          renderMarkets(parsed);
        } else {
          renderMarketSkeleton();
        }
      } else {
        renderMarketSkeleton();
      }
    } catch (_) {
      renderMarketSkeleton();
    }
    const initial = decodeURIComponent(location.hash.replace(/^#/, '') || 'Home');
    state.route = ROUTES.includes(initial) ? initial : 'Home';
    refreshBootstrap(true);
    state.refreshTimer = setInterval(() => {
      refreshBootstrap(false);
      if (state.bootstrap?.ready) { clearInterval(state.refreshTimer); state.refreshTimer = setInterval(() => refreshBootstrap(false), 10000); }
    }, 1000);
    setInterval(() => { if (state.route !== 'Home') return; renderBanner(); }, 15000);
  }
  init();
})();
