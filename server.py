from __future__ import annotations

import concurrent.futures
import hashlib
import gzip
import math
import html
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import unicodedata
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from db_adapter import get_db, UniversalRow

# AETHERIA CORE V22.2 — WORLD UNDERSTOOD / INDIA-FIRST INTELLIGENCE
# Principles:
# - Real external sources only; no synthetic news fallback.
# - Source failures are isolated.
# - Ingestion is asynchronous; the UI never waits for ranking/source diagnostics.
# - Read APIs are served from an in-memory snapshot built in the background.
# - Search uses SQLite FTS5 when available.
# - Learning is behavioural and reversible; no code is self-rewritten at runtime.

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
CONFIG_DIR = Path(os.environ.get("AETHERIA_CONFIG_DIR", str(BASE_DIR))).expanduser()
SOURCES_FILE = Path(os.environ.get("AETHERIA_SOURCES", str(CONFIG_DIR / "sources.json"))).expanduser()
DATA_DIR = Path(os.environ.get("AETHERIA_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_FILE = Path(os.environ.get("AETHERIA_DB", str(DATA_DIR / "aetheria.db"))).expanduser()
HOST = os.environ.get("AETHERIA_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("AETHERIA_PORT", "8000")))
VERSION = "V23.1"
USER_AGENT = os.environ.get("AETHERIA_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Aetheria/23.1 world-intelligence")
SCAN_SECONDS = float(os.environ.get("AETHERIA_SCAN_SECONDS", "2.0"))
SNAPSHOT_SECONDS = float(os.environ.get("AETHERIA_SNAPSHOT_SECONDS", "2.0"))
LEARNING_SECONDS = int(os.environ.get("AETHERIA_LEARNING_SECONDS", "300"))
TELEMETRY_FLUSH_SECONDS = float(os.environ.get("AETHERIA_TELEMETRY_FLUSH_SECONDS", "3"))
MAX_WORKERS = int(os.environ.get("AETHERIA_WORKERS", "32"))
FEED_TIMEOUT = float(os.environ.get("AETHERIA_FEED_TIMEOUT", "8.0"))
GDELT_TIMEOUT = float(os.environ.get("AETHERIA_GDELT_TIMEOUT", "12.0"))
MAX_ITEMS_PER_SOURCE = int(os.environ.get("AETHERIA_MAX_ITEMS_PER_SOURCE", "150"))
MAX_DISCOVERY_ITEMS = int(os.environ.get("AETHERIA_MAX_DISCOVERY_ITEMS", "300"))
MAX_RESPONSE_BYTES = int(os.environ.get("AETHERIA_MAX_RESPONSE_BYTES", str(8 * 1024 * 1024)))
CONNECT_TIMEOUT = float(os.environ.get("AETHERIA_CONNECT_TIMEOUT", "6.0"))
RETENTION_DAYS = int(os.environ.get("AETHERIA_RETENTION_DAYS", "30"))
EVENT_ACTIVE_HOURS = float(os.environ.get("AETHERIA_EVENT_ACTIVE_HOURS", "72"))
EVENT_POOL_LIMIT = int(os.environ.get("AETHERIA_EVENT_POOL_LIMIT", "5000"))
SNAPSHOT_EVENT_LIMIT = int(os.environ.get("AETHERIA_SNAPSHOT_EVENT_LIMIT", "180"))
LOCAL_ANALYSIS_SNIPPETS = int(os.environ.get("AETHERIA_LOCAL_ANALYSIS_SNIPPETS", "8"))
LATEST_LANE_LIMIT = int(os.environ.get("AETHERIA_LATEST_LANE_LIMIT", "400"))
SECONDARY_LANE_LIMIT = int(os.environ.get("AETHERIA_SECONDARY_LANE_LIMIT", "18"))
SIGNAL_LANE_LIMIT = int(os.environ.get("AETHERIA_SIGNAL_LANE_LIMIT", "5"))
EVENT_INDEX_LIMIT = int(os.environ.get("AETHERIA_EVENT_INDEX_LIMIT", "2000"))
PRIMARY_DESCRIPTION_LIMIT = int(os.environ.get("AETHERIA_PRIMARY_DESCRIPTION_LIMIT", "360"))

# Dynamic source discovery and local context configuration. Static source URLs are
# configuration, not content; discovered feeds are persisted so a catalog outage
# does not remove previously discovered feeds.
DYNAMIC_SOURCES_FILE = DATA_DIR / "dynamic_sources.json"
DYNAMIC_CATALOG_INTERVAL = int(os.environ.get("AETHERIA_DYNAMIC_CATALOG_INTERVAL", "1800"))
DYNAMIC_SOURCE_LIMIT = int(os.environ.get("AETHERIA_DYNAMIC_SOURCE_LIMIT", "600"))
AETHERIA_CITY = clean_text(os.environ.get("AETHERIA_CITY", "")) if "clean_text" in globals() else os.environ.get("AETHERIA_CITY", "")
AETHERIA_STATE = clean_text(os.environ.get("AETHERIA_STATE", "")) if "clean_text" in globals() else os.environ.get("AETHERIA_STATE", "")
INDIA_LANGUAGES = {"hi","bn","mr","ta","te","kn","ml","gu","pa"}
RSS_CATALOGS = [
    {"name":"NDTV RSS", "url":"https://www.ndtv.com/rss", "provider":"NDTV"},
    {"name":"The Indian Express RSS", "url":"https://indianexpress.com/rss/", "provider":"The Indian Express"},
    {"name":"Times of India RSS", "url":"https://timesofindia.indiatimes.com/rss.cms", "provider":"Times of India"},
    {"name":"Hindustan Times RSS", "url":"https://www.hindustantimes.com/rss", "provider":"Hindustan Times"},
    {"name":"India Today RSS", "url":"https://www.indiatoday.in/rss", "provider":"India Today"},
    {"name":"Amar Ujala RSS", "url":"https://www.amarujala.com/rss", "provider":"Amar Ujala"},
    {"name":"Live Hindustan RSS", "url":"https://www.livehindustan.com/rss", "provider":"Live Hindustan"},
    {"name":"OneIndia Telugu RSS", "url":"https://telugu.oneindia.com/rss/", "provider":"OneIndia Telugu"},
    {"name":"OneIndia Odia RSS", "url":"https://odia.oneindia.com/rss/", "provider":"OneIndia Odia"},
    {"name":"Business Standard Hindi RSS", "url":"https://hindi.business-standard.com/rss-feeds", "provider":"Business Standard Hindi"},
    {"name":"Economic Times RSS", "url":"https://economictimes.indiatimes.com/rss.cms", "provider":"Economic Times"},
    {"name":"ET Government RSS", "url":"https://government.economictimes.indiatimes.com/rss", "provider":"ET Government"},
    {"name":"ET B2B RSS", "url":"https://b2b.economictimes.indiatimes.com/rss", "provider":"ET B2B"},
    {"name":"ET Infra RSS", "url":"https://infra.economictimes.indiatimes.com/rss", "provider":"ET Infra"},
    {"name":"ET CFO RSS", "url":"https://cfo.economictimes.indiatimes.com/rss", "provider":"ET CFO"},
    {"name":"ET LegalWorld RSS", "url":"https://legal.economictimes.indiatimes.com/rss", "provider":"ET LegalWorld"},
    {"name":"ET BFSI RSS", "url":"https://bfsi.economictimes.indiatimes.com/rss", "provider":"ET BFSI"},
    {"name":"ET Sustainability RSS", "url":"https://sustainability.economictimes.indiatimes.com/rss", "provider":"ET Sustainability"},
]


STOPWORDS = set("the a an and or to of in on for with as at by from is are was were after over new latest says say that this these those has have had into about amid during against before between through their its it be been being will would could should than more most not no how why who what when where which while according report reports reported update updates official officials".split())
URGENT = set("breaking urgent emergency warning attack explosion earthquake tsunami cyclone hurricane flood wildfire evacuation evacuate crash collapse missile war conflict sanctions strike ceasefire outage blackout alert dies death killed injures threat shooting volcano".split())

CATEGORIES = [
    ("Top", "Top"), ("World", "World"), ("India", "India"), ("Local", "Local"), ("Politics", "Politics"),
    ("Geopolitics", "Geopolitics"), ("Legal", "Legal"), ("Business", "Business"), ("Markets", "Markets"), ("Economy", "Economy"),
    ("Technology", "Technology"), ("AI", "AI"), ("Science", "Science"), ("Space", "Space"), ("Health", "Health"),
    ("Climate", "Climate"), ("Weather", "Weather"), ("Sports", "Sports"), ("Entertainment", "Entertainment"),
    ("Culture", "Culture"), ("Property", "Property"), ("Energy", "Energy"), ("Commodities", "Commodities"),
    ("Travel", "Travel"), ("Education", "Education"), ("Autos", "Autos"),
]
TOPIC_TERMS = {
    "Sports": set("sport sports football soccer cricket tennis golf basketball baseball hockey formula motorsport racing boxing mma olympics fifa nba nfl mlb nhl atp wta premier league champions league match matches game games tournament championship athlete athletes coach transfer transfers score scores fixtures results medal medals grand prix f1 indycar nascar college football".split()),
    "AI": set("ai artificial intelligence generative model models chatbot machine learning neural agent agents robotics inference model".split()),
    "Technology": set("technology tech software hardware semiconductor semiconductors chip chips cloud cybersecurity cyber privacy smartphone apple google microsoft meta amazon developer platform computing data digital internet".split()),
    "Markets": set("stock stocks shares equity equities market markets index indices sensex nifty dow nasdaq sp500 bonds yields rupee dollar euro forex trading investor investors futures options".split()),
    "Business": set("business company companies earnings merger acquisition ipo startup startups corporate ceo revenue profit sales jobs employment industry retail logistics trade".split()),
    "Economy": set("economy economic inflation gdp recession growth unemployment wages central bank interest rates fiscal monetary debt deficit tariffs".split()),
    "Finance": set("bank banking finance financial lending credit mortgage insurance payment payments fintech".split()),
    "Commodities": set("commodity commodities oil crude brent wti gold silver copper wheat maize rice soybean soybeans fertilizer steel coal aluminum aluminium gas natural gas grain grains palm palm oil".split()),
    "Energy": set("energy power electricity solar wind nuclear reactor renewable grid battery batteries utility utilities lng oil gas".split()),
    "Science": set("science research study studies discovery discoveries experiment experiments physics chemistry biology medicine vaccine vaccines gene genetics laboratory lab".split()),
    "Space": set("space nasa esa orbit satellite satellites moon lunar mars rocket rockets launch launches asteroid asteroids comet astronomy telescope".split()),
    "Health": set("health healthcare medicine medical hospital hospitals disease diseases drug drugs pharma pharmaceutical public health cancer diabetes mental wellness".split()),
    "Climate": set("climate climate change emissions carbon greenhouse warming drought heatwave biodiversity environment pollution conservation".split()),
    "Weather": set("weather storm storms cyclone cyclones hurricane hurricanes flood floods earthquake earthquakes tsunami wildfire wildfires tornado rainfall rain snow heat cold warning evacuation volcano".split()),
    "Geopolitics": set("geopolitics diplomacy diplomatic conflict war wars sanctions tariff tariffs treaty treaties military defence defense border nato iran israel palestine gaza russia ukraine china taiwan missile ceasefire security".split()),
    "Politics": set("politics political parliament congress senate election elections vote voting government minister president prime minister opposition party parties legislation bill policy campaign".split()),
    "Legal": set("court courts supreme high judge judges bench verdict ruling bail trial petition petitioner lawsuit litigation lawyer lawyers advocate advocates legal justice criminal civil constitutional arbitration tribunal judgment prosecution ed cbi nia fir bar council sc hc order appeal affidavit habeas corpus remand chargesheet convict acquitted jurisdiction stay injunction".split()),
    "India": set("india indian bharat delhi mumbai bengaluru bangalore hyderabad chennai kolkata punjab gujarat maharashtra rajasthan karnataka kerala tamil nadu telangana bihar up uttar pradesh madhya pradesh west bengal odisha assam jaipur ahmedabad pune lucknow".split()),
    "Local": set("municipal municipality civic corporation police traffic district neighbourhood neighborhood local court station metro airport road flyover housing authority civic body".split()),
    "Property": set("property real estate housing homes home prices rent rental mortgage apartment apartments commercial property residential construction builder developers development".split()),
    "Travel": set("travel tourism tourist airport airline airlines flight flights hotel hotels holiday holidays visa destination destinations".split()),
    "Education": set("education school schools university universities college colleges student students exam exams curriculum teacher teachers scholarship".split()),
    "Entertainment": set("entertainment film films movie movies cinema actor actress music singer album streaming television tv series celebrity celebrities box office".split()),
    "Culture": set("culture books book literature art arts museum theatre theater heritage festival festivals design food cuisine".split()),
    "Autos": set("auto autos automobile automobiles car cars vehicle vehicles ev electric vehicle tesla toyota volkswagen ford gm motor motors bikes motorcycle".split()),
}

DB_LOCK = threading.Lock()
STOP = threading.Event()
SOURCE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="aetheria-source")
SOURCE_INFLIGHT: set[str] = set()
SOURCE_INFLIGHT_LOCK = threading.Lock()
LAST_LEARNING = 0.0
SOURCE_CONFIG_MTIME = 0.0
SOURCE_CONFIG_LAST_CHECK = 0.0
SNAPSHOT_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
TELEMETRY_LOCK = threading.Lock()
EVENT_INDEX_LOCK = threading.Lock()
FEED_INVALIDATED = threading.Event()

SNAPSHOT = {"revision": 0, "built_at": 0.0, "events": [], "important": [], "impact": [], "latest": [], "moving": [], "sections": [], "categories": [], "future": [], "market": {}, "home": {}, "state": {}}
STATE_CACHE = {"at": 0.0, "value": {}}
TELEMETRY_QUEUE = deque()
EVENT_INDEX = []
EVENT_POSTINGS = defaultdict(set)
EVENT_ENTITY_POSTINGS = defaultdict(set)
EVENT_INDEX_LAST_REFRESH = 0.0
EVENT_INDEX_MIN_REFRESH = float(os.environ.get("AETHERIA_EVENT_INDEX_MIN_REFRESH", "1.0"))
CLUSTER_CANDIDATE_TOKEN_LIMIT = int(os.environ.get("AETHERIA_CLUSTER_CANDIDATE_TOKEN_LIMIT", "8"))
CLUSTER_MAX_DF_RATIO = float(os.environ.get("AETHERIA_CLUSTER_MAX_DF_RATIO", "0.08"))
CLUSTER_MIN_RARE_DF = int(os.environ.get("AETHERIA_CLUSTER_MIN_RARE_DF", "8"))
FUTURE_CACHE_SECONDS = float(os.environ.get("AETHERIA_FUTURE_CACHE_SECONDS", "45"))
FUTURE_CACHE_LOCK = threading.Lock()
FUTURE_CACHE = {"at": 0.0, "value": []}
MARKET_POLL_SECONDS = float(os.environ.get("AETHERIA_MARKET_POLL_SECONDS", "30"))
MARKET_CACHE_LOCK = threading.Lock()
MARKET_CACHE = {"at": 0.0, "status": "warming", "groups": []}
MARKET_REFRESH_INFLIGHT = False
AI_LOCK = threading.Lock()
AI_INFLIGHT: set[str] = set()


def now() -> float:
    return time.time()


def db():
    return get_db(DB_FILE, timeout=5.0)


def db_read():
    return get_db(DB_FILE, timeout=5.0, query_only=True)


def ensure_column(con, table, column, definition):
    if getattr(con, "is_postgres", False):
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            con.commit()
        except Exception:
            pass
        return
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    with DB_LOCK:
        con = db()
        con.executescript("""
        CREATE TABLE IF NOT EXISTS sources(
          id TEXT PRIMARY KEY,name TEXT NOT NULL,provider TEXT,url TEXT UNIQUE NOT NULL,topic TEXT,tier TEXT,format TEXT,
          interval_sec INTEGER DEFAULT 300,max_items INTEGER,enabled INTEGER DEFAULT 1,etag TEXT,last_modified TEXT,last_success REAL,
          last_failure REAL,failures INTEGER DEFAULT 0,fetched INTEGER DEFAULT 0,items INTEGER DEFAULT 0,corroborated INTEGER DEFAULT 0,
          language TEXT DEFAULT 'en',
          country TEXT DEFAULT '',
          discovered_from TEXT DEFAULT '',
          region TEXT DEFAULT '',
          city TEXT DEFAULT '',
          state_name TEXT DEFAULT '',
          corrections INTEGER DEFAULT 0,reliability REAL DEFAULT 0.50,created_at REAL,updated_at REAL,
          state TEXT DEFAULT 'idle',last_attempt REAL,last_duration_ms INTEGER DEFAULT 0,last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS articles(
          id TEXT PRIMARY KEY,source_id TEXT,canonical_url TEXT UNIQUE,title TEXT NOT NULL,description TEXT,published REAL,fetched REAL,
          language TEXT,country TEXT,topic TEXT,tier TEXT,domain TEXT,fingerprint TEXT,image_url TEXT,
          FOREIGN KEY(source_id) REFERENCES sources(id)
        );
        CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published);
        CREATE INDEX IF NOT EXISTS idx_articles_fingerprint ON articles(fingerprint);
        CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY,title TEXT NOT NULL,topic TEXT,status TEXT NOT NULL,first_seen REAL,last_seen REAL,last_change REAL,
          velocity REAL DEFAULT 0,novelty REAL DEFAULT 0,corroboration REAL DEFAULT 0,authority REAL DEFAULT 0,urgency REAL DEFAULT 0,
          significance REAL DEFAULT 0,india_relevance REAL DEFAULT 0,financial_relevance REAL DEFAULT 0,supply_chain_relevance REAL DEFAULT 0,
          geopolitical_relevance REAL DEFAULT 0,social_relevance REAL DEFAULT 0,article_count INTEGER DEFAULT 0,source_count INTEGER DEFAULT 0,
          official_count INTEGER DEFAULT 0,publisher_count INTEGER DEFAULT 0,discovery_count INTEGER DEFAULT 0,primary_article_id TEXT,
          summary TEXT,entities TEXT DEFAULT '[]',locations TEXT DEFAULT '[]',last_reason TEXT,created_at REAL,updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_events_last_seen ON events(last_seen);
        CREATE INDEX IF NOT EXISTS idx_events_significance ON events(significance);
        CREATE INDEX IF NOT EXISTS idx_events_topic_seen ON events(topic,last_seen);
        CREATE TABLE IF NOT EXISTS event_articles(event_id TEXT,article_id TEXT,first_linked REAL,PRIMARY KEY(event_id,article_id));
        CREATE TABLE IF NOT EXISTS event_updates(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,article_id TEXT,observed_at REAL,change_type TEXT,note TEXT);
        CREATE INDEX IF NOT EXISTS idx_event_updates_event ON event_updates(event_id,observed_at);
        CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,action TEXT,value REAL DEFAULT 1,at REAL,session TEXT);
        CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session,at);
        CREATE TABLE IF NOT EXISTS learning(key TEXT PRIMARY KEY,value REAL DEFAULT 0,observations INTEGER DEFAULT 0,updated_at REAL);
        CREATE TABLE IF NOT EXISTS system_metrics(key TEXT PRIMARY KEY,value TEXT,updated_at REAL);
        CREATE TABLE IF NOT EXISTS ai_context(event_id TEXT PRIMARY KEY,summary TEXT,changed TEXT,watch TEXT,provider TEXT,model TEXT,generated_at REAL,status TEXT);
        CREATE TABLE IF NOT EXISTS schedules(
          id TEXT PRIMARY KEY, source_id TEXT, title TEXT NOT NULL, category TEXT, kind TEXT, start_ts REAL NOT NULL, end_ts REAL,
          time_known INTEGER DEFAULT 1, url TEXT, description TEXT, importance REAL DEFAULT 0.50, updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_schedules_start ON schedules(start_ts);
        CREATE INDEX IF NOT EXISTS idx_schedules_category ON schedules(category,start_ts);
        CREATE TABLE IF NOT EXISTS user_follows(
          session TEXT, event_id TEXT, followed_at REAL, last_seen_change REAL, last_checked REAL,
          PRIMARY KEY(session, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_follows_session ON user_follows(session);
        """)
        ensure_column(con,"sources","max_items","INTEGER")
        ensure_column(con,"sources","language","TEXT")
        ensure_column(con,"sources","country","TEXT")
        ensure_column(con,"sources","discovered_from","TEXT")
        ensure_column(con,"sources","region","TEXT")
        ensure_column(con,"sources","city","TEXT")
        ensure_column(con,"sources","state_name","TEXT")
        ensure_column(con,"sources","consecutive_failures","INTEGER DEFAULT 0")
        ensure_column(con,"sources","last_http_status","INTEGER DEFAULT 0")
        ensure_column(con,"sources","next_attempt_at","REAL DEFAULT 0")
        ensure_column(con,"sources","error_class","TEXT DEFAULT ''")
        ensure_column(con,"ai_context","why","TEXT")
        ensure_column(con,"ai_context","uncertainty","TEXT")
        ensure_column(con,"ai_context","evidence_note","TEXT")
        # latest_article_id tracks the most recently ingested article per event (by pub time)
        # This is separate from primary_article_id (original founding article) and is used
        # to display the freshest headline/URL in the Latest tab.
        ensure_column(con,"events","latest_article_id","TEXT")
        ensure_column(con,"events","latest_article_pub","REAL DEFAULT 0")
        try:
            con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS event_fts USING fts5(event_id UNINDEXED,title,summary,topic,entities,locations,domains,article_titles)")
        except Exception:
            pass
        con.commit(); con.close()
        # Backfill latest_article_id for events created before this column was added.
        try:
            con=db()
            backfilled=con.execute("""UPDATE events SET
                latest_article_id=(SELECT a.id FROM event_articles ea JOIN articles a ON a.id=ea.article_id
                    WHERE ea.event_id=events.id ORDER BY COALESCE(a.published,0) DESC LIMIT 1),
                latest_article_pub=(SELECT COALESCE(MAX(a.published),0) FROM event_articles ea JOIN articles a ON a.id=ea.article_id
                    WHERE ea.event_id=events.id)
                WHERE latest_article_id IS NULL AND EXISTS(SELECT 1 FROM event_articles WHERE event_id=events.id)""").rowcount
            if backfilled>0: print(f"[init_db] Backfilled latest_article_id for {backfilled} events",flush=True)
            # Fix GDELT discovery intervals to 600s — was 60-120s causing HTTP 429 rate limits.
            gdelt_fixed=con.execute("UPDATE sources SET interval_sec=600 WHERE name LIKE '%GDELT%' AND tier='discovery' AND interval_sec<300").rowcount
            if gdelt_fixed>0: print(f"[init_db] Set GDELT discovery interval=600s for {gdelt_fixed} sources",flush=True)
            con.commit(); con.close()
        except Exception as be:
            print(f"[init_db] migration warning: {be}",flush=True)
        # Configure WAL once during startup; concurrent request connections only read/write normally.
        try:
            con=db(); con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA synchronous=NORMAL"); con.close()
        except Exception:
            pass


def clean_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(url: str) -> str:
    try:
        p = urllib.parse.urlsplit(url)
        if p.scheme not in ("http", "https"):
            return url
        blocked = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","mc_cid","mc_eid"}
        q = [(k,v) for k,v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k.lower() not in blocked]
        return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip("/"),urllib.parse.urlencode(q),""))
    except Exception:
        return url


def parse_date(value) -> float | None:
    if value is None: return None
    ts = None
    if isinstance(value,(int,float)):
        ts = float(value)/1000 if value > 10_000_000_000 else float(value)
    else:
        v_str = clean_text(str(value))
        if not v_str: return None
        for v in (v_str, v_str.replace("Z","+00:00")):
            try:
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
                break
            except Exception: pass
        if ts is None:
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT", "%a, %d %b %Y %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(v_str, fmt)
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                    ts = dt.timestamp()
                    break
                except Exception: pass
    if ts is not None:
        t_curr = now()
        if ts > t_curr + 86400 or ts < 946684800:
            return None
        return ts
    return None


def tokens(text: str) -> set[str]:
    # Script-agnostic tokenizer: group Unicode letters/marks/numbers so Indic,
    # Latin, Cyrillic and other scripts remain searchable without a language dictionary.
    out=[]; cur=[]
    for ch in clean_text(text).lower():
        cat=unicodedata.category(ch)
        if cat.startswith(("L","M","N")):
            cur.append(ch)
        elif cur:
            token="".join(cur)
            if len(token)>=2 and token not in STOPWORDS:
                out.append(token)
            cur=[]
    if cur:
        token="".join(cur)
        if len(token)>=2 and token not in STOPWORDS:
            out.append(token)
    return set(out)


def token_jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1,len(a | b))


def norm_title(text: str) -> str:
    t = clean_text(text).lower()
    t = re.sub(r"\b(live updates?|live|watch|breaking|latest|update)\b[:\-–—]?", " ", t)
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+"," ",t).strip()


def fingerprint(title: str, domain: str) -> str:
    return hashlib.sha1((norm_title(title)+"|"+domain.lower()).encode()).hexdigest()


def stable_id(prefix: str, value: str) -> str:
    return prefix + "_" + hashlib.sha1(value.encode()).hexdigest()[:20]


def extract_entities(text: str):
    """Extract title-level entities without a fixed name dictionary.

    Capitalized phrase + numeric/alphanumeric tokens are retained so identities
    such as product names, model numbers and aircraft designations stay distinct while ordinary
    repeated vocabulary remains useful for semantic matching.
    """
    raw=clean_text(text)
    candidates=[]
    phrase_re = re.compile(r"\b(?:[A-Z][A-Za-z0-9’'&.-]{1,})(?:(?:\s+)(?:[A-Z][A-Za-z0-9’'&.-]{1,}|\d{1,6})){0,4}\b")
    for m in phrase_re.finditer(raw):
        phrase=m.group(0).strip(" .,:;!?-")
        if len(phrase)<3: continue
        words=phrase.split()
        if all(w.lower() in STOPWORDS for w in words): continue
        low=phrase.lower()
        if low not in {x.lower() for x in candidates}: candidates.append(phrase)
    # Standalone uppercase identifiers/tickers remain useful as cross-source anchors.
    for tok in re.findall(r"\b[A-Z]{2,8}(?:[-.][A-Z0-9]{1,8})?\b", raw):
        if tok.lower() not in STOPWORDS and tok.lower() not in {x.lower() for x in candidates}:
            candidates.append(tok)
    return candidates[:16]



def infer_topic(title: str, configured: str) -> str:
    """Use source configuration as the baseline, but reclassify broad feeds
    when the article title carries a strong specialist topic signal.
    """
    t=tokens(title); scores={k:len(t&v) for k,v in TOPIC_TERMS.items()}
    priority=["Sports","AI","Markets","Commodities","Energy","Technology","Science","Space","Health","Weather","Climate","Geopolitics","Legal","Politics","Business","Economy","Property","Travel","Education","Entertainment","Culture","Autos","India","Local"]
    best=max(priority,key=lambda k:(scores.get(k,0),-priority.index(k)))
    best_score=scores.get(best,0)
    broad={"World","All","Top"}
    if configured and configured not in broad:
        # Source taxonomy is the stable category anchor. Reclassify only when
        # the article title carries a materially stronger specialist signal.
        configured_score=scores.get(configured,0)
        if best==configured or best_score < max(3,configured_score+3):
            return configured
    return best if best_score else (configured or "World")



# Keep topical terms available for event matching; only generic news grammar is
# removed. This prevents terms such as wheat, shares, missile, or satellite from
# disappearing from the event signature before similarity is calculated.
CLUSTER_GENERIC = STOPWORDS | {"live","developing","breaking","watch","latest","update","updates","reports","report","says","said","story","stories","video","photos"}

def content_tokens(text: str) -> set[str]:
    return {w for w in tokens(text) if w not in CLUSTER_GENERIC}

def numeric_entity_anchors(entities):
    """Return named/alphanumeric identity anchors containing digits.
    These dynamically protect distinct numbered variants from chain-merging.
    """
    return {str(e).strip().lower() for e in (entities or ()) if re.search(r"\d", str(e))}

def numeric_title_anchors(text):
    """Return standalone numeric identifiers, excluding ordinary calendar years."""
    out=set()
    for tok in re.findall(r"(?<![A-Za-z])\d{1,6}(?![A-Za-z])", clean_text(text)):
        try: n=int(tok)
        except Exception: continue
        if 1900 <= n <= 2100: continue
        out.add(tok)
    return out

def build_postings(index_rows):
    postings=defaultdict(set); entity_postings=defaultdict(set)
    for e in index_rows:
        eid=e["id"]
        for tok in (e.get("tokens_content") or e.get("tokens") or set()): postings[tok].add(eid)
        for ent in (e.get("entities") or set()): entity_postings[str(ent).lower()].add(eid)
    return postings,entity_postings



def _load_dynamic_source_rows():
    try:
        if not DYNAMIC_SOURCES_FILE.exists(): return []
        rows=json.loads(DYNAMIC_SOURCES_FILE.read_text(encoding="utf-8"))
        return [x for x in rows if x.get("url") and x.get("name") and x.get("enabled",True)]
    except Exception:
        return []


def load_source_config():
    if not SOURCES_FILE.exists():
        raise RuntimeError(f"Source registry not found: {SOURCES_FILE}")
    static_rows=json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    merged=[]; seen=set()
    for x in static_rows + _load_dynamic_source_rows():
        url=canonical_url(str(x.get("url") or ""))
        if not url or not x.get("name") or not x.get("enabled",True) or url in seen: continue
        seen.add(url); y=dict(x); y["url"]=url; merged.append(y)
    return merged


def _catalog_topic(label, url):
    text=clean_text(f"{label} {url}").lower()
    if any(k in text for k in ("entertainment","bollywood","hollywood","movie","movies","cinema","music","actor","actress","celebrity","film","television","series")): return "Entertainment"
    if any(k in text for k in ("sport","cricket","football","tennis","golf","ipl","olympic")): return "Sports"
    if any(k in text for k in ("market","stock","share","ipo","forex","gold","commodity","equity","mutual")): return "Markets"
    if any(k in text for k in ("bank","finance","insurance","tax","wealth","money")): return "Finance"
    if any(k in text for k in ("company","corporate","industry","startup","business","trade","retail")): return "Business"
    if any(k in text for k in ("technology","tech","ai","artificial","cyber","software","semiconductor")): return "Technology"
    if any(k in text for k in ("science","research","space","nasa")): return "Science"
    if any(k in text for k in ("weather","climate","environment","pollution","storm","earthquake")): return "Weather"
    if any(k in text for k in ("politic","election","government","governance","policy")): return "Politics"
    if any(k in text for k in ("international","world","global","diplomacy","defence","defense","geopolit")): return "World"
    if any(k in text for k in ("delhi","mumbai","bengaluru","bangalore","hyderabad","chennai","kolkata","pune","jaipur","lucknow","ahmedabad","city","cities","state","uttar-pradesh","bihar","punjab","gujarat","maharashtra","rajasthan","kerala","karnataka","telangana","tamil-nadu")): return "Local"
    if any(k in text for k in ("india","indian","bharat","national","nation")): return "India"
    return "World"


def _catalog_language(label, url):
    text=f"{label} {url}"
    if re.search(r"[\u0900-\u097F]",text) or "hindi" in text.lower() or "hindi." in url.lower(): return "hi"
    if re.search(r"[\u0980-\u09FF]",text): return "bn"
    if re.search(r"[\u0B80-\u0BFF]",text): return "ta"
    if re.search(r"[\u0C00-\u0C7F]",text): return "te"
    if re.search(r"[\u0C80-\u0CFF]",text): return "kn"
    if re.search(r"[\u0D00-\u0D7F]",text): return "ml"
    if re.search(r"[\u0A80-\u0AFF]",text): return "gu"
    if re.search(r"[\u0A00-\u0A7F]",text): return "pa"
    if re.search(r"[\u0900-\u097F]",text): return "hi"
    return "en"


def _catalog_city_state(label, url):
    text=clean_text(f"{label} {url}").lower().replace("_","-")
    city_map={
      "delhi":("Delhi","Delhi"),"delhi-ncr":("Delhi NCR","Delhi"),"mumbai":("Mumbai","Maharashtra"),"pune":("Pune","Maharashtra"),
      "bengaluru":("Bengaluru","Karnataka"),"bangalore":("Bengaluru","Karnataka"),"hyderabad":("Hyderabad","Telangana"),
      "chennai":("Chennai","Tamil Nadu"),"kolkata":("Kolkata","West Bengal"),"jaipur":("Jaipur","Rajasthan"),
      "ahmedabad":("Ahmedabad","Gujarat"),"lucknow":("Lucknow","Uttar Pradesh"),"patna":("Patna","Bihar"),
      "chandigarh":("Chandigarh","Chandigarh"),"guwahati":("Guwahati","Assam"),"nagpur":("Nagpur","Maharashtra"),
      "surat":("Surat","Gujarat"),"rajkot":("Rajkot","Gujarat"),"bhubaneswar":("Bhubaneswar","Odisha"),
    }
    for key,val in city_map.items():
        if re.search(rf"(?<![a-z]){re.escape(key)}(?![a-z])",text): return val
    state_map={
      "uttar-pradesh":"Uttar Pradesh","uttarakhand":"Uttarakhand","bihar":"Bihar","jharkhand":"Jharkhand","rajasthan":"Rajasthan",
      "punjab":"Punjab","haryana":"Haryana","maharashtra":"Maharashtra","gujarat":"Gujarat","karnataka":"Karnataka",
      "kerala":"Kerala","telangana":"Telangana","tamil-nadu":"Tamil Nadu","andhra-pradesh":"Andhra Pradesh","west-bengal":"West Bengal",
      "odisha":"Odisha","assam":"Assam","goa":"Goa","madhya-pradesh":"Madhya Pradesh","chhattisgarh":"Chhattisgarh",
    }
    for key,val in state_map.items():
        if key in text: return ("",val)
    return ("","")


def _extract_catalog_entries(raw, catalog):
    text=raw.decode("utf-8","replace")
    entries=[]; seen=set()
    # Keep the parser dependency-free. Official catalog pages commonly expose
    # feed URLs in anchors, data-* attributes, JSON blobs and plain text.
    anchors=re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",text,flags=re.I|re.S)
    candidates=[]
    for href,label_html in anchors:
        label=clean_text(re.sub(r"<[^>]+>"," ",label_html))
        candidates.append((href,label))
    for u in re.findall(r"(?:data-(?:rss|feed|url)|rss(?:Url|URL)|feed(?:Url|URL))\s*=\s*[\"']([^\"']+)[\"']",text,flags=re.I):
        candidates.append((u,""))
    for u in re.findall(r"https?://[^\s\"'<>\\]+(?:rss|feed|\.xml|opml)[^\s\"'<>\\]*",text,flags=re.I):
        candidates.append((u,""))
    for u in re.findall(r"(?:/|\"|')((?:rss|feed|feeds|opml)[^\"'<> ]+\.xml)",text,flags=re.I):
        candidates.append((u,""))
    blocked=("/gallery","/photos","/video","/videos","podcast","horoscope","astrology","shop","sponsored","partner-content","webstories")
    for href,label in candidates:
        url=urllib.parse.urljoin(catalog["url"],html.unescape(href)).strip()
        try: p=urllib.parse.urlsplit(url);
        except Exception: continue
        if p.scheme not in ("http","https") or not p.netloc: continue
        path=p.path.lower()
        if not any(k in path or k in p.query.lower() for k in ("rss","feed",".xml","opml")): continue
        if any(k in (path+" "+label.lower()) for k in blocked): continue
        url=canonical_url(url)
        if url in seen or url==canonical_url(catalog["url"]): continue
        seen.add(url)
        topic=_catalog_topic(label,url); language=_catalog_language(label,url); city,state_name=_catalog_city_state(label,url)
        region="IN" if catalog["provider"] not in {"NDTV","The Indian Express"} or language in INDIA_LANGUAGES or topic in {"India","Local","Finance","Markets","Business","Politics","Entertainment","Sports"} or "india" in (label+url).lower() else ""
        entries.append({"name":f"{catalog['provider']} · {label or p.path.rsplit('/',1)[-1] or 'RSS'}","provider":catalog["provider"],"url":url,"topic":topic,"tier":"publisher","format":"rss","interval_sec":300,"max_items":150,"enabled":True,"language":language,"country":"IN" if region=="IN" else "","region":region,"city":city,"state_name":state_name,"discovered_from":catalog["url"]})
    return entries


def refresh_dynamic_catalogs():
    all_entries=[]; success=0
    for catalog in RSS_CATALOGS:
        try:
            _,raw,_=request_bytes(catalog["url"],timeout=min(8.0,FEED_TIMEOUT+2))
            rows=_extract_catalog_entries(raw,catalog)
            if rows:
                all_entries.extend(rows); success+=1
        except Exception as exc:
            print(f"[Aetheria catalog] {catalog['name']}: {type(exc).__name__}: {str(exc)[:120]}")
    if not all_entries: return 0
    # Prefer category feeds over duplicate catch-all feeds but retain broad coverage.
    uniq={r["url"]:r for r in all_entries}
    ranked=sorted(uniq.values(), key=lambda r:(0 if r.get("language") in INDIA_LANGUAGES else 1,0 if r.get("region")=="IN" else 1,0 if r.get("topic") in {"India","Entertainment","Markets","Business","Local"} else 1,r["name"]))
    rows=ranked[:DYNAMIC_SOURCE_LIMIT]
    DATA_DIR.mkdir(parents=True,exist_ok=True); tmp=DYNAMIC_SOURCES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(DYNAMIC_SOURCES_FILE)
    sync_sources(); FEED_INVALIDATED.set()
    return len(rows)


def catalog_loop():
    # Catalog discovery never blocks HTTP startup. Previously discovered sources stay active if a catalog is down.
    first=True
    while not STOP.is_set():
        try:
            n=refresh_dynamic_catalogs()
            if n: print(f"[Aetheria catalog] discovered {n} RSS feeds",flush=True)
        except Exception as exc:
            print(f"[Aetheria catalog] {type(exc).__name__}: {str(exc)[:160]}")
        first=False
        STOP.wait(DYNAMIC_CATALOG_INTERVAL)


def sync_sources():
    rows=load_source_config(); t=now(); ids=[]
    with DB_LOCK:
        con=db()
        for s in rows:
            sid=stable_id("src",canonical_url(s["url"])); ids.append(sid)
            max_items=s.get("max_items")
            max_items=int(max_items) if isinstance(max_items,(int,float,str)) and str(max_items).strip() else None
            con.execute("""INSERT INTO sources(id,name,provider,url,topic,tier,format,interval_sec,max_items,enabled,language,country,discovered_from,region,city,state_name,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,provider=excluded.provider,topic=excluded.topic,
                tier=excluded.tier,format=excluded.format,interval_sec=excluded.interval_sec,max_items=excluded.max_items,language=excluded.language,country=excluded.country,
                discovered_from=excluded.discovered_from,region=excluded.region,city=excluded.city,state_name=excluded.state_name,enabled=1,updated_at=excluded.updated_at""",
                (sid,s["name"],s.get("provider",s["name"]),canonical_url(s["url"]),s.get("topic","World"),s.get("tier","publisher"),s.get("format","rss"),int(s.get("interval_sec",120)),max_items,1,s.get("language","en"),s.get("country","") or ("IN" if s.get("region")=="IN" else ""),s.get("discovered_from",""),s.get("region",""),s.get("city",""),s.get("state_name",s.get("state","")),t,t))
        if ids:
            marks=",".join("?" for _ in ids); con.execute(f"UPDATE sources SET enabled=0 WHERE id NOT IN ({marks})",ids)
        try:
            con.execute("""UPDATE events SET topic='Legal'
                WHERE (lower(title) LIKE '%court%' OR lower(title) LIKE '%bail%' OR lower(title) LIKE '%verdict%' OR lower(title) LIKE '%judiciary%' OR lower(title) LIKE '%supreme court%' OR lower(title) LIKE '%high court%' OR lower(title) LIKE '%tribunal%' OR lower(title) LIKE '%cbi%' OR lower(title) LIKE '%chargesheet%')
                AND (topic IS NULL OR topic IN ('World','India','Politics','Top'))""")
        except Exception:
            pass
        con.commit(); con.close()


def _header_block(text: str):
    lines=text.replace("\r\n","\n").split("\n"); status=None; hdr={}
    for line in lines:
        if line.startswith("HTTP/"):
            m=re.search(r"\s(\d{3})\s",line); status=int(m.group(1)) if m else status
        elif ":" in line:
            k,v=line.split(":",1); hdr[k.strip().lower()]=v.strip()
    return status,hdr


def request_bytes(url, etag=None, last_modified=None, timeout=8):
    headers={"User-Agent":USER_AGENT,"Accept":"application/rss+xml,application/atom+xml,application/json,application/xml,text/xml,application/geo+json,*/*"}
    if etag: headers["If-None-Match"]=etag
    if last_modified: headers["If-Modified-Since"]=last_modified
    curl=shutil.which("curl") or shutil.which("curl.exe")
    if curl:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="aetheria-hdr-", ignore_cleanup_errors=True) as td:
            hp=str(Path(td)/"headers.txt")
            cmd=[curl,"-sS","-L","--compressed","--connect-timeout",str(CONNECT_TIMEOUT),"--max-time",str(timeout),"-A",USER_AGENT,"-D",hp,"-o","-"]
            for k,v in headers.items(): cmd += ["-H",f"{k}: {v}"]
            cmd.append(url)
            try:
                proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout+1.5,check=False)
            except subprocess.TimeoutExpired:
                raise TimeoutError(f"request deadline exceeded after {timeout:.1f}s")
            if proc.returncode != 0:
                err=proc.stderr.decode("utf-8","replace").strip()[:220]
                raise OSError(err or f"curl exit {proc.returncode}")
            body=proc.stdout
            if len(body)>MAX_RESPONSE_BYTES: raise ValueError("response exceeded configured maximum")
            hs=Path(hp).read_text("iso-8859-1",errors="replace") if Path(hp).exists() else ""
            status,hdr=_header_block(hs); status=status or 200
            if status==304: return 304,b"",hdr
            if status<200 or status>=300: raise OSError(f"HTTP {status}")
            return status,body,hdr
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(MAX_RESPONSE_BYTES+1)
        if len(raw)>MAX_RESPONSE_BYTES: raise ValueError("response exceeded configured maximum")
        return r.status,raw,dict(r.headers)


def source_item_limit(source):
    configured=source.get("max_items")
    if configured is not None:
        try: return max(1,int(configured))
        except Exception: pass
    return MAX_DISCOVERY_ITEMS if source.get("tier")=="discovery" else MAX_ITEMS_PER_SOURCE


def parse_feed(raw: bytes, source):
    if not raw or not raw.strip():
        raise ValueError("empty feed document")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as pe:
        try:
            cleaned = raw.decode("utf-8", errors="replace").strip()
            if "<" in cleaned:
                cleaned = cleaned[cleaned.index("<"):]
            root = ET.fromstring(cleaned.encode("utf-8"))
        except Exception:
            raise ValueError(f"invalid XML: {str(pe)[:140]}")
    except Exception as exc:
        raise ValueError(f"invalid XML: {str(exc)[:140]}")
    out = []; limit = source_item_limit(source)
    nodes=[]
    for node in root.iter():
        tag=node.tag.split("}")[-1].lower()
        if tag in ("item","entry"): nodes.append(node)
    parsed=[]
    for node in nodes:
        tag=node.tag.split("}")[-1].lower()
        if tag not in ("item","entry"): continue
        vals={}; image_url=""
        for child in list(node):
            k=child.tag.split("}")[-1].lower(); href=child.attrib.get("href",""); url_attr=child.attrib.get("url",""); rel=child.attrib.get("rel","")
            media_type=(child.attrib.get("type") or "").lower(); medium=(child.attrib.get("medium") or "").lower()
            text=clean_text(child.text); value=text or href or url_attr
            if k in ("title","description","summary","guid","id","pubdate","published","updated","date","language","country"): vals[k]=value
            elif k=="link":
                if rel in ("","alternate") or "link" not in vals: vals["link"]=href or value
                if (rel=="enclosure" or medium=="image" or media_type.startswith("image/")) and (href or url_attr):
                    image_url=image_url or url_attr or href
            elif k in ("enclosure","thumbnail","media"):
                if url_attr or href:
                    image_url=image_url or url_attr or href
            elif k in ("content","encoded") and value:
                # media:content may be a real image URL; otherwise retain it as article description.
                if (medium=="image" or media_type.startswith("image/")) and (url_attr or href):
                    image_url=image_url or url_attr or href
                else:
                    vals.setdefault("description",value)
            for sub in list(child):
                sk=sub.tag.split("}")[-1].lower(); su=sub.attrib.get("url","") or sub.attrib.get("href","")
                sm=(sub.attrib.get("type") or "").lower(); smed=(sub.attrib.get("medium") or "").lower()
                if su and ("image" in sk or sk in ("thumbnail","content") or sm.startswith("image/") or smed=="image"): image_url=image_url or su
        title=vals.get("title",""); link=canonical_url(vals.get("link","") or vals.get("guid","") or vals.get("id","") )
        if not title or not link or urllib.parse.urlsplit(link).scheme not in ("http","https"): continue
        pub=vals.get("pubdate") or vals.get("published") or vals.get("updated") or vals.get("date")
        parsed.append({"title":title,"url":link,"description":vals.get("description") or "","published":parse_date(pub),"language":vals.get("language") or source.get("language") or "en","country":vals.get("country") or source.get("country") or ("IN" if source.get("region")=="IN" else ""),"topic":infer_topic(title,source.get("topic","World")),"domain":urllib.parse.urlsplit(link).netloc.lower(),"tier":source.get("tier","publisher"),"source_id":source["id"],"image_url":canonical_url(image_url) if image_url else ""})
    parsed.sort(key=lambda x: (x.get("published") is not None, x.get("published") or 0), reverse=True)
    return parsed[:limit]



def _ics_unfold(raw: bytes):
    text=raw.decode("utf-8","replace").replace("\r\n","\n").replace("\r","\n")
    lines=text.split("\n"); out=[]
    for line in lines:
        if line.startswith((" ","\t")) and out: out[-1]+=line[1:]
        else: out.append(line)
    return out


def parse_ics_datetime(value, params=""):
    value=value.strip(); tz=None
    m=re.search(r"TZID=([^;:]+)",params,re.I)
    if m:
        try: tz=ZoneInfo(m.group(1))
        except Exception: tz=None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp(),True
        if "T" in value:
            fmt="%Y%m%dT%H%M%S" if len(value)>=15 else "%Y%m%dT%H%M"
            dt=datetime.strptime(value[:len("20261002T083000") if len(value)>=15 else len("20261002T0830")],fmt).replace(tzinfo=tz or timezone.utc)
            return dt.timestamp(),True
        return datetime.strptime(value[:8],"%Y%m%d").replace(tzinfo=tz or timezone.utc).timestamp(),False
    except Exception:
        return None,False


def schedule_import(source, rows):
    sid=source["id"]; cutoff=now()-7*86400; fresh=[]
    for r in rows:
        start=r.get("start_ts")
        if not start or start<cutoff: continue
        title=clean_text(r.get("title") or "Scheduled event")[:240]
        category=r.get("category") or source.get("topic","World")
        kind=r.get("kind") or "scheduled"
        importance=max(.05,min(.99,float(r.get("importance",.5))))
        eid=stable_id("sch",f"{sid}|{title}|{int(start)}")
        fresh.append({"id":eid,"source_id":sid,"title":title,"category":category,"kind":kind,
                      "start_ts":start,"end_ts":r.get("end_ts"),"time_known":int(bool(r.get("time_known",True))),
                      "url":safe_url(r.get("url") or source.get("url","")),
                      "description":clean_text(r.get("description") or "")[:500],
                      "importance":importance,"updated_at":now()})
    try:
        with DB_LOCK:
            con=db()
            con.execute("DELETE FROM schedules WHERE source_id=?",(sid,))
            if fresh:
                con.executemany(
                    """INSERT OR REPLACE INTO schedules
                    (id,source_id,title,category,kind,start_ts,end_ts,time_known,url,description,importance,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [tuple(x[k] for k in ("id","source_id","title","category","kind","start_ts","end_ts",
                                          "time_known","url","description","importance","updated_at")) for x in fresh])
            con.commit(); con.close()
    except Exception:
        return 0
    with FUTURE_CACHE_LOCK:
        FUTURE_CACHE["at"]=0.0; FUTURE_CACHE["value"]=[]
    return len(fresh)


def parse_ics(raw, source):
    rows=[]; cur=None
    for line in _ics_unfold(raw):
        if line.strip()=="BEGIN:VEVENT": cur={}; continue
        if line.strip()=="END:VEVENT":
            if cur and cur.get("start_ts") and cur.get("title"):
                title=cur["title"].lower(); imp=.55
                if any(k in title for k in ("cpi","employment","inflation","jobs","productivity","interest","rate","gdp","retail sales")):
                    imp=.78
                rows.append({**cur,"category":source.get("topic","Economy"),"kind":"economic_release","importance":imp})
            cur=None; continue
        if cur is None or ":" not in line: continue
        left,val=line.split(":",1); key=left.split(";",1)[0].upper(); params=left[len(key):]
        if key in ("DTSTART","DTEND"):
            ts,known=parse_ics_datetime(val,params); cur["start_ts" if key=="DTSTART" else "end_ts"]=ts
            if key=="DTSTART": cur["time_known"]=known
        elif key in ("SUMMARY","DESCRIPTION","URL"):
            cur[{"SUMMARY":"title","DESCRIPTION":"description","URL":"url"}[key]]=val.replace("\\n"," ")
    return rows


def parse_fomc_html(raw, source):
    text=html.unescape(raw.decode("utf-8","replace"))
    text=re.sub(r"<script.*?</script>|<style.*?</style>"," ",text,flags=re.I|re.S)
    text=re.sub(r"<[^>]+>"," ",text); text=re.sub(r"\s+"," ",text)
    months={m:i for i,m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"],1)}
    rows=[]; current_year=datetime.now().year
    sections=list(re.finditer(r"(20\d{2}) FOMC Meetings",text))
    for ix,m in enumerate(sections):
        year=int(m.group(1))
        if year<current_year: continue
        sec=text[m.end():(sections[ix+1].start() if ix+1<len(sections) else len(text))]
        for mm,mi in months.items():
            mmatch=re.search(rf"\b{mm}\s+(\d{{1,2}})(?:-(\d{{1,2}}))?(\*)?",sec)
            if not mmatch: continue
            day=int(mmatch.group(1)); day2=int(mmatch.group(2) or day)
            try:
                start=datetime(year,mi,day,12,0,tzinfo=timezone.utc).timestamp()
                finish=datetime(year,mi,day2,12,0,tzinfo=timezone.utc).timestamp()
            except ValueError: continue
            if start<now()-86400: continue
            rows.append({"title":f"Federal Reserve FOMC meeting — {mm} {day}{('-'+str(day2)) if day2!=day else ''}, {year}",
                         "start_ts":start,"end_ts":finish,"time_known":False,"category":"Markets","kind":"policy_meeting",
                         "importance":.88,"url":source.get("url"),"description":"Official FOMC meeting dates; meeting times are not specified in the calendar."})
    return rows


def parse_schedule(raw, source):
    fmt=source.get("format")
    if fmt=="ics": return parse_ics(raw,source)
    if fmt=="fomc_html": return parse_fomc_html(raw,source)
    return []


def classify_error(err_str: str) -> tuple[str, int]:
    err = (err_str or "").lower()
    if "429" in err or "rate" in err or "too many requests" in err:
        return "RATE_LIMITED", 429
    if "404" in err or "not found" in err:
        return "NOT_FOUND", 404
    if "timeout" in err or "timed out" in err or "deadline" in err:
        return "TIMEOUT", 408
    if "dns" in err or "name or service not known" in err or "could not resolve host" in err:
        return "DNS_ERROR", 502
    if "xml" in err or "element" in err or "parse" in err or "not well-formed" in err:
        return "INVALID_FEED", 422
    if any(code in err for code in ("500", "502", "503", "504")):
        return "UNAVAILABLE", 500
    return "DEGRADED", 500


def set_source_state(sid,state,error=None,started=None):
    with DB_LOCK:
        con=db(); con.execute("UPDATE sources SET state=?,last_attempt=?,last_error=?,updated_at=? WHERE id=?",(state,started or now(),error,now(),sid)); con.commit(); con.close()


def fetch_source(source):
    sid=source["id"]; started=now(); set_source_state(sid,"fetching",None,started)
    url=source["url"]
    if url.startswith("https://api.gdeltproject.org/"):
        url=url.replace("https://api.gdeltproject.org/", "http://api.gdeltproject.org/")
    try:
        timeout=GDELT_TIMEOUT if str(source.get("provider","")).lower()=="gdelt" else FEED_TIMEOUT
        status,raw,headers=request_bytes(url,source.get("etag"),source.get("last_modified"),timeout)
        duration=int((now()-started)*1000)
        if status==304:
            with DB_LOCK:
                con=db(); con.execute("UPDATE sources SET state='online',last_success=?,last_duration_ms=?,failures=0,consecutive_failures=0,last_error=NULL,last_http_status=304,error_class='',next_attempt_at=0,updated_at=? WHERE id=?",(now(),duration,now(),sid)); con.commit(); con.close()
            return [],{"id":sid,"name":source["name"],"ok":True,"not_modified":True,"items":0,"ms":duration,"tier":source.get("tier","publisher")}
        if source.get("format") in ("ics","fomc_html"):
            count=schedule_import(source,parse_schedule(raw,source)); duration=int((now()-started)*1000)
            with DB_LOCK:
                con=db(); con.execute("UPDATE sources SET etag=?,last_modified=?,last_success=?,failures=0,consecutive_failures=0,fetched=fetched+1,items=items+?,state='online',last_duration_ms=?,last_error=NULL,last_http_status=200,error_class='',next_attempt_at=0,updated_at=? WHERE id=?",(headers.get("etag") if isinstance(headers,dict) else None,headers.get("last-modified") if isinstance(headers,dict) else None,now(),count,duration,now(),sid)); con.commit(); con.close()
            return [],{"id":sid,"name":source["name"],"ok":True,"items":count,"schedules":count,"ms":duration,"tier":"official"}
        if source.get("format")=="geojson":
            data=json.loads(raw.decode("utf-8",errors="replace")); items=[]
            for f in data.get("features",[])[:MAX_ITEMS_PER_SOURCE]:
                p=f.get("properties",{}); detail=p.get("detail") or p.get("url") or "https://earthquake.usgs.gov/earthquakes/"
                items.append({"title":clean_text(p.get("title","Earthquake")),"url":canonical_url(detail),"description":clean_text(p.get("place","")),"published":parse_date(p.get("time")),"language":"en","country":"","topic":"Weather","domain":source.get("provider",source["name"]),"tier":source.get("tier","official"),"source_id":sid,"image_url":""})
        else:
            items=parse_feed(raw,source)
        hdr={k.lower():v for k,v in headers.items()}; duration=int((now()-started)*1000)
        with DB_LOCK:
            con=db(); con.execute("UPDATE sources SET etag=?,last_modified=?,last_success=?,failures=0,consecutive_failures=0,fetched=fetched+1,items=items+?,state='online',last_duration_ms=?,last_error=NULL,last_http_status=200,error_class='',next_attempt_at=0,updated_at=? WHERE id=?",(hdr.get("etag"),hdr.get("last-modified"),now(),len(items),duration,now(),sid)); con.commit(); con.close()
        return items,{"id":sid,"name":source["name"],"ok":True,"items":len(items),"ms":duration,"tier":source.get("tier","publisher")}
    except Exception as exc:
        duration=int((now()-started)*1000); err=str(exc)[:240]
        error_class, http_status = classify_error(err)
        base_interval = max(45, int(source.get("interval_sec") or 120))
        prev_failures = int(source.get("consecutive_failures") or source.get("failures") or 0) + 1
        if error_class == "RATE_LIMITED":
            backoff_delay = max(300, base_interval * 3)
        elif error_class == "NOT_FOUND":
            backoff_delay = max(600, base_interval * 4)
        elif error_class == "DNS_ERROR":
            backoff_delay = max(180, base_interval * 2)
        else:
            mult = min(16, 2 ** min(prev_failures, 4))
            backoff_delay = base_interval * mult
        next_attempt_at = now() + backoff_delay
        with DB_LOCK:
            con=db(); con.execute("UPDATE sources SET state='error',last_failure=?,failures=failures+1,consecutive_failures=COALESCE(consecutive_failures,0)+1,last_duration_ms=?,last_error=?,last_http_status=?,error_class=?,next_attempt_at=?,updated_at=? WHERE id=?",(now(),duration,err,http_status,error_class,next_attempt_at,now(),sid)); con.commit(); con.close()
        return [],{"id":sid,"name":source["name"],"ok":False,"items":0,"ms":duration,"tier":source.get("tier","publisher"),"error":err,"error_class":error_class}


def _refresh_fts_for_event(con,event_id):
    if getattr(con, "is_postgres", False):
        return
    try:
        e=con.execute("SELECT id,title,summary,topic,entities,locations FROM events WHERE id=?",(event_id,)).fetchone()
        if not e: return
        rows=con.execute("SELECT a.title,a.domain FROM event_articles ea JOIN articles a ON a.id=ea.article_id WHERE ea.event_id=?",(event_id,)).fetchall()
        domains=" ".join(r["domain"] or "" for r in rows); article_titles=" | ".join(r["title"] or "" for r in rows)
        con.execute("DELETE FROM event_fts WHERE event_id=?",(event_id,))
        con.execute("INSERT INTO event_fts(event_id,title,summary,topic,entities,locations,domains,article_titles) VALUES(?,?,?,?,?,?,?,?)",(event_id,e["title"],e["summary"] or "",e["topic"] or "",e["entities"] or "",e["locations"] or "",domains,article_titles))
    except Exception:
        pass


def article_upsert(items):
    fresh=[]
    with DB_LOCK:
        con=db()
        for a in items:
            url=a.get("url"); title=clean_text(a.get("title"))
            if not url or not title or not url.startswith(("http://","https://")): continue
            aid=stable_id("art",url); fp=fingerprint(title,a.get("domain",""))
            ex=con.execute("SELECT id FROM articles WHERE canonical_url=?",(url,)).fetchone()
            if ex:
                con.execute("UPDATE articles SET title=?,description=?,published=COALESCE(?,published),topic=?,tier=?,domain=?,image_url=COALESCE(NULLIF(?,''),image_url) WHERE id=?",(title,a.get("description",""),a.get("published"),a.get("topic","World"),a.get("tier","publisher"),a.get("domain",""),a.get("image_url","") or "",ex[0])); continue
            con.execute("INSERT INTO articles(id,source_id,canonical_url,title,description,published,fetched,language,country,topic,tier,domain,fingerprint,image_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,a.get("source_id"),url,title,a.get("description",""),a.get("published"),now(),a.get("language",""),a.get("country",""),a.get("topic","World"),a.get("tier","publisher"),a.get("domain",""),fp,a.get("image_url","") or ""))
            fresh.append((aid,a))
        con.commit(); con.close()
    return fresh


def refresh_event_index(force=False):
    global EVENT_INDEX, EVENT_POSTINGS, EVENT_ENTITY_POSTINGS, EVENT_INDEX_LAST_REFRESH
    if not force and now()-EVENT_INDEX_LAST_REFRESH < EVENT_INDEX_MIN_REFRESH:
        return
    try:
        con=db_read()
        rows=con.execute("""SELECT e.id,e.title,e.topic,e.last_seen,e.entities,
            COALESCE((SELECT GROUP_CONCAT(a.title,' | ') FROM event_articles ea2 JOIN articles a ON a.id=ea2.article_id WHERE ea2.event_id=e.id),'') article_titles,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT a.source_id) FROM event_articles ea3 JOIN articles a ON a.id=ea3.article_id WHERE ea3.event_id=e.id),'') source_ids,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT a.domain) FROM event_articles ea4 JOIN articles a ON a.id=ea4.article_id WHERE ea4.event_id=e.id),'') domains
          FROM events e WHERE e.last_seen>? AND length(trim(e.title))>=8
          ORDER BY e.last_seen DESC LIMIT ?""",(now()-EVENT_ACTIVE_HOURS*3600,EVENT_INDEX_LIMIT)).fetchall()
        con.close()
    except Exception:
        rows=[]
    idx=[]
    for r in rows:
        try: ents=set(json.loads(r["entities"] or "[]"))
        except Exception: ents=set()
        sig_texts=[x.strip() for x in (r["article_titles"] or "").split(" | ") if x.strip()][-8:]
        if not sig_texts: sig_texts=[r["title"] or ""]
        sig_sets=[content_tokens(x) for x in sig_texts if x]
        union=set().union(*(sig_sets or [set()]))
        union.update(content_tokens(r["title"] or ""))
        source_ids={x for x in (r["source_ids"] or "").split(",") if x}
        domains={x for x in (r["domains"] or "").split(",") if x}
        idx.append({"id":r["id"],"title":r["title"],"topic":r["topic"],"last_seen":r["last_seen"],"tokens":union,"tokens_content":union,"signatures":sig_sets,"entities":ents,"source_ids":source_ids,"domains":domains})
    postings,entity_postings=build_postings(idx)
    with EVENT_INDEX_LOCK:
        EVENT_INDEX=idx; EVENT_POSTINGS=postings; EVENT_ENTITY_POSTINGS=entity_postings
    EVENT_INDEX_LAST_REFRESH=now()


def _weighted_jaccard(a:set[str], b:set[str], df:dict[str,int], n:int) -> float:
    if not a or not b: return 0.0
    def w(token):
        return 1.0 + math.log((n+1)/max(1,df.get(token,0)+1))
    inter=a & b; union=a | b
    return sum(w(t) for t in inter)/max(1e-9,sum(w(t) for t in union))

def _event_term_stats(index_rows):
    df=Counter()
    for e in index_rows:
        for t in (e.get("tokens_content") or e.get("tokens") or set()): df[t]+=1
    return df,max(1,len(index_rows))

def _score_event_candidate(article, e, df=None, n=None):
    at=content_tokens(article["title"]+" "+article.get("description", ""))
    ents=set(extract_entities(article["title"]))
    topic=article.get("topic")
    et=e.get("tokens_content") or e.get("tokens") or content_tokens(e.get("title", ""))
    if df is None or n is None: df,n=_event_term_stats([e])
    article_time=article.get("published") or now(); event_time=e.get("last_seen") or now()
    hours=abs(article_time-event_time)/3600
    if topic and e.get("topic") not in (topic,"World") and hours>8: return None
    sig_sets=e.get("signatures") or [et]
    sim=max((_weighted_jaccard(at,s,df,n) for s in sig_sets if s),default=0.0)
    entity_overlap=bool(ents & (e.get("entities") or set()))
    shared=len(at & et)
    exact=norm_title(article["title"]) and norm_title(article["title"])==norm_title(e.get("title", ""))
    same_source=bool(article.get("source_id") and article.get("source_id") in (e.get("source_ids") or set()))
    if exact: return 1.0
    shared_entities=ents & (e.get("entities") or set())
    entity_count=len(shared_entities)
    # If both sides carry numbered/alphanumeric named anchors, do not let a
    # common brand/topic word merge otherwise distinct variants.
    article_anchors=numeric_entity_anchors(ents)
    event_anchors=numeric_entity_anchors(e.get("entities") or set())
    if article_anchors and event_anchors and not (article_anchors & event_anchors):
        return None
    article_numbers=numeric_title_anchors(article["title"])
    event_numbers=numeric_title_anchors(e.get("title", ""))
    if article_numbers and event_numbers and not (article_numbers & event_numbers):
        return None
    entity_bonus=0.25 if entity_overlap else 0
    time_bonus=0.08 if hours<12 else 0.03 if hours<30 else 0
    topic_bonus=0.03 if topic and topic==e.get("topic") else 0
    score=sim*.64+entity_bonus+time_bonus+topic_bonus
    if entity_overlap and hours<12: score+=0.05
    if shared<2 and not (entity_overlap and hours<18): return None
    if same_source:
        if not entity_overlap and sim<0.72: return None
        if entity_overlap and sim<0.58: return None
    elif not entity_overlap and hours>18:
        return None
    # One shared named entity (for example a major public figure) is not enough
    # to merge two stories; the wording must also be materially similar. Exact
    # numbered/alphanumeric anchors are stronger identity evidence and allow
    # paraphrased cross-source reports to converge without collapsing variants.
    numeric_anchor_match=bool(article_anchors and event_anchors and (article_anchors & event_anchors))
    if entity_count==1 and sim<0.60 and not numeric_anchor_match: return None
    threshold=0.43 if numeric_anchor_match and hours<18 else 0.45 if (entity_count>=2 and hours<12) else 0.58 if (entity_overlap and hours<12) else 0.62
    if score<threshold: return None
    return score


def _candidate_events_from_index(article,index_rows,df=None,n=None,postings=None,entity_postings=None,by_id=None):
    if df is None or n is None: df,n=_event_term_stats(index_rows)
    if postings is None or entity_postings is None:
        postings,entity_postings=build_postings(index_rows)
    at=content_tokens(article["title"]+" "+article.get("description", "")); ents=set(extract_entities(article["title"]))
    by_id=by_id or {e["id"]:e for e in index_rows}; ids=set()
    max_df=max(CLUSTER_MIN_RARE_DF,int(n*CLUSTER_MAX_DF_RATIO))
    rare_tokens=[tok for tok in at if df.get(tok,0)<=max_df]
    ranked_tokens=sorted(rare_tokens,key=lambda tok:(df.get(tok,0), -len(tok), tok))[:max(1,CLUSTER_CANDIDATE_TOKEN_LIMIT)]
    for tok in ranked_tokens: ids.update(postings.get(tok,()))
    for ent in ents: ids.update(entity_postings.get(str(ent).lower(),()))
    candidates=[]
    for eid in ids:
        e=by_id.get(eid)
        if not e: continue
        score=_score_event_candidate(article,e,df,n)
        if score is not None: candidates.append((score,eid))
    candidates.sort(reverse=True)
    return candidates[:4]


def get_candidate_events(article):
    with EVENT_INDEX_LOCK:
        idx=list(EVENT_INDEX); postings=dict(EVENT_POSTINGS); entity_postings=dict(EVENT_ENTITY_POSTINGS)
        postings={k:set(v) for k,v in postings.items()}; entity_postings={k:set(v) for k,v in entity_postings.items()}
    df,n=_event_term_stats(idx)
    return _candidate_events_from_index(article,idx,df,n,postings,entity_postings)


def recalc_event(event_id):
    with DB_LOCK:
        con=db(); e=con.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone();
        if not e: con.close(); return
        rows=con.execute("SELECT a.*,s.reliability FROM event_articles ea JOIN articles a ON a.id=ea.article_id LEFT JOIN sources s ON s.id=a.source_id WHERE ea.event_id=? ORDER BY COALESCE(a.published,a.fetched) DESC",(event_id,)).fetchall()
        unique={r["source_id"] for r in rows}; official=sum(r["tier"]=="official" for r in rows); publisher=sum(r["tier"]=="publisher" for r in rows); discovery=sum(r["tier"]=="discovery" for r in rows)
        t=now(); recent=[r for r in rows if r["published"] and r["published"]>t-6*3600]
        elapsed=max(.25,(t-(e["first_seen"] or t))/3600); velocity=min(1.0,len(recent)/elapsed)
        corroboration=min(1.0,max(0,len(unique)-1)/4); authority=min(1.0,official*.35+publisher*.08+discovery*.02)
        urgency=min(1.0,sum(1 for r in rows[:20] if tokens(r["title"])&URGENT)/4)
        novelty=1.0 if t-(e["first_seen"] or t)<2*3600 else max(.05,1-(t-(e["first_seen"] or t))/86400)
        title=e["title"].lower(); tt=tokens(title)
        india_title=1.0 if (tt & TOPIC_TERMS["India"]) or any(x in title for x in ("india","indian","delhi","mumbai","rupee")) else 0.0
        india_source=max([1.0 if str(r["country"] or "").upper()=="IN" else 0.0 for r in rows] or [0.0])
        india_lang=max([0.75 if str(r["language"] or "").lower() in {"hi","bn","mr","ta","te","kn","ml","gu","pa"} else 0.0 for r in rows] or [0.0])
        india=max(india_title, india_source, india_lang)
        financial=1.0 if tt&TOPIC_TERMS["Markets"] or tt&TOPIC_TERMS["Business"] or tt&TOPIC_TERMS["Finance"] else 0.0
        supply=1.0 if tt&set("shipping port freight oil gas grain wheat maize rice fertilizer supply chain export import semiconductor".split()) else 0.0
        geo=1.0 if tt&TOPIC_TERMS["Geopolitics"] else 0.0
        social=1.0 if tt&set("protest migration jobs election education public safety social crime".split()) else 0.0
        significance=min(1.0,velocity*.20+corroboration*.20+authority*.17+urgency*.18+novelty*.10+max(india,financial,supply,geo,social)*.15)
        if official>0 and len(unique)>=2: status="CONFIRMED"
        elif len(unique)>=2: status="DEVELOPING"
        elif discovery>0: status="UNVERIFIED"
        else: status="NEW"
        if e["status"]=="CONFIRMED" and status!="CONFIRMED": status="CONFIRMED"
        reason=f"{len(unique)} independent source(s); {official} official; corroboration {corroboration:.2f}"
        con.execute("UPDATE events SET status=?,velocity=?,novelty=?,corroboration=?,authority=?,urgency=?,significance=?,india_relevance=?,financial_relevance=?,supply_chain_relevance=?,geopolitical_relevance=?,social_relevance=?,article_count=?,source_count=?,official_count=?,publisher_count=?,discovery_count=?,last_reason=?,updated_at=? WHERE id=?",(status,velocity,novelty,corroboration,authority,urgency,significance,india,financial,supply,geo,social,len(rows),len(unique),official,publisher,discovery,reason,t,event_id))
        _refresh_fts_for_event(con,event_id)
        con.commit(); con.close()




def _recalc_event_con(con,event_id,t=None):
    e=con.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
    if not e: return
    rows=con.execute("SELECT a.*,s.reliability FROM event_articles ea JOIN articles a ON a.id=ea.article_id LEFT JOIN sources s ON s.id=a.source_id WHERE ea.event_id=? ORDER BY COALESCE(a.published,a.fetched) DESC",(event_id,)).fetchall()
    unique={r["source_id"] for r in rows}; official=sum(r["tier"]=="official" for r in rows); publisher=sum(r["tier"]=="publisher" for r in rows); discovery=sum(r["tier"]=="discovery" for r in rows)
    t=t or now(); recent=[r for r in rows if r["published"] and r["published"]>t-6*3600]
    elapsed=max(.25,(t-(e["first_seen"] or t))/3600); velocity=min(1.0,len(recent)/elapsed)
    corroboration=min(1.0,max(0,len(unique)-1)/4); authority=min(1.0,official*.35+publisher*.08+discovery*.02)
    urgency=min(1.0,sum(1 for r in rows[:20] if tokens(r["title"])&URGENT)/4)
    novelty=1.0 if t-(e["first_seen"] or t)<2*3600 else max(.05,1-(t-(e["first_seen"] or t))/86400)
    title=e["title"].lower(); tt=tokens(title)
    india_title=1.0 if (tt & TOPIC_TERMS["India"]) or any(x in title for x in ("india","indian","delhi","mumbai","rupee")) else 0.0
    india_source=max([1.0 if str(r["country"] or "").upper()=="IN" else 0.0 for r in rows] or [0.0])
    india_lang=max([0.75 if str(r["language"] or "").lower() in {"hi","bn","mr","ta","te","kn","ml","gu","pa"} else 0.0 for r in rows] or [0.0])
    india=max(india_title, india_source, india_lang)
    financial=1.0 if tt&TOPIC_TERMS["Markets"] or tt&TOPIC_TERMS["Business"] or tt&TOPIC_TERMS["Finance"] else 0.0
    supply=1.0 if tt&set("shipping port freight oil gas grain wheat maize rice fertilizer supply chain export import semiconductor".split()) else 0.0
    geo=1.0 if tt&TOPIC_TERMS["Geopolitics"] else 0.0
    social=1.0 if tt&set("protest migration jobs election education public safety social crime".split()) else 0.0
    significance=min(1.0,velocity*.20+corroboration*.20+authority*.17+urgency*.18+novelty*.10+max(india,financial,supply,geo,social)*.15)
    conflicts=_conflict_pairs(rows)
    if conflicts: status="DISPUTED"
    elif official>0 and len(unique)>=2: status="CONFIRMED"
    elif len(unique)>=2: status="DEVELOPING"
    elif discovery>0: status="UNVERIFIED"
    else: status="NEW"
    if e["status"]=="CONFIRMED" and not conflicts and status!="CONFIRMED": status="CONFIRMED"
    reason=f"{len(unique)} independent source(s); {official} official; corroboration {corroboration:.2f}" + (f"; {len(conflicts)} conflicting signal(s)" if conflicts else "")
    con.execute("UPDATE events SET status=?,velocity=?,novelty=?,corroboration=?,authority=?,urgency=?,significance=?,india_relevance=?,financial_relevance=?,supply_chain_relevance=?,geopolitical_relevance=?,social_relevance=?,article_count=?,source_count=?,official_count=?,publisher_count=?,discovery_count=?,last_reason=?,updated_at=? WHERE id=?",(status,velocity,novelty,corroboration,authority,urgency,significance,india,financial,supply,geo,social,len(rows),len(unique),official,publisher,discovery,reason,t,event_id))
    _refresh_fts_for_event(con,event_id)


def link_article(aid,a):
    # Compatibility path; bulk ingestion below is preferred.
    if not aid: return None
    with DB_LOCK:
        con=db()
        idx_rows=con.execute("SELECT id,title,topic,last_seen,entities FROM events WHERE last_seen>? ORDER BY last_seen DESC LIMIT ?",(now()-EVENT_ACTIVE_HOURS*3600,EVENT_INDEX_LIMIT)).fetchall()
        idx=[]
        for r in idx_rows:
            try: ents=set(json.loads(r["entities"] or "[]"))
            except Exception: ents=set()
            idx.append({"id":r["id"],"title":r["title"],"topic":r["topic"],"last_seen":r["last_seen"],"tokens":content_tokens(r["title"]),"tokens_content":content_tokens(r["title"]),"signatures":[content_tokens(r["title"])],"entities":ents,"source_ids":set(),"domains":set()})
        df,n=_event_term_stats(idx)
        cands=_candidate_events_from_index(a,idx,df,n)
        if cands: event_id=cands[0][1]; change="UPDATE"
        else:
            event_id=stable_id("evt",a["url"]+"|"+str(int((a.get("published") or now())/3600))); change="NEW"
            ents=extract_entities(a["title"]); tpc=a.get("topic","World"); t=a.get("published") or now()
            con.execute("INSERT OR IGNORE INTO events(id,title,topic,status,first_seen,last_seen,last_change,primary_article_id,entities,locations,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(event_id,a["title"],tpc,"NEW",t,t,now(),aid,json.dumps(ents),json.dumps(ents),now(),now()))
        if not con.execute("SELECT 1 FROM event_articles WHERE event_id=? AND article_id=?",(event_id,aid)).fetchone():
            con.execute("INSERT INTO event_articles(event_id,article_id,first_linked) VALUES(?,?,?)",(event_id,aid,now()))
            con.execute("INSERT INTO event_updates(event_id,article_id,observed_at,change_type,note) VALUES(?,?,?,?,?)",(event_id,aid,now(),change,a["title"][:240]))
            con.execute("UPDATE events SET last_seen=?,last_change=?,primary_article_id=COALESCE(primary_article_id,?) WHERE id=?",(a.get("published") or now(),now(),aid,event_id))
        _recalc_event_con(con,event_id)
        con.commit(); con.close()
    refresh_event_index()
    return event_id


def ingest(items):
    if not items: return 0
    fresh=article_upsert(items)
    if not fresh: return 0
    affected=set(); t=now()
    # Take the current index once, then grow it as new events are created in this batch.
    with EVENT_INDEX_LOCK:
        local_index=[dict(x) for x in EVENT_INDEX]
    local_postings, local_entity_postings=build_postings(local_index)
    local_by_id={e["id"]:e for e in local_index}
    df,n=_event_term_stats(local_index)
    with DB_LOCK:
        con=db()
        for aid,a in fresh:
            cands=_candidate_events_from_index(a,local_index,df,n,local_postings,local_entity_postings,local_by_id)
            article_terms=content_tokens(a["title"]+" "+a.get("description", ""))
            pub_ts = a.get("published")
            # CRITICAL FIX: last_seen must represent WHEN WE FETCHED this information,
            # not when the article was originally published. Using pub_ts for last_seen
            # caused old re-fetched articles to inflate event freshness. t is the
            # current ingest time — this is the real "we observed new info" timestamp.
            # We still use pub_ts for first_seen (when the event started) and for
            # sorting within the latest lane (article_pub in meta).
            art_seen = t  # always use current ingest time for last_seen
            if cands:
                event_id=cands[0][1]; change="UPDATE"
                # Let the in-batch event representation evolve so subsequent
                # matching uses newly observed vocabulary without a DB reread.
                ev=local_by_id.get(event_id)
                if ev is not None:
                    ev["last_seen"]=max(float(ev.get("last_seen") or 0), art_seen)
                    before=set(ev.get("tokens_content") or ev.get("tokens") or set())
                    ev.setdefault("tokens_content",set()).update(article_terms)
                    ev.setdefault("tokens",set()).update(article_terms)
                    ev.setdefault("signatures",[]).append(set(article_terms)); ev["signatures"]=ev["signatures"][-8:]
                    new_entities=extract_entities(a["title"])
                    ev.setdefault("entities",set()).update(new_entities)
                    ev.setdefault("source_ids",set()).add(a.get("source_id",""))
                    for tok in set(ev["tokens_content"]) - before: df[tok]=df.get(tok,0)+1
                    for tok in article_terms: local_postings.setdefault(tok,set()).add(event_id)
                    for ent in new_entities: local_entity_postings.setdefault(str(ent).lower(),set()).add(event_id)
            else:
                event_id=stable_id("evt",a["url"]+"|"+str(int((pub_ts or t)/3600))); change="NEW"
                ents=extract_entities(a["title"]); tpc=a.get("topic","World"); first_seen_ts=pub_ts or t
                con.execute("""INSERT INTO events(id,title,topic,status,first_seen,last_seen,last_change,primary_article_id,entities,locations,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=MAX(events.last_seen, excluded.last_seen), last_change=excluded.last_change, updated_at=excluded.updated_at""",
                    (event_id,a["title"],tpc,"NEW",first_seen_ts,art_seen,t,aid,json.dumps(ents),json.dumps(ents),t,t))
                new_ev={"id":event_id,"title":a["title"],"topic":tpc,"last_seen":art_seen,"tokens":set(article_terms),"tokens_content":set(article_terms),"signatures":[set(article_terms)],"entities":set(ents),"source_ids":{a.get("source_id","")},"domains":{a.get("domain","")}}
                local_index.append(new_ev); local_by_id[event_id]=new_ev
                for tok in article_terms: df[tok]=df.get(tok,0)+1; local_postings.setdefault(tok,set()).add(event_id)
                for ent in ents: local_entity_postings.setdefault(str(ent).lower(),set()).add(event_id)
                n += 1
            if not con.execute("SELECT 1 FROM event_articles WHERE event_id=? AND article_id=?",(event_id,aid)).fetchone():
                con.execute("INSERT INTO event_articles(event_id,article_id,first_linked) VALUES(?,?,?)",(event_id,aid,t))
                con.execute("INSERT INTO event_updates(event_id,article_id,observed_at,change_type,note) VALUES(?,?,?,?,?)",(event_id,aid,t,change,a["title"][:240]))
                # Update last_seen to current time (we just got fresh info), primary_article_id is the founding article.
                # Also update latest_article_id if this article's pub_ts is newer than the stored one.
                con.execute("UPDATE events SET last_seen=MAX(last_seen, ?),last_change=?,primary_article_id=COALESCE(primary_article_id,?),latest_article_id=CASE WHEN COALESCE(latest_article_pub,0)<? THEN ? ELSE latest_article_id END,latest_article_pub=CASE WHEN COALESCE(latest_article_pub,0)<? THEN ? ELSE latest_article_pub END WHERE id=?",
                    (art_seen,t,aid,pub_ts or 0,aid,pub_ts or 0,pub_ts or 0,event_id))
            affected.add(event_id)
        for eid in affected: _recalc_event_con(con,eid,t)
        con.execute("INSERT OR REPLACE INTO system_metrics(key,value,updated_at) VALUES('last_ingest',?,?)",(str(t),t))
        con.commit(); con.close()
    FEED_INVALIDATED.set(); refresh_event_index()
    return len(affected)


def _session_learning(con,session):
    if not session: return {}
    rows=con.execute("SELECT action,COUNT(*) n FROM telemetry WHERE session=? AND at>? GROUP BY action",(session,now()-30*86400)).fetchall()
    return {r[0]:int(r[1]) for r in rows}


def queue_telemetry(data):
    with TELEMETRY_LOCK: TELEMETRY_QUEUE.append(data)


def flush_telemetry():
    with TELEMETRY_LOCK:
        if not TELEMETRY_QUEUE: return
        rows=list(TELEMETRY_QUEUE); TELEMETRY_QUEUE.clear()
    with DB_LOCK:
        con=db(); con.executemany("INSERT INTO telemetry(event_id,action,value,at,session) VALUES(?,?,?,?,?)",[(x.get("event_id"),x.get("action"),float(x.get("value",1)),float(x.get("at",now())),str(x.get("session", ""))[:100]) for x in rows if x.get("event_id") and x.get("action")]); con.commit(); con.close()


def calibrate_learning():
    t=now()
    flush_telemetry()
    with DB_LOCK:
        con=db()
        src=con.execute("SELECT id,fetched,failures,corroborated,reliability FROM sources WHERE enabled=1").fetchall()
        for r in src:
            attempts=max(1,int(r["fetched"] or 0)+int(r["failures"] or 0)); success=int(r["fetched"] or 0)/attempts if attempts else .5
            target=max(.10,min(.99,.35+.40*success+.25*min(1,(r["corroborated"] or 0)/max(1,r["fetched"] or 1))))
            con.execute("UPDATE sources SET reliability=? WHERE id=?",(.92*float(r["reliability"] or .5)+.08*target,r["id"]))
        topics=con.execute("SELECT topic FROM events WHERE last_seen>? GROUP BY topic",(t-30*86400,)).fetchall()
        for tr in topics:
            topic=tr[0]; seen=con.execute("SELECT COUNT(*) FROM telemetry t JOIN events e ON e.id=t.event_id WHERE e.topic=? AND t.action='seen' AND t.at>?",(topic,t-30*86400)).fetchone()[0]; opened=con.execute("SELECT COUNT(*) FROM telemetry t JOIN events e ON e.id=t.event_id WHERE e.topic=? AND t.action='open' AND t.at>?",(topic,t-30*86400)).fetchone()[0]; rate=opened/max(1,seen)
            con.execute("INSERT INTO learning(key,value,observations,updated_at) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,observations=excluded.observations,updated_at=excluded.updated_at",(f"topic_open_rate:{topic}",rate,seen,t))
        con.execute("INSERT OR REPLACE INTO system_metrics(key,value,updated_at) VALUES('last_calibration',?,?)",(str(t),t)); con.commit(); con.close()
    FEED_INVALIDATED.set()


def safe_url(url):
    return url if isinstance(url,str) and urllib.parse.urlsplit(url).scheme in ("http","https") and urllib.parse.urlsplit(url).netloc else ""


def build_personal_relevance(e, signals=None):
    signals=signals or {}
    out=[]
    topic=e.get("topic") or "World"
    financial=float(signals.get("financial") or e.get("financial_relevance") or 0)
    supply=float(signals.get("supply_chain") or e.get("supply_chain_relevance") or 0)
    social=float(signals.get("social") or e.get("social_relevance") or 0)
    geo=float(signals.get("geopolitical") or e.get("geopolitical_relevance") or 0)
    if financial>=.45: out.append("Money / costs")
    if supply>=.45: out.append("Prices / availability")
    if social>=.45: out.append("Safety / public life")
    if topic in {"Business","Technology","AI","Markets","Economy","Education"} or financial>=.60: out.append("Work / business")
    if topic in {"Travel","Weather","Climate","Local"}: out.append("Travel / mobility")
    if topic in {"Health"}: out.append("Health / daily life")
    if not out and geo>=.55: out.append("Policy / security")
    # Keep only observed, general relevance categories; this is not personalized advice.
    seen=set(); result=[]
    for x in out:
        if x not in seen: seen.add(x); result.append(x)
    return result[:4]

def build_local_relevance(title, topic=None, city="", state_name=""):
    if not (city or state_name): return 0.0
    txt=clean_text(title).lower()
    score=0.0
    for value,weight in ((city,.75),(state_name,.45)):
        val=clean_text(value).lower()
        if val and val in txt: score=max(score,weight)
    if topic in {"Local","India"} and score: score=min(1.0,score+.10)
    return score


def _serialize_event(e,meta_map,score_override=None):
    m=meta_map.get(e["id"]); domains=[d for d in (m["domains"].split(",") if m and m["domains"] else []) if d]
    mlanguages = (m["languages"] if m is not None and "languages" in m.keys() else "") if hasattr(m, "keys") else (m.get("languages") if m else "")
    languages=[d for d in str(mlanguages or "").split(",") if d]
    mcountries = m["countries"] if m is not None and "countries" in m.keys() else ""
    countries=[d for d in str(mcountries or "").split(",") if d]
    # published: use the most recently published article's timestamp
    # (MAX published across all linked articles, already computed in meta_map)
    pub=float(m["published"]) if m and m["published"] else None
    # latest_published: the timestamp of the latest_article_id specifically
    latest_pub=float(m["latest_published"]) if m and m.get("latest_published") else pub
    signals={"global":round(float(e["significance"] or 0),2),"india":round(float(e["india_relevance"] or 0),2),"financial":round(float(e["financial_relevance"] or 0),2),"supply_chain":round(float(e["supply_chain_relevance"] or 0),2),"geopolitical":round(float(e["geopolitical_relevance"] or 0),2),"social":round(float(e["social_relevance"] or 0),2)}
    confidence=min(.99,max(.05,.38*float(e["corroboration"] or 0)+.30*float(e["authority"] or 0)+.17*float(e["velocity"] or 0)+.15*float(e["significance"] or 0)))
    impact=min(.99,max(.05,.45*float(e["significance"] or 0)+.18*float(e["urgency"] or 0)+.12*float(e["financial_relevance"] or 0)+.12*float(e["geopolitical_relevance"] or 0)+.13*float(e["supply_chain_relevance"] or 0)))
    source_strength=min(.99,max(.05,.50*min(1,float(e["official_count"] or 0)/2)+.30*min(1,float(e["publisher_count"] or 0)/4)+.20*min(1,float(e["source_count"] or 0)/6)))
    affected=[]
    if signals["financial"]>=.45: affected.append("Markets")
    if signals["geopolitical"]>=.45: affected.append("Security")
    if signals["supply_chain"]>=.45: affected.append("Supply chain")
    if signals["india"]>=.45: affected.append("India")
    if signals["social"]>=.45: affected.append("Public impact")
    if e["topic"] in ("Weather","Climate"): affected.append("Environment")
    if e["topic"]=="Sports": affected.append("Sports")
    why=[]
    if e["source_count"]>=2: why.append(f"{e['source_count']} independent reports")
    if e["official_count"]: why.append(f"{e['official_count']} official source{'s' if e['official_count']!=1 else ''}")
    if impact>=.65: why.append("high impact signal")
    elif confidence>=.70: why.append("strong corroboration")
    elif e["velocity"]>=.60: why.append("rapidly developing")
    if not why: why.append("fresh event activity")
    local_rel=build_local_relevance(e["title"], e.get("topic"), AETHERIA_CITY, AETHERIA_STATE)
    life_path=build_personal_relevance(e, signals)
    if local_rel>0 and "Local" not in life_path: life_path=["Local / city impact"]+life_path
    # URL: use the latest article's URL as the primary click-through for recency.
    # Falls back to primary_article (founding article) if latest is not available.
    display_url = safe_url(m["latest_url"] if m else "") or safe_url(m["primary_url"] if m else "")
    display_domain = (m["latest_domain"] if m else "") or (m["primary_domain"] if m else "")
    display_image = safe_url(m.get("latest_image_url") if m else "") or safe_url(m.get("image_url") if m else "")
    obj={"id":e["id"],"title":e["title"],"topic":e["topic"],"status":e["status"],"last_seen":e["last_seen"],
         "published":pub,"published_utc":datetime.fromtimestamp(pub,timezone.utc).isoformat() if pub else None,
         "latest_published":latest_pub,"latest_published_utc":datetime.fromtimestamp(latest_pub,timezone.utc).isoformat() if latest_pub else None,
         "score":round(float(score_override if score_override is not None else e["significance"])*100,1),
         "sources":e["source_count"],"source_tiers":{"official":e["official_count"],"publisher":e["publisher_count"],"discovery":e["discovery_count"]},
         "source_domains":domains[:6],"languages":languages[:8],"source_countries":countries[:8],
         "article_count":int(e["article_count"] or 0),
         "url":display_url,"domain":display_domain,"image_url":display_image,
         "latest_url":safe_url(m["latest_url"] if m else ""),"latest_domain":(m["latest_domain"] if m else ""),
         "description":(e["summary"] or (m["description"] if m and m["description"] else ""))[:PRIMARY_DESCRIPTION_LIMIT],
         "velocity":round(float(e["velocity"] or 0),2),"signals":signals,
         "india_lens_score":round(min(1.0,max(0.0,.55*signals["india"]+.18*signals["financial"]+.15*signals["supply_chain"]+.08*signals["geopolitical"]+.04*signals["global"])),3),
         "india_lens_reasons":[x for x in ([(("India" if signals["india"]>=.45 else None)),("Markets" if signals["financial"]>=.45 else None),("Trade / supply" if signals["supply_chain"]>=.45 else None),("Geopolitics" if signals["geopolitical"]>=.45 else None)]) if x][:3],
         "intelligence":{"confidence":round(confidence,2),"impact":round(impact,2),"source_strength":round(source_strength,2)},
         "reason":e["last_reason"] or "","why_matters":why[:3],"affected_domains":affected[:4],
         "personal_relevance":life_path,"life_impact":life_path[:4],"decision_relevance":life_path[:4],
         "primary_article_id":e["primary_article_id"],"local_relevance":round(local_rel,3)}
    return obj


def build_enriched():
    active_cutoff=now()-EVENT_ACTIVE_HOURS*3600
    retention_cutoff=now()-RETENTION_DAYS*86400
    con=None
    try:
        con=db_read()
        rows=con.execute("SELECT * FROM events WHERE last_seen>? AND length(trim(title))>=8 ORDER BY last_seen DESC LIMIT ?",(active_cutoff,EVENT_POOL_LIMIT)).fetchall()
        if not rows:
            rows=con.execute("SELECT * FROM events WHERE last_seen>? AND length(trim(title))>=8 ORDER BY last_seen DESC LIMIT ?",(retention_cutoff,EVENT_POOL_LIMIT)).fetchall()
        if not rows:
            return []
        ids=[r["id"] for r in rows]
        meta=[]
        chunk_size=500
        for i in range(0, len(ids), chunk_size):
            chunk_ids=ids[i:i+chunk_size]
            marks=",".join("?" for _ in chunk_ids)
            try:
                # FIXED: Use correlated subquery to get data from the article with MAX published.
                # Previously MAX(a.canonical_url) gave a lexicographically-highest URL, not the
                # URL of the most-recently-published article. Now we use latest_article_id from
                # the events table (set during ingest) and a correlated subquery fallback.
                chunk_meta=con.execute(f"""SELECT ea.event_id,
                    MAX(CASE WHEN a.id=e.primary_article_id THEN a.canonical_url END) primary_url,
                    MAX(CASE WHEN a.id=e.primary_article_id THEN a.domain END) primary_domain,
                    MAX(CASE WHEN a.id=e.primary_article_id THEN a.image_url END) primary_image_url,
                    MAX(CASE WHEN a.id=e.primary_article_id THEN a.published END) primary_published,
                    MAX(CASE WHEN a.id=e.primary_article_id THEN a.description END) primary_description,
                    MAX(CASE WHEN a.id=e.latest_article_id THEN a.canonical_url END) latest_url,
                    MAX(CASE WHEN a.id=e.latest_article_id THEN a.domain END) latest_domain,
                    MAX(CASE WHEN a.id=e.latest_article_id THEN a.image_url END) latest_image_url,
                    MAX(CASE WHEN a.id=e.latest_article_id THEN a.description END) latest_description,
                    MAX(CASE WHEN a.id=e.latest_article_id THEN a.published END) latest_published,
                    MAX(a.published) published,
                    GROUP_CONCAT(DISTINCT a.domain) domains,
                    GROUP_CONCAT(DISTINCT a.language) languages,
                    GROUP_CONCAT(DISTINCT a.country) countries
                  FROM event_articles ea JOIN articles a ON a.id=ea.article_id JOIN events e ON e.id=ea.event_id
                  WHERE ea.event_id IN ({marks}) GROUP BY ea.event_id, e.id, e.primary_article_id, e.latest_article_id""",chunk_ids).fetchall()
                meta.extend(chunk_meta)
            except Exception as meta_exc:
                print(f"[Aetheria build_enriched meta warning] {type(meta_exc).__name__}: {str(meta_exc)[:180]}", flush=True)
        try:
            learn=con.execute("SELECT key,value,observations FROM learning WHERE key LIKE 'topic_open_rate:%'").fetchall()
        except Exception:
            learn=[]
    except Exception as exc:
        print(f"[Aetheria build_enriched warning] {type(exc).__name__}: {str(exc)[:180]}", flush=True)
        return []
    finally:
        if con:
            con.close()
    meta_map={}
    for m in meta:
        m_dict = dict(m)
        # latest_url/domain/image: prefer the explicit latest_article_id match;
        # fall back to primary if latest_article_id is the same or null.
        m_dict["latest_url"] = m_dict.get("latest_url") or m_dict.get("primary_url") or ""
        m_dict["latest_domain"] = m_dict.get("latest_domain") or m_dict.get("primary_domain") or ""
        m_dict["latest_image_url"] = m_dict.get("latest_image_url") or m_dict.get("primary_image_url") or ""
        m_dict["latest_description"] = m_dict.get("latest_description") or m_dict.get("primary_description") or ""
        m_dict["latest_published"] = m_dict.get("latest_published") or m_dict.get("published") or None
        # primary_url is the canonical event link (founding article). Use it as fallback everywhere.
        m_dict["primary_url"] = m_dict.get("primary_url") or m_dict.get("latest_url") or ""
        m_dict["primary_domain"] = m_dict.get("primary_domain") or m_dict.get("latest_domain") or ""
        m_dict["image_url"] = m_dict.get("primary_image_url") or m_dict.get("latest_image_url") or ""
        m_dict["description"] = m_dict.get("primary_description") or m_dict.get("latest_description") or ""
        meta_map[m_dict["event_id"]] = m_dict

    learn_map={m["key"].split(":",1)[1]:(float(m["value"]),int(m["observations"] or 0)) for m in learn}
    out=[]; t=now()
    for r0 in rows:
        e=dict(r0)
        age_h=max(0.0,(t-float(e["last_seen"] or t))/3600.0)
        freshness=max(0.0, 1.0 - (age_h / 24.0) ** 0.8) if age_h <= 36.0 else 0.0
        recency_mult=1.0 if age_h <= 8.0 else (0.85 if age_h <= 16.0 else (0.50 if age_h <= 24.0 else (0.20 if age_h <= 48.0 else 0.05)))
        base=(float(e["significance"] or 0)*.38+freshness*.36+float(e["velocity"] or 0)*.12+float(e["corroboration"] or 0)*.07+float(e["authority"] or 0)*.04+float(e["novelty"] or 0)*.03)*recency_mult
        lr=learn_map.get(e["topic"])
        if lr and lr[1]>=8:
            base*=max(.92,min(1.10,1+(lr[0]-.20)*.20))
        impact=.45*float(e["significance"] or 0)+.18*float(e["urgency"] or 0)+.12*float(e["financial_relevance"] or 0)+.12*float(e["geopolitical_relevance"] or 0)+.13*float(e["supply_chain_relevance"] or 0)
        # latest_score: use the article's actual pub_ts for sorting the Latest tab.
        # This is the MAX published timestamp across all linked articles (from meta_map["published"]).
        # last_seen is now always current-ingest-time, so it's not useful for article pub ordering.
        # We use MAX(article published) as the authoritative "when did this event last have new info".
        m=meta_map.get(e["id"])
        article_pub_raw=float(m["published"]) if m and m["published"] else 0.0
        article_pub_ts=article_pub_raw if (t - 86400 * 30 <= article_pub_raw <= t + 7200) else 0.0
        # latest_score is based purely on article publication time so Latest tab is CHRONOLOGICAL by article.
        latest=article_pub_ts if article_pub_ts > 0 else float(e["last_seen"] or 0)
        moving=(float(e["velocity"] or 0)*.60+freshness*.25+float(e["novelty"] or 0)*.15)*recency_mult
        flash=(.34*float(e["urgency"] or 0)+.24*float(e["velocity"] or 0)+.18*freshness+.14*float(e["significance"] or 0)+.06*float(e["authority"] or 0)+.04*float(e["corroboration"] or 0))*recency_mult
        obj=_serialize_event(e,meta_map,base)
        india_lens=float(obj.get("india_lens_score") or 0)
        editorial=(freshness*.46+float(e["significance"] or 0)*.20+float(e["velocity"] or 0)*.12+float(e["corroboration"] or 0)*.06+india_lens*.14+flash*.02)*recency_mult
        obj["flash_score"]=round(max(0.0,min(1.0,flash)),3)
        obj["is_flash"]=bool(flash>=.72 and freshness>=.20 and (float(e["urgency"] or 0)>=.45 or int(e["source_count"] or 0)>=2 or int(e["official_count"] or 0)>0))
        out.append({"raw":e,"important_score":base,"impact_score":impact,"latest_score":latest,"moving_score":moving,"flash_score":flash,"editorial_score":editorial,"obj":obj})
    out.sort(key=lambda x:x["important_score"],reverse=True)
    return out


def diversity_select(items,n=10,exclude_ids=None,per_topic=2,per_domain=2):
    chosen=[]; topic_counts=Counter(); domain_counts=Counter(); excluded=set(exclude_ids or ())
    for x in items:
        oid=x["obj"]["id"]
        if oid in excluded: continue
        o=x["obj"]; topic=o.get("topic") or "World"; dom=o.get("domain") or ""
        if topic_counts[topic]>=per_topic: continue
        if dom and domain_counts[dom]>=per_domain: continue
        chosen.append(x); excluded.add(oid); topic_counts[topic]+=1; domain_counts[dom]+=1
        if len(chosen)>=n: break
    if len(chosen)<n:
        for x in items:
            oid=x["obj"]["id"]
            if oid in excluded: continue
            chosen.append(x); excluded.add(oid)
            if len(chosen)>=n: break
    return [x["obj"] for x in chosen]



def section_groups():
    return [
      ("India & Current Affairs",{"India","Politics","Local","Education","Health"}),
      ("Finance & Markets",{"Finance","Markets","Economy","Business","Commodities","Energy"}),
      ("World & Geopolitics",{"Geopolitics","World"}),
      ("Technology & Science",{"Technology","AI","Science","Space"}),
      ("Sports",{"Sports"}),
      ("Entertainment & Culture",{"Entertainment","Culture"}),
      ("Local & Life",{"Travel","Property","Autos"}),
    ]


def build_sections(enriched,exclude_ids=None):
    excluded=set(exclude_ids or ())
    sections=[]
    # Keep discovery rails useful even when the live source window is small.
    # Two stories per rail below 40 active events; three when the pool is richer.
    per_section=2 if len(enriched)<40 else 4
    for label,topics in section_groups():
        picked=[]
        for x in enriched:
            o=x["obj"]
            if o["id"] in excluded or o.get("topic") not in topics: continue
            picked.append(o); excluded.add(o["id"])
            if len(picked)>=per_section: break
        if picked:
            sections.append({"id":re.sub(r"[^a-z0-9]+","-",label.lower()).strip("-"),
                             "label":label,"events":picked})
    return sections


def future_watch(limit=18, force=False):
    global FUTURE_CACHE
    t=now()
    with FUTURE_CACHE_LOCK:
        if not force and FUTURE_CACHE["at"] and t-FUTURE_CACHE["at"] < FUTURE_CACHE_SECONDS:
            return list(FUTURE_CACHE["value"])[:limit]
    try:
        con=db_read()
        rows=con.execute(
            "SELECT * FROM schedules WHERE start_ts>=? AND start_ts<=? "
            "ORDER BY start_ts ASC, importance DESC LIMIT 80",(t,t+30*86400)
        ).fetchall(); con.close()
    except Exception:
        with SNAPSHOT_LOCK: fallback=list(SNAPSHOT.get("future",[]))[:limit]
        return fallback
    out=[]
    for r in rows:
        d=dict(r); horizon="30D"
        if d["start_ts"]<=t+86400: horizon="24H"
        elif d["start_ts"]<=t+7*86400: horizon="7D"
        out.append({"id":d["id"],"title":d["title"],"category":d["category"],"kind":d["kind"],
                    "start_ts":d["start_ts"],"end_ts":d["end_ts"],"time_known":bool(d["time_known"]),
                    "url":d["url"],"description":d["description"],"importance":d["importance"],
                    "horizon":horizon})
    with FUTURE_CACHE_LOCK:
        FUTURE_CACHE={"at":t,"value":out}
    return out[:limit]



def _market_json(url, timeout=5):
    status,raw,_=request_bytes(url,timeout=timeout)
    if status<200 or status>=300: raise OSError(f"HTTP {status}")
    return json.loads(raw.decode("utf-8","replace"))


def _yahoo_quote(symbol):
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(symbol,safe="")+"?range=1d&interval=15m&includePrePost=false"
    data=_market_json(url,timeout=5)
    res=((data.get("chart") or {}).get("result") or [{}])[0]
    meta=res.get("meta") or {}
    price=meta.get("regularMarketPrice")
    prev=meta.get("previousClose")
    if price is None: raise ValueError("price unavailable")
    change=None
    change_num=None
    if prev not in (None,0):
        change_num=round(float(price)-float(prev),2)
        change=change_num/float(prev)
    # Extract intraday sparkline points
    sparkline=[]
    try:
        quote_indicators=((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes=quote_indicators.get("close") or []
        sparkline=[round(float(v),2) for v in closes if v is not None][-20:]
    except Exception:
        sparkline=[]
    return {"symbol":symbol,"price":float(price),"change":change,"change_num":change_num,"previous_close":float(prev) if prev is not None else None,"sparkline":sparkline,"currency":meta.get("currency") or "","at":float(meta.get("regularMarketTime") or now())}


def _frankfurter_rates():
    # Live/near-live market quote first; ECB/Frankfurter reference is an explicit
    # lower-frequency fallback and is never labelled as a live market tick.
    live=[]
    for sym,label in (("INR=X","USD/INR"),("EURINR=X","EUR/INR"),("GBPINR=X","GBP/INR"),("JPYINR=X","JPY/INR")):
        try:
            q=_yahoo_quote(sym); q["symbol"]=label; q["label"]=label; live.append(q)
        except Exception:
            pass
    if live:
        for q in live: q["quote_type"]="market"
        return live
    data=_market_json("https://api.frankfurter.dev/v2/rates?base=INR&quotes=USD,EUR,GBP,JPY",timeout=5)
    labels={"USD":"USD/INR","EUR":"EUR/INR","GBP":"GBP/INR","JPY":"JPY/INR"}
    out=[]
    for row in data.get("rates",[]) if isinstance(data,dict) else []:
        q=row.get("quote") or row.get("currency"); r=row.get("rate")
        if q and r not in (None,0): out.append({"symbol":labels.get(q,f"{q}/INR"),"price":1.0/float(r),"change":None,"currency":"INR reference","at":now(),"quote_type":"reference"})
    return out


def _bullion_prices():
    # Oropocket's public India endpoint is used only as a public quote source when it returns a usable payload.
    out=[]
    try:
        data=_market_json("https://api.oropocket.com/public/prices",timeout=5)
        blob=data.get("data") if isinstance(data,dict) else data
        if isinstance(blob,dict):
            blob=[blob]
        if isinstance(blob,list):
            for x in blob:
                name=str((x.get("name") or x.get("metal") or x.get("symbol") or "")).lower()
                val=x.get("sell") or x.get("price") or x.get("rate")
                if val is None: continue
                if "gold" in name and not any(o["symbol"]=="Gold / India quote" for o in out): out.append({"symbol":"Gold / India quote","label":"GOLD","price":float(val),"change":None,"currency":str(x.get("currency") or "INR"),"at":now()})
                if "silver" in name and not any(o["symbol"]=="Silver / India quote" for o in out): out.append({"symbol":"Silver / India quote","label":"SILVER","price":float(val),"change":None,"currency":str(x.get("currency") or "INR"),"at":now()})
    except Exception:
        pass
    if not out:
        for sym,label in (("GC=F","Gold / global futures"),("SI=F","Silver / global futures")):
            try:
                q=_yahoo_quote(sym)
                q["symbol"]=label
                q["label"]="GOLD" if "Gold" in label else "SILVER"
                out.append(q)
            except Exception:
                pass
    return out


def refresh_market(force=False):
    global MARKET_CACHE
    t=now()
    with MARKET_CACHE_LOCK:
        if not force and MARKET_CACHE.get("at") and t-MARKET_CACHE["at"]<MARKET_POLL_SECONDS:
            return MARKET_CACHE
    groups=[]
    # 1. India Key Indices
    india_idx=[]
    for sym,label in (("^NSEI","NIFTY 50"),("^BSESN","SENSEX"),("^NSEBANK","NIFTY BANK"),("^CNXIT","NIFTY IT")):
        try:
            q=_yahoo_quote(sym); q["label"]=label; india_idx.append(q)
        except Exception as exc:
            india_idx.append({"label":label,"symbol":sym,"available":False,"error":str(exc)[:120]})

    # 2. International & Global Indices
    global_idx=[]
    for sym,label in (("^GSPC","S&P 500"),("^IXIC","NASDAQ"),("^DJI","DOW JONES"),("^N225","NIKKEI 225"),("^FTSE","FTSE 100")):
        try:
            q=_yahoo_quote(sym); q["label"]=label; global_idx.append(q)
        except Exception as exc:
            global_idx.append({"label":label,"symbol":sym,"available":False,"error":str(exc)[:120]})

    # 3. Currencies (INR Pairs)
    fx=[]
    try:
        fx=_frankfurter_rates()
    except Exception as exc:
        fx=[{"label":"INR FX","available":False,"error":str(exc)[:120]}]

    # 4. Bullion & Commodities
    commodities=[]
    try:
        commodities=_bullion_prices()
    except Exception as exc:
        commodities=[{"label":"Bullion","available":False,"error":str(exc)[:120]}]
    try:
        oil=_yahoo_quote("BZ=F"); oil["label"]="Brent Crude"; oil["symbol"]="Brent Crude"; commodities.append(oil)
    except Exception:
        pass

    groups=[
        {"id":"india","label":"INDIA","source":"NSE / BSE · latest observed","items":india_idx},
        {"id":"global","label":"GLOBAL","source":"US & Global Exchanges · latest observed","items":global_idx},
        {"id":"currency","label":"CURRENCY","source":"Live INR quote when available","items":fx},
        {"id":"commodities","label":"COMMODITIES","source":"Global Futures · Bullion & Energy","items":commodities},
    ]
    available=sum(1 for g in groups if any(i.get("available",True) and i.get("price") is not None for i in g["items"]))
    cache={"at":t,"status":"live" if available else "unavailable","updated_iso":datetime.fromtimestamp(t,timezone.utc).isoformat(),"groups":groups}
    with MARKET_CACHE_LOCK: MARKET_CACHE=cache
    with SNAPSHOT_LOCK: SNAPSHOT["market"]=cache
    return cache



def request_market_refresh(force=False):
    """Return the current market snapshot immediately and refresh stale quotes in the background."""
    global MARKET_REFRESH_INFLIGHT
    t=now()
    with MARKET_CACHE_LOCK:
        cache=dict(MARKET_CACHE)
        age=t-float(MARKET_CACHE.get("at") or 0)
        stale=force or age>=MARKET_POLL_SECONDS or not MARKET_CACHE.get("groups")
        if not stale or MARKET_REFRESH_INFLIGHT:
            return cache
        MARKET_REFRESH_INFLIGHT=True
    def worker():
        global MARKET_REFRESH_INFLIGHT
        try:
            refresh_market(force=True)
        except Exception as exc:
            print(f"[Aetheria market] {type(exc).__name__}: {str(exc)[:160]}")
        finally:
            with MARKET_CACHE_LOCK:
                MARKET_REFRESH_INFLIGHT=False
    threading.Thread(target=worker,daemon=True,name="aetheria-market-refresh").start()
    return cache

def market_loop():
    while not STOP.is_set():
        try: request_market_refresh(force=True)
        except Exception as exc: print(f"[Aetheria market] {type(exc).__name__}: {str(exc)[:160]}")
        STOP.wait(MARKET_POLL_SECONDS)


def impact_channels(e):
    s=e.get("signals",{}); channels=[]
    if s.get("financial",0)>=.45: channels.append({"channel":"Financial","path":"Event → markets / financing / earnings","strength":s.get("financial")})
    if s.get("supply_chain",0)>=.45: channels.append({"channel":"Supply chain","path":"Event → trade / logistics / availability","strength":s.get("supply_chain")})
    if s.get("geopolitical",0)>=.45: channels.append({"channel":"Geopolitical","path":"Event → policy / security / trade","strength":s.get("geopolitical")})
    if s.get("india",0)>=.45: channels.append({"channel":"India","path":"Event → India-specific exposure","strength":s.get("india")})
    if s.get("social",0)>=.45: channels.append({"channel":"Public / social","path":"Event → public services / behaviour","strength":s.get("social")})
    if e.get("topic") in ("Weather","Climate"): channels.append({"channel":"Environment","path":"Event → transport / agriculture / energy","strength":s.get("global",0)})
    if e.get("topic")=="Sports": channels.append({"channel":"Sports","path":"Event → team / tournament / competition context","strength":s.get("global",0)})
    channels.sort(key=lambda x:x["strength"],reverse=True)
    return channels[:5]


def related_events(eid,limit=6):
    # Read-only contextual lookup. Ranking favours shared entities/title terms,
    # then topic and time proximity; broad category matches alone are insufficient.
    try:
        con=db_read()
        e=con.execute("SELECT * FROM events WHERE id=?",(eid,)).fetchone()
        if not e: con.close(); return []
        rows=con.execute(
            "SELECT * FROM events WHERE id!=? AND last_seen>? AND length(trim(title))>=8 "
            "ORDER BY last_seen DESC LIMIT 500",(eid,now()-72*3600)).fetchall(); con.close()
    except Exception:
        return []
    et=tokens(e["title"] or ""); 
    try: ents=set(json.loads(e["entities"] or "[]"))
    except Exception: ents=set()
    scored=[]
    for r in rows:
        rt=tokens(r["title"] or "")
        try: rent=set(json.loads(r["entities"] or "[]"))
        except Exception: rent=set()
        overlap=token_jaccard(et,rt)
        entity=len(ents&rent)/max(1,len(ents|rent))
        topic=.22 if r["topic"]==e["topic"] else 0
        rec=max(0,1-abs(float(r["last_seen"] or 0)-float(e["last_seen"] or 0))/172800)*.12
        score=overlap*.48+entity*.30+topic+rec
        if score>=.24 and (overlap>=.12 or entity>0):
            scored.append((score,r))
    scored.sort(key=lambda x:x[0],reverse=True)
    return [dict(r) for _,r in scored[:limit]]


def intelligence_status():
    return {
        "engine":"Aetheria Intelligence Engine",
        "mode":"LOCAL_DETERMINISTIC",
        "clustering":"multilingual event similarity",
        "trust":"source corroboration + authority + reliability",
        "conflict_detection":"claim polarity + semantic overlap",
        "summarization":"source-evidence extractive synthesis",
        "learning":"behavioural calibration",
        "multilingual":True,
    }

def _conflict_pairs(rows):
    positive={"confirms","confirmed","agrees","agreed","accepts","accepted","approved","approves","plans","planned","backs","supports","supported","will"}
    negative={"denies","denied","rejects","rejected","refutes","refuted","dismisses","dismissed","no plans","won't","wont","not","rules out","ruled out"}
    out=[]
    prepared=[]
    for r in rows:
        title=clean_text(r["title"] or "")
        tt=tokens(title)
        pos=any(p in title.lower() for p in positive); neg=any(n in title.lower() for n in negative)
        prepared.append((title,tt,pos,neg,r["domain"] or "source"))
    for i,a in enumerate(prepared):
        for b in prepared[i+1:]:
            if a[2]==b[3] or a[3]==b[2]:
                sim=token_jaccard(a[1],b[1])
                if sim>=.14:
                    out.append({"a":a[0],"b":b[0],"sources":f"{a[4]} ↔ {b[4]}","similarity":round(sim,2)})
    return out[:4]


def evidence_for_event(con,eid):
    rows=con.execute("SELECT a.title,a.domain,a.tier,a.published,a.language,COALESCE(s.reliability,.5) reliability FROM event_articles ea JOIN articles a ON a.id=ea.article_id LEFT JOIN sources s ON s.id=a.source_id WHERE ea.event_id=? ORDER BY COALESCE(a.published,a.fetched) DESC",(eid,)).fetchall()
    unique_domains=sorted({r["domain"] for r in rows if r["domain"]})
    reliability=sum(float(r["reliability"] or .5) for r in rows)/max(1,len(rows))
    conflicts=_conflict_pairs(rows)
    tiers=Counter(r["tier"] for r in rows)
    if conflicts: state="DISPUTED"
    elif tiers["official"] and len(unique_domains)>=2: state="CONFIRMED"
    elif len(unique_domains)>=2: state="DEVELOPING"
    elif tiers["discovery"] and not tiers["publisher"]: state="UNVERIFIED"
    else: state="NEW"
    return {"state":state,"reports":len(rows),"independent_sources":len(unique_domains),"official":tiers["official"],"publisher":tiers["publisher"],"discovery":tiers["discovery"],"source_reliability":round(reliability,2),"languages":sorted({r["language"] for r in rows if r["language"]}),"conflicts":conflicts}


def local_ai_analysis(con,eid):
    e=con.execute("SELECT * FROM events WHERE id=?",(eid,)).fetchone()
    if not e: return None
    ev=dict(e); evidence=evidence_for_event(con,eid)
    rows=con.execute("SELECT a.title,a.domain,a.description FROM event_articles ea JOIN articles a ON a.id=ea.article_id WHERE ea.event_id=? ORDER BY COALESCE(a.published,a.fetched) DESC LIMIT ?",(eid,LOCAL_ANALYSIS_SNIPPETS)).fetchall()
    titles=[clean_text(r["title"] or "") for r in rows if r["title"]]
    why=[]
    if evidence["independent_sources"]>=2: why.append(f"{evidence['independent_sources']} independent sources")
    if evidence["official"]: why.append(f"{evidence['official']} official source")
    if ev["velocity"]>=.45: why.append("rapidly changing coverage")
    if ev["india_relevance"]>=.45: why.append("direct India relevance")
    if ev["financial_relevance"]>=.45: why.append("financial transmission signal")
    if ev["supply_chain_relevance"]>=.45: why.append("supply-chain transmission signal")
    summary=titles[0] if titles else ev["title"]
    if len(titles)>1 and titles[1].lower()!=summary.lower(): summary += " — " + titles[1]
    uncertainty="; ".join(c["sources"] for c in evidence["conflicts"]) if evidence["conflicts"] else ("single-source / early signal" if evidence["independent_sources"]<2 else "no material source conflict detected")
    return {"summary":summary[:700],"why":" · ".join(why[:5]) or "fresh event activity","uncertainty":uncertainty[:500],"evidence_note":f"{evidence['reports']} reports · {evidence['independent_sources']} independent sources · {evidence['source_reliability']:.0%} average source reliability","status":"LOCAL_OBSERVED"}


def rebuild_snapshot():
    global SNAPSHOT
    enriched=build_enriched()
    with MARKET_CACHE_LOCK:
        market_snapshot=dict(MARKET_CACHE)
        market_snapshot["groups"]=[dict(g) for g in (MARKET_CACHE.get("groups") or [])]
        for g in market_snapshot["groups"]:
            g["items"]=list(g.get("items") or [])
    state=system_state(force=False)
    future=future_watch()
    if not enriched:
        with SNAPSHOT_LOCK:
            if SNAPSHOT.get("events"):
                SNAPSHOT["built_at"] = now()
                SNAPSHOT["state"] = state
                SNAPSHOT["market"] = market_snapshot
            else:
                SNAPSHOT={"revision":SNAPSHOT.get("revision",0)+1,"built_at":now(),"events":[],"flash":[],"important":[],"impact":[],"latest":[],"moving":[],"sections":[],"categories":category_payload_fast([]),"future":future,"market":market_snapshot,"home":build_home_payload([],[],[],[],future,[]),"state":state}
        FEED_INVALIDATED.clear(); return

    enriched_sorted=sorted(enriched,key=lambda x:(x["latest_score"],x["flash_score"]),reverse=True)
    flash_objs=[x["obj"] for x in sorted(enriched,key=lambda x:(x["flash_score"],x["latest_score"]),reverse=True) if x["obj"].get("is_flash")][:6]
    flash_ids={x["id"] for x in flash_objs}
    ranked_latest=[x for x in enriched_sorted if x["obj"]["id"] not in flash_ids]
    latest_visible=ranked_latest[:10]
    latest_signal=[x for x in ranked_latest[10:] if x["obj"]["id"] not in {z["obj"]["id"] for z in latest_visible}][:SIGNAL_LANE_LIMIT]
    latest_reserved={x["obj"]["id"] for x in (latest_visible+latest_signal)}

    candidates_important=[x for x in sorted(enriched,key=lambda x:(x["important_score"],x["latest_score"]),reverse=True) if x["obj"]["id"] not in latest_reserved and x["obj"]["id"] not in flash_ids]
    important_objs=diversity_select(candidates_important,max(SECONDARY_LANE_LIMIT,12))
    important_ids={x["id"] for x in important_objs}

    candidates_impact=[x for x in sorted(enriched,key=lambda x:(x["impact_score"],x["latest_score"]),reverse=True) if x["obj"]["id"] not in latest_reserved and x["obj"]["id"] not in important_ids and x["obj"]["id"] not in flash_ids]
    impact_objs=[x["obj"] for x in candidates_impact[:max(SECONDARY_LANE_LIMIT,12)]]

    moving_objs=[x["obj"] for x in sorted(enriched,key=lambda x:(x["moving_score"],x["latest_score"]),reverse=True)[:15]]
    visible_important_ids={x["id"] for x in important_objs[:5]}
    visible_impact_ids={x["id"] for x in impact_objs[:5]}
    discovery_exclude=flash_ids|latest_reserved|visible_important_ids|visible_impact_ids
    sections=build_sections(enriched,exclude_ids=discovery_exclude)
    all_objs=[x["obj"] for x in enriched[:max(SNAPSHOT_EVENT_LIMIT, 350)]]
    cats=category_payload_fast([x["obj"] for x in enriched])
    home=build_home_payload(enriched,ranked_latest,important_objs,impact_objs,future,moving_objs,flash_objs)

    # Ensure category diversity in SNAPSHOT["latest"] so all tabs (Legal, World, Technology, Geopolitics, etc.) have rich stories
    by_topic = {}
    for x in ranked_latest:
        t = x["obj"].get("topic") or "World"
        by_topic.setdefault(t, []).append(x)

    latest_diverse = []
    seen_latest_ids = set()
    for t, items in by_topic.items():
        for it in items[:30]:
            if it["obj"]["id"] not in seen_latest_ids:
                latest_diverse.append(it)
                seen_latest_ids.add(it["obj"]["id"])

    for it in ranked_latest:
        if len(latest_diverse) >= 800:
            break
        if it["obj"]["id"] not in seen_latest_ids:
            latest_diverse.append(it)
            seen_latest_ids.add(it["obj"]["id"])

    latest_diverse.sort(key=lambda x:(x["latest_score"],x["flash_score"]),reverse=True)
    latest_lane_objs = [x["obj"] for x in latest_diverse]

    t_now = now()
    latest_article_pub = max((float(o.get("published") or 0) for o in all_objs if o.get("published")), default=0.0)
    latest_event_seen = max((float(o.get("last_seen") or 0) for o in all_objs if o.get("last_seen")), default=0.0)
    freshest_age = round(max(0.0, t_now - latest_event_seen), 1) if latest_event_seen > 0 else 0.0

    with SNAPSHOT_LOCK:
        rev=SNAPSHOT.get("revision",0)+1
        SNAPSHOT={
            "revision":rev,
            "built_at":t_now,
            "latest_article_published_at":latest_article_pub,
            "latest_event_last_seen":latest_event_seen,
            "freshest_event_age_seconds":freshest_age,
            "events":all_objs,
            "flash":flash_objs,
            "important":important_objs,
            "impact":impact_objs,
            "latest":latest_lane_objs,
            "moving":moving_objs,
            "sections":sections,
            "categories":cats,
            "future":future,
            "market":market_snapshot,
            "home":home,
            "state":state
        }
    print(f"[SNAPSHOT] Rebuilt revision {rev} | duration={int((now()-t_now)*1000)}ms | events={len(all_objs)} | freshest_event={freshest_age}s ago", flush=True)
    refresh_event_index()
    FEED_INVALIDATED.clear()


def build_home_payload(enriched, ranked_latest, important_objs, impact_objs, future, moving_objs, flash_objs=None):
    latest=[x["obj"] for x in ranked_latest]
    flash_objs=list(flash_objs or [])
    now_ts=now()
    if not latest and not flash_objs:
        return {"lead":None,"stack":[],"flash":[],"happening":[],"india_lens":[],"impact":[],"emerging":[],"read_next":[],"now":None,"next":(future or [None])[0],"pressure":[],"metrics":{"reports_24h":0,"events_24h":0,"confirmed":0,"developing":0,"disputed":0,"unverified":0,"flash":0},"ai":intelligence_status()}
    used=set()
    flash_ids={o["id"] for o in flash_objs}
    def _stack_score(x):
        """Dynamic continuous signal score for the Story Stack.
        Combines recency, new information, reporting velocity, independent source breadth,
        and India/Global significance without fixed hardcoded ratios."""
        o=x["obj"]
        pub_time=float(o.get("published") or o.get("last_seen") or now_ts)
        age_h=max(0.0,(now_ts-pub_time)/3600.0)
        recency=math.exp(-age_h / 14.0) # Continuous exponential decay
        
        india=float(o.get("india_lens_score") or 0)
        local=float(o.get("local_relevance") or 0)
        velocity=float(o.get("velocity") or 0)
        sources=min(1.0, float(o.get("sources") or 1) / 8.0)
        impact=float((o.get("intelligence") or {}).get("impact") or 0.5)

        # Dynamic blend without fixed category or region quotas
        signal = (recency * 0.45) + (velocity * 0.15) + (sources * 0.15) + (max(india, local) * 0.15) + (impact * 0.10)
        return signal

    # Stack candidates: prefer events published in the last 24h; fall back to all if fewer than 4
    fresh_editorial=[x for x in enriched if x["obj"]["id"] not in flash_ids and max(0.0,(now_ts-float(x["obj"].get("published") or x["obj"].get("last_seen") or now_ts))/3600.0)<=24.0]
    editorial_candidates=fresh_editorial if len(fresh_editorial)>=4 else [x for x in enriched if x["obj"]["id"] not in flash_ids]
    editorial_pool=sorted(editorial_candidates, key=_stack_score, reverse=True)
    stack=[x["obj"] for x in editorial_pool[:10]]
    # If the live pool is temporarily smaller, keep a true latest-first fallback from
    # already verified events, never fabricate stories.
    if len(stack)<10:
        for o in sorted(latest,key=lambda z:(float(z.get("last_seen") or 0),float(z.get("published") or 0)),reverse=True):
            if o["id"] in flash_ids or o["id"] in {x["id"] for x in stack}: continue
            stack.append(o)
            if len(stack)>=10: break
    lead=(flash_objs[0] if flash_objs else (stack[0] if stack else latest[0]))
    used.update(x["id"] for x in stack); used.update(flash_ids)

    # India Now is a strict India/local lane. Flash items stay in the dedicated Flash rail.
    india_pool=[]
    for o in latest:
        if o["id"] in used: continue
        india_score=float((o.get("signals") or {}).get("india") or 0)
        country_in="IN" in {str(c).upper() for c in (o.get("source_countries") or [])}
        lang_in=bool(set(str(x).lower() for x in (o.get("languages") or [])) & INDIA_LANGUAGES)
        local=o.get("local_relevance",0)>0
        if india_score>=.35 or country_in or lang_in or local or o.get("topic") in {"India","Local"}: india_pool.append(o)
    # India Now: sort primarily by publication recency so truly breaking India news surfaces first.
    # Secondary sort by india signal and local relevance for diversity.
    india_pool=sorted(india_pool,key=lambda o:(
        float(o.get("published") or o.get("last_seen") or 0)*0.70
        +float((o.get("signals") or {}).get("india") or 0)*3600.0*8.0*0.20
        +float(o.get("local_relevance") or 0)*3600.0*8.0*0.10
    ),reverse=True)
    happening=[]; hc=Counter(); hd=Counter()
    for o in india_pool:
        topic=o.get("topic") or "World"; dom=o.get("domain") or ""
        if hc[topic]>=2 or (dom and hd[dom]>=2): continue
        happening.append(o); used.add(o["id"]); hc[topic]+=1; hd[dom]+=1
        if len(happening)>=5: break

    india_ranked=sorted([x for x in enriched if x["obj"]["id"] not in used],key=lambda x:(float(x["obj"].get("india_lens_score",0))*.48+float(x["obj"].get("local_relevance",0))*.16+float(x["moving_score"])*.16+max(0.0,min(1.0,1.0-(now_ts-float(x["obj"].get("last_seen") or now_ts))/86400.0))*.12+float(x["raw"].get("significance",0))*.08),reverse=True)
    india_lens=[]; ic=Counter()
    for x in india_ranked:
        o=x["obj"]; topic=o.get("topic") or "World"
        if o["id"] in used or float(o.get("india_lens_score",0))<.14: continue
        if ic[topic]>=2: continue
        india_lens.append(o); used.add(o["id"]); ic[topic]+=1
        if len(india_lens)>=6: break

    impact_ranked=sorted([x for x in enriched if x["obj"]["id"] not in used],key=lambda x:(float(x["impact_score"]),float(x["obj"].get("india_lens_score",0)),float(x["moving_score"])),reverse=True)
    impact=[]; pc=Counter()
    for x in impact_ranked:
        o=x["obj"]; topic=o.get("topic") or "World"
        if pc[topic]>=2: continue
        impact.append(o); used.add(o["id"]); pc[topic]+=1
        if len(impact)>=6: break

    emerging_ranked=sorted([x for x in enriched if x["obj"]["id"] not in used],key=lambda x:(float(x["moving_score"])*.50+float(x["raw"].get("novelty",0))*.30+float(x["impact_score"])*.20),reverse=True)
    emerging=[]
    for x in emerging_ranked:
        o=x["obj"]
        if int(o.get("sources") or 0)>3: continue
        if float(o.get("velocity") or 0)<.15 and float(x["raw"].get("novelty",0))<.45: continue
        emerging.append(o); used.add(o["id"])
        if len(emerging)>=4: break

    read_next=[o for o in latest if o["id"] not in used and o["id"] not in flash_ids][:12]
    now_item=(moving_objs or [None])[0]
    metrics={"reports_24h":int(sum(float(x["obj"].get("article_count") or 0) for x in enriched)),"events_24h":len(enriched),"confirmed":sum(1 for x in enriched if x["obj"].get("status")=="CONFIRMED"),"developing":sum(1 for x in enriched if x["obj"].get("status")=="DEVELOPING"),"disputed":sum(1 for x in enriched if x["obj"].get("status")=="DISPUTED"),"unverified":sum(1 for x in enriched if x["obj"].get("status")=="UNVERIFIED"),"flash":len(flash_objs)}
    return {"lead":lead,"stack":stack,"flash":flash_objs,"happening":happening,"india_lens":india_lens,"impact":impact,"emerging":emerging,"read_next":read_next,"now":now_item,"next":(future or [None])[0],"pressure":build_pressure(enriched),"metrics":metrics,"ai":intelligence_status()}


def category_payload_fast(items):
    counts=Counter(o.get("topic") for o in items if o.get("topic")); return [{"id":cid,"label":label,"count":int(counts.get(cid,0))} for cid,label in CATEGORIES]


def build_pressure(enriched, limit=6):
    """Observed news-pressure map: activity intensity, not sentiment and not a forecast."""
    channels=[
        ("Geopolitical pressure","geopolitical"),
        ("Market pressure","financial"),
        ("Trade & supply","supply_chain"),
        ("India exposure","india"),
        ("Technology pressure","technology"),
        ("Public / security","social"),
    ]
    technology_topics={"Technology","AI","Science","Space"}
    sums={k:0.0 for _,k in channels}; weights={k:0.0 for _,k in channels}
    t=now()
    for x in (enriched or [])[:700]:
        o=x["obj"]
        age_h=max(0.0,(t-float(o.get("last_seen") or t))/3600.0)
        freshness=max(0.15,1.0-age_h/48.0)
        velocity=float(o.get("velocity") or 0)
        event_weight=freshness*(0.70+0.30*velocity)
        sig=o.get("signals") or {}
        for _,k in channels:
            raw=sig.get(k,0)
            if k=="technology" and not raw and o.get("topic") in technology_topics:
                raw=max(float(o.get("significance") or 0),float(o.get("velocity") or 0)*0.65)
            v=max(0.0,min(1.0,float(raw or 0)))
            sums[k]+=v*event_weight
            weights[k]+=event_weight
    out=[]
    for label,key in channels:
        score=(sums[key]/weights[key]) if weights[key] else 0.0
        out.append({"id":key,"label":label,"score":round(max(0.0,min(1.0,score)),3)})
    out.sort(key=lambda x:x["score"],reverse=True)
    return out[:max(1,min(limit,len(out)))]


def system_state(force=False):
    with STATE_LOCK:
        if not force and STATE_CACHE["value"] and now()-STATE_CACHE["at"]<3:
            return STATE_CACHE["value"]
    con=None
    try:
        con=db_read(); t=now()
        ev=con.execute("SELECT COUNT(*) FROM events WHERE last_seen>?",(t-86400,)).fetchone()[0]
        ev48=con.execute("SELECT COUNT(*) FROM events WHERE last_seen>?",(t-2*86400,)).fetchone()[0]
        sig=con.execute("SELECT COUNT(*) FROM events WHERE last_seen>? AND significance>=0.55",(t-86400,)).fetchone()[0]
        arts=con.execute("SELECT COUNT(*) FROM articles WHERE fetched>?",(t-86400,)).fetchone()[0]
        arts48=con.execute("SELECT COUNT(*) FROM articles WHERE fetched>?",(t-2*86400,)).fetchone()[0]
        total=con.execute("SELECT COUNT(*) FROM sources WHERE enabled=1").fetchone()[0]
        healthy=con.execute("SELECT COUNT(*) FROM sources WHERE enabled=1 AND state='online' AND last_success IS NOT NULL AND (last_failure IS NULL OR last_success>last_failure)").fetchone()[0]
        fetching=con.execute("SELECT COUNT(*) FROM sources WHERE enabled=1 AND state='fetching'").fetchone()[0]
        telemetry=con.execute("SELECT COUNT(*) FROM telemetry WHERE at>?",(t-7*86400,)).fetchone()[0]
        learning=con.execute("SELECT COALESCE(SUM(observations),0) FROM learning").fetchone()[0]
        lm=con.execute("SELECT value FROM system_metrics WHERE key='last_ingest'").fetchone()
        lc=con.execute("SELECT value FROM system_metrics WHERE key='last_calibration'").fetchone()
        total_articles=con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        total_events=con.execute("SELECT COUNT(*) FROM events WHERE last_seen> ?",(t-EVENT_ACTIVE_HOURS*3600,)).fetchone()[0]
        value={"events_24h":int(ev),"events_48h":int(ev48),"events_active":int(total_events),"significant_24h":int(sig),"articles_24h":int(arts),"articles_48h":int(arts48),"articles_total":int(total_articles),"sources":int(total),
               "healthy_sources":int(healthy),"fetching_sources":int(fetching),
               "last_ingest":float(lm[0]) if lm else None,"last_calibration":float(lc[0]) if lc else None,
               "ready":bool(ev or healthy),"feed_ready":bool(ev>0 or arts>0),"engine_error":ENGINE_ERROR,"engine_error_at":ENGINE_ERROR_AT,
               "telemetry_7d":int(telemetry),"learning_observations":int(learning),"event_pool_limit":EVENT_POOL_LIMIT,"snapshot_event_limit":SNAPSHOT_EVENT_LIMIT}
    except sqlite3.OperationalError:
        with STATE_LOCK:
            return dict(STATE_CACHE.get("value") or {"events_24h":0,"events_48h":0,"events_active":0,"significant_24h":0,"articles_24h":0,"articles_48h":0,"articles_total":0,
                "sources":0,"healthy_sources":0,"fetching_sources":0,"last_ingest":None,"last_calibration":None,
                "ready":False,"feed_ready":False,"engine_error":ENGINE_ERROR,"engine_error_at":ENGINE_ERROR_AT,"telemetry_7d":0,"learning_observations":0,"event_pool_limit":EVENT_POOL_LIMIT,"snapshot_event_limit":SNAPSHOT_EVENT_LIMIT})
    finally:
        if con: con.close()
    with STATE_LOCK: STATE_CACHE.update({"at":now(),"value":value})
    return value



def source_status():
    con=None
    try:
        con=db_read()
        rows=con.execute("SELECT id,name,provider,url,tier,max_items,last_success,last_failure,failures,items,reliability,interval_sec,enabled,state,last_attempt,last_duration_ms,last_error,language,country,region,city,state_name,discovered_from FROM sources WHERE enabled=1 ORDER BY CASE tier WHEN 'official' THEN 0 WHEN 'publisher' THEN 1 ELSE 2 END,name").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        if con: con.close()



def diagnostics_payload():
    s=source_status()
    t=now()
    con=None
    art_1h=art_6h=art_24h=0
    evt_1h=evt_6h=evt_24h=0
    last_fetch_t=None
    last_ingest_t=None
    try:
        con=db_read()
        art_1h=con.execute("SELECT COUNT(*) FROM articles WHERE fetched>?",(t-3600,)).fetchone()[0]
        art_6h=con.execute("SELECT COUNT(*) FROM articles WHERE fetched>?",(t-6*3600,)).fetchone()[0]
        art_24h=con.execute("SELECT COUNT(*) FROM articles WHERE fetched>?",(t-24*3600,)).fetchone()[0]
        evt_1h=con.execute("SELECT COUNT(*) FROM events WHERE updated_at>?",(t-3600,)).fetchone()[0]
        evt_6h=con.execute("SELECT COUNT(*) FROM events WHERE updated_at>?",(t-6*3600,)).fetchone()[0]
        evt_24h=con.execute("SELECT COUNT(*) FROM events WHERE updated_at>?",(t-24*3600,)).fetchone()[0]
        last_fetch_row=con.execute("SELECT MAX(last_success) FROM sources").fetchone()
        last_fetch_t=last_fetch_row[0] if last_fetch_row else None
        lm=con.execute("SELECT value FROM system_metrics WHERE key='last_ingest'").fetchone()
        last_ingest_t=float(lm[0]) if lm and lm[0] else None
    except Exception:
        pass
    finally:
        if con: con.close()

    def counts(pool):
        return {
            "total":len(pool),
            "online":sum(1 for r in pool if r["state"]=="online" and r["last_success"] and (not r["last_failure"] or r["last_success"]>=r["last_failure"])),
            "fetching":sum(1 for r in pool if r["state"]=="fetching"),
            "degraded":sum(1 for r in pool if r.get("error_class") in ("DEGRADED","UNAVAILABLE")),
            "rate_limited":sum(1 for r in pool if r.get("error_class")=="RATE_LIMITED"),
            "invalid_feed":sum(1 for r in pool if r.get("error_class")=="INVALID_FEED"),
            "not_found":sum(1 for r in pool if r.get("error_class")=="NOT_FOUND"),
            "dns_error":sum(1 for r in pool if r.get("error_class")=="DNS_ERROR"),
            "timeout":sum(1 for r in pool if r.get("error_class")=="TIMEOUT"),
            "errors":sum(1 for r in pool if r["state"]=="error")
        }

    grouped={tier:counts([r for r in s if r["tier"]==tier]) for tier in ("publisher","discovery","official")}
    with SNAPSHOT_LOCK:
        snap_built_at=SNAPSHOT.get("built_at",0)
        snap_rev=SNAPSHOT.get("revision",0)
        freshest_age=SNAPSHOT.get("freshest_event_age_seconds",0)

    debug_diag = {}
    try:
        con_d = db_read()
        n_art = con_d.execute("SELECT a.title, s.name, a.published FROM articles a JOIN sources s ON s.id=a.source_id ORDER BY a.published DESC LIMIT 1").fetchone()
        n_ind = con_d.execute("SELECT a.title, s.name, a.published FROM articles a JOIN sources s ON s.id=a.source_id WHERE s.country='IN' OR s.region='IN' OR a.country='IN' ORDER BY a.published DESC LIMIT 1").fetchone()
        n_int = con_d.execute("SELECT a.title, s.name, a.published FROM articles a JOIN sources s ON s.id=a.source_id WHERE (s.country!='IN' AND (s.region IS NULL OR s.region!='IN')) AND (a.country IS NULL OR a.country!='IN') ORDER BY a.published DESC LIMIT 1").fetchone()
        con_d.close()
        debug_diag = {
            "newest_article": {"title": n_art[0], "source": n_art[1], "published": datetime.fromtimestamp(n_art[2], timezone.utc).isoformat() if n_art and n_art[2] else None} if n_art else None,
            "newest_indian_article": {"title": n_ind[0], "source": n_ind[1], "published": datetime.fromtimestamp(n_ind[2], timezone.utc).isoformat() if n_ind and n_ind[2] else None} if n_ind else None,
            "newest_international_article": {"title": n_int[0], "source": n_int[1], "published": datetime.fromtimestamp(n_int[2], timezone.utc).isoformat() if n_int and n_int[2] else None} if n_int else None
        }
    except Exception:
        pass

    return {
        "ok":True,
        "debug_diagnostics": debug_diag,
        "freshness":{
            "articles_1h":int(art_1h),
            "articles_6h":int(art_6h),
            "articles_24h":int(art_24h),
            "events_updated_1h":int(evt_1h),
            "events_updated_6h":int(evt_6h),
            "events_updated_24h":int(evt_24h),
            "last_successful_fetch":datetime.fromtimestamp(last_fetch_t,timezone.utc).isoformat() if last_fetch_t else None,
            "last_successful_ingest":datetime.fromtimestamp(last_ingest_t,timezone.utc).isoformat() if last_ingest_t else None,
            "last_snapshot_rebuild":datetime.fromtimestamp(snap_built_at,timezone.utc).isoformat() if snap_built_at else None,
            "snapshot_revision":snap_rev,
            "freshest_event_age_seconds":freshest_age
        },
        "sources":counts(s),
        "feed":grouped["publisher"],
        "discovery":grouped["discovery"],
        "official":grouped["official"],
        "last_success_source":max((r for r in s if r["last_success"]),key=lambda x:x["last_success"],default=None),
        "errors":[{"name":r["name"],"state":r["state"],"error_class":r.get("error_class",""),"error":r["last_error"],"ms":r["last_duration_ms"],"failures":r["failures"],"consecutive_failures":r.get("consecutive_failures",0),"next_attempt_in_sec":round(max(0,(r.get("next_attempt_at") or 0)-t),1),"tier":r["tier"],"country":r["country"]} for r in s if r["state"]=="error"][:20]
    }




def _source_done(future,source):
    sid=source["id"]
    sname=source.get("name", sid)
    try:
        items,status=future.result()
        changed=False
        ingested_n=0
        if items:
            ingested_n=ingest(items)
            changed=bool(ingested_n)
        if status.get("schedules"):
            changed=True
        if changed: FEED_INVALIDATED.set()
        # Use sys.stdout.buffer for safe Unicode output on Windows CP1252 terminals
        try:
            print(f"[SOURCE] '{sname}' ({source.get('tier','publisher')}) | ok={status.get('ok')} | fetched={len(items or [])} | ingested={ingested_n} | duration={status.get('ms',0)}ms", flush=True)
        except (UnicodeEncodeError, UnicodeDecodeError):
            safe_name=sname.encode('ascii','replace').decode('ascii')
            print(f"[SOURCE] '{safe_name}' ({source.get('tier','publisher')}) | ok={status.get('ok')} | fetched={len(items or [])} | ingested={ingested_n} | duration={status.get('ms',0)}ms", flush=True)
    except Exception as exc:
        err=str(exc)[:200]
        try:
            print(f"[SOURCE ERROR] '{sname}' | {type(exc).__name__}: {err}", flush=True)
        except (UnicodeEncodeError, UnicodeDecodeError):
            safe_name=sname.encode('ascii','replace').decode('ascii')
            safe_err=err.encode('ascii','replace').decode('ascii')
            print(f"[SOURCE ERROR] '{safe_name}' | {type(exc).__name__}: {safe_err}", flush=True)
    finally:
        with SOURCE_INFLIGHT_LOCK: SOURCE_INFLIGHT.discard(sid)


def maybe_sync_sources():
    global SOURCE_CONFIG_MTIME,SOURCE_CONFIG_LAST_CHECK
    t=now();
    if t-SOURCE_CONFIG_LAST_CHECK<15: return
    SOURCE_CONFIG_LAST_CHECK=t
    try: mt=SOURCES_FILE.stat().st_mtime
    except Exception: return
    if mt!=SOURCE_CONFIG_MTIME:
        sync_sources(); SOURCE_CONFIG_MTIME=mt


def schedule_due_sources():
    maybe_sync_sources()
    with DB_LOCK:
        con=db()
        src=[dict(r) for r in con.execute("SELECT * FROM sources WHERE enabled=1").fetchall()]
        # STALL RECOVERY: any source stuck in "fetching" state for >3x FEED_TIMEOUT has likely
        # lost its thread callback. Reset it to "idle" so it gets re-queued on the next scan.
        stall_threshold = t_now = now()
        stall_cutoff = stall_threshold - max(FEED_TIMEOUT * 4, 60.0)
        try:
            stalled_count = con.execute(
                "UPDATE sources SET state='idle',last_error='stall-recovery',updated_at=? "
                "WHERE state='fetching' AND last_attempt<? AND enabled=1",
                (t_now, stall_cutoff)).rowcount
            if stalled_count:
                print(f"[STALL-RECOVERY] Reset {stalled_count} stalled sources to idle", flush=True)
        except Exception as exc:
            print(f"[STALL-RECOVERY] {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        con.commit(); con.close()
    t=now(); src.sort(key=lambda s:(0 if s.get("tier")=="official" else 1 if s.get("tier")=="publisher" else 2,s.get("last_success") or 0))
    # Also evict source IDs from SOURCE_INFLIGHT if they have been there too long
    # (defensive measure in case a future callback is dropped by the executor)
    with SOURCE_INFLIGHT_LOCK:
        stale_ids=[sid for sid in list(SOURCE_INFLIGHT) if not any(s["id"]==sid for s in src)]
        for sid in stale_ids:
            SOURCE_INFLIGHT.discard(sid)
    submitted=0
    # Limit concurrent discovery fetches to prevent them from starving publisher threads
    with SOURCE_INFLIGHT_LOCK:
        discovery_inflight=sum(1 for sid in SOURCE_INFLIGHT if any(s["id"]==sid and s.get("tier")=="discovery" for s in src))
    max_discovery_concurrent=max(4, MAX_WORKERS // 4)
    discovery_stagger=0.0
    for s in src:
        sid=s["id"]
        with SOURCE_INFLIGHT_LOCK:
            if sid in SOURCE_INFLIGHT: continue
            next_attempt=float(s.get("next_attempt_at") or 0)
            if next_attempt>0 and t<next_attempt: continue
            last=max(s.get("last_success") or 0,s.get("last_failure") or 0); interval=max(45,int(s.get("interval_sec") or 120))
            if t-last<interval: continue
            # Throttle discovery tier to avoid starving publisher/official sources
            if s.get("tier")=="discovery":
                discovery_inflight_now=sum(1 for x in SOURCE_INFLIGHT if any(ss["id"]==x and ss.get("tier")=="discovery" for ss in src))
                if discovery_inflight_now>=max_discovery_concurrent: continue
            SOURCE_INFLIGHT.add(sid)
        try:
            if s.get("tier")=="discovery":
                discovery_stagger += 0.5
                def delayed_fetch(src=s, delay=discovery_stagger):
                    time.sleep(delay)
                    return fetch_source(src)
                f=SOURCE_EXECUTOR.submit(delayed_fetch)
            else:
                f=SOURCE_EXECUTOR.submit(fetch_source,s)
            f.add_done_callback(lambda fut,src=s:_source_done(fut,src)); submitted+=1
        except Exception:
            with SOURCE_INFLIGHT_LOCK: SOURCE_INFLIGHT.discard(sid)
    return submitted


ENGINE_ERROR = None
ENGINE_ERROR_AT = 0.0
ENGINE_ERROR_LOCK = threading.Lock()

def maintenance_loop():
    global LAST_LEARNING, ENGINE_ERROR, ENGINE_ERROR_AT
    first=True; last_snapshot=now()
    while not STOP.is_set():
        try:
            submitted=schedule_due_sources()
            if FEED_INVALIDATED.is_set() and now()-last_snapshot>=SNAPSHOT_SECONDS:
                rebuild_snapshot(); last_snapshot=now()
            if first or now()-LAST_LEARNING>=LEARNING_SECONDS:
                LAST_LEARNING=now(); threading.Thread(target=calibrate_learning,daemon=True,name="aetheria-learning").start()
            with ENGINE_ERROR_LOCK:
                ENGINE_ERROR=None; ENGINE_ERROR_AT=0.0
            first=False
        except Exception as exc:
            with ENGINE_ERROR_LOCK:
                ENGINE_ERROR=str(exc)[:240]; ENGINE_ERROR_AT=now()
            print(f"[Aetheria engine] {type(exc).__name__}: {str(exc)[:220]}")
            first=False
        STOP.wait(SCAN_SECONDS)


def telemetry_loop():
    while not STOP.is_set():
        flush_telemetry(); STOP.wait(TELEMETRY_FLUSH_SECONDS)


def event_detail(eid):
    con=None
    try:
        con=db_read()
        e=con.execute("""SELECT e.*,a.published primary_published,a.image_url primary_image,a.canonical_url primary_url,a.domain primary_domain,a.description primary_description,
          la.published latest_published,la.image_url latest_image,la.canonical_url latest_url,la.domain latest_domain,la.description latest_description
          FROM events e
          LEFT JOIN articles a ON a.id=e.primary_article_id
          LEFT JOIN articles la ON la.id=e.latest_article_id
          WHERE e.id=?""",(eid,)).fetchone()
        if not e:
            return None
        rows=con.execute("SELECT a.title,a.canonical_url,a.domain,a.tier,a.published,a.image_url,a.language FROM event_articles ea JOIN articles a ON a.id=ea.article_id WHERE ea.event_id=? ORDER BY COALESCE(a.published,a.fetched) DESC",(eid,)).fetchall()
        updates=con.execute("SELECT observed_at,change_type,note FROM event_updates WHERE event_id=? ORDER BY observed_at DESC LIMIT 30",(eid,)).fetchall()
        evidence=evidence_for_event(con,eid)
        local_ai=local_ai_analysis(con,eid)
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None
    finally:
        if con:
            con.close()

    d=dict(e)
    src=[dict(r) for r in rows]
    why=[]
    if d.get("source_count",0)>=2:
        why.append(f"{d['source_count']} independent reports")
    if d.get("official_count",0):
        why.append(f"{d['official_count']} official source{'s' if d['official_count']!=1 else ''}")
    if d.get("significance",0)>=.65:
        why.append("high significance")
    if d.get("financial_relevance",0)>=.5:
        why.append("financial relevance")
    if d.get("geopolitical_relevance",0)>=.5:
        why.append("geopolitical relevance")
    if d.get("supply_chain_relevance",0)>=.5:
        why.append("supply-chain relevance")
    context={"why":why[:4] or ["fresh event activity"],
             "latest_change":updates[0]["note"] if updates else "",
             "affected_domains":[]}
    for flag,label in (("financial_relevance","Markets"),("geopolitical_relevance","Security"),
                       ("supply_chain_relevance","Supply chain"),("india_relevance","India"),
                       ("social_relevance","Public impact")):
        if d.get(flag,0)>=.45:
            context["affected_domains"].append(label)
    context["affected_domains"]=context["affected_domains"][:4]
    sd=_serialize_event(d,{d["id"]:{"published":d.get("latest_published") or d.get("primary_published"),
                                    "latest_published":d.get("latest_published"),
                                    "latest_url":d.get("latest_url"),
                                    "latest_domain":d.get("latest_domain"),
                                    "latest_image_url":d.get("latest_image"),
                                    "latest_description":d.get("latest_description") or "",
                                    "primary_url":d.get("primary_url"),
                                    "primary_domain":d.get("primary_domain"),"image_url":d.get("primary_image"),
                                    "description":d.get("primary_description") or "",
                                    "domains":",".join([x.get("domain","") for x in src]),
                                    "languages":",".join([x.get("language","") for x in src if x.get("language")])}})
    related=[]
    rel_con=None
    try:
        rel_con=db_read()
        for r in related_events(eid):
            rr={"id":r["id"],"title":r["title"],"topic":r["topic"],"status":r["status"],"last_seen":r["last_seen"]}
            try:
                latest_rel=rel_con.execute("""SELECT a.canonical_url url,a.domain,a.published,a.image_url
                                          FROM event_articles ea JOIN articles a ON a.id=ea.article_id
                                          WHERE ea.event_id=? ORDER BY COALESCE(a.published,0) DESC LIMIT 1""",(r["id"],)).fetchone()
                if latest_rel:
                    rr.update({"url":safe_url(latest_rel["url"] or ""),"domain":latest_rel["domain"] or "","published":latest_rel["published"],"image_url":safe_url(latest_rel["image_url"] or "")})
            except Exception:
                pass
            related.append(rr)
    finally:
        if rel_con:
            rel_con.close()
    event_payload=dict(d)
    event_payload.update({
        "latest_url":sd.get("latest_url") or sd.get("url") or "",
        "latest_domain":sd.get("latest_domain") or sd.get("domain") or "",
        "latest_published":sd.get("latest_published") or sd.get("published"),
        "latest_image_url":sd.get("latest_image_url") or sd.get("image_url") or "",
        "intelligence":sd.get("intelligence") or {}
    })
    return {"event":event_payload,"sources":src,"timeline":[dict(r) for r in updates],"ai":None,
            "local_ai":local_ai,"evidence":evidence,"context":context,
            "primary_description":d.get("primary_description") or "",
            "impact_channels":impact_channels(sd),"related":related,"future_watch":future_watch(8),
            "ai_capabilities":intelligence_status()}

def article_stream(limit=60, offset=0, topic="", india=False, world=False):
    """Return a true article-level publication stream.

    This endpoint deliberately uses articles.published for chronology. Event activity
    (last_seen) is returned only as context and never used as the article publication time.
    """
    try:
        limit=max(1,min(int(limit or 60),200))
    except Exception:
        limit=60
    try:
        offset=max(0,int(offset or 0))
    except Exception:
        offset=0
    topic=clean_text(topic).strip()
    con=None
    try:
        con=db_read()
        params=[]
        where=["a.published IS NOT NULL", "length(trim(a.title))>=8"]
        if topic:
            topic_map={"Market":"Markets","Geopolitical":"Geopolitics"}
            topic=topic_map.get(topic,topic)
            where.append("a.topic=?")
            params.append(topic)
        if india:
            where.append("(COALESCE(a.country,'')='IN' OR COALESCE(s.country,'')='IN' OR COALESCE(s.region,'')='IN' OR a.topic IN ('India','Local') OR COALESCE(e.india_relevance,0)>=0.14)")
        if world:
            where.append("(COALESCE(a.country,'')<>'IN' AND COALESCE(s.country,'')<>'IN' AND COALESCE(s.region,'')<>'IN' AND a.topic NOT IN ('India','Local'))")
        sql=f"""SELECT a.id article_id,a.title,a.description,a.canonical_url,a.domain,a.image_url,
                       a.published,a.fetched,a.language,a.country,a.topic,a.tier,
                       s.id source_id,s.name source_name,s.country source_country,s.tier source_tier,
                       ea.event_id,
                       e.status event_status,e.last_seen event_last_seen,e.significance,e.india_relevance,
                       e.financial_relevance,e.supply_chain_relevance,e.geopolitical_relevance,e.social_relevance,
                       e.source_count,e.article_count,e.latest_article_id
                FROM articles a
                LEFT JOIN sources s ON s.id=a.source_id
                LEFT JOIN event_articles ea ON ea.article_id=a.id
                LEFT JOIN events e ON e.id=ea.event_id
                WHERE {' AND '.join(where)}
                ORDER BY a.published DESC, a.fetched DESC
                LIMIT ? OFFSET ?"""
        rows=con.execute(sql,params+[limit,offset]).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            pub=float(d.get("published") or 0)
            out.append({
                "id":d.get("article_id"),
                "article_id":d.get("article_id"),
                "event_id":d.get("event_id"),
                "title":d.get("title") or "",
                "description":(d.get("description") or "")[:PRIMARY_DESCRIPTION_LIMIT],
                "url":safe_url(d.get("canonical_url") or ""),
                "domain":d.get("domain") or "",
                "image_url":safe_url(d.get("image_url") or ""),
                "published":pub,
                "published_utc":datetime.fromtimestamp(pub,timezone.utc).isoformat() if pub else None,
                "fetched":float(d.get("fetched") or 0),
                "language":d.get("language") or "",
                "country":d.get("country") or d.get("source_country") or "",
                "topic":d.get("topic") or "World",
                "tier":d.get("tier") or d.get("source_tier") or "",
                "source":{"id":d.get("source_id"),"name":d.get("source_name") or d.get("domain") or "Unknown","domain":d.get("domain") or "","country":d.get("source_country") or "","tier":d.get("source_tier") or d.get("tier") or ""},
                "event":{"id":d.get("event_id"),"status":d.get("event_status"),"last_seen":float(d.get("event_last_seen") or 0),"significance":float(d.get("significance") or 0),"india_relevance":float(d.get("india_relevance") or 0),"financial_relevance":float(d.get("financial_relevance") or 0),"supply_chain_relevance":float(d.get("supply_chain_relevance") or 0),"geopolitical_relevance":float(d.get("geopolitical_relevance") or 0),"social_relevance":float(d.get("social_relevance") or 0),"sources":int(d.get("source_count") or 0),"article_count":int(d.get("article_count") or 0),"latest_article_id":d.get("latest_article_id")}
            })
        return out
    except Exception as exc:
        print(f"[Aetheria article stream warning] {type(exc).__name__}: {str(exc)[:180]}", flush=True)
        return []
    finally:
        if con:
            con.close()


def _search_temporal_predicates(query):
    q=clean_text(str(query or "")).lower()
    predicates=[]; params=[]
    for m in re.finditer(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b",q):
        try:
            dt=datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),tzinfo=ZoneInfo("Asia/Kolkata"))
            predicates.append("(a.published>=? AND a.published<?)")
            params.extend([dt.timestamp(),(dt+timedelta(days=1)).timestamp()])
        except Exception: pass
    month_map={x.lower():i+1 for i,x in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"])}
    month_map.update({x[:3]:i+1 for i,x in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"])})
    pat=r"\b("+"|".join(month_map.keys())+r")\s+(\d{1,2})(?:\s*,?\s*(20\d{2}))?\b"
    for m in re.finditer(pat,q):
        try:
            year=int(m.group(3) or datetime.now(ZoneInfo("Asia/Kolkata")).year)
            dt=datetime(year,month_map[m.group(1)],int(m.group(2)),tzinfo=ZoneInfo("Asia/Kolkata"))
            predicates.append("(a.published>=? AND a.published<?)")
            params.extend([dt.timestamp(),(dt+timedelta(days=1)).timestamp()])
        except Exception: pass
    for m in re.finditer(r"\b(1[0-2]|0?[1-9]):([0-5]\d)\s*(am|pm)?\b",q):
        try:
            hour=int(m.group(1)); minute=int(m.group(2)); ap=m.group(3)
            if ap=="pm" and hour<12: hour+=12
            if ap=="am" and hour==12: hour=0
            predicates.append("(CAST(strftime('%H',a.published,'unixepoch') AS INTEGER)=? AND CAST(strftime('%M',a.published,'unixepoch') AS INTEGER)=?)")
            params.extend([hour,minute])
        except Exception: pass
    return predicates,params

def search_articles(query,limit=60):
    """Search live article records and return article-level results.
    Publication chronology and source URLs/images come from the same article row.
    """
    q=clean_text(str(query or "")).strip()
    if not q:
        return []
    terms=[t for t in tokens(q) if len(t)>1][:12]
    needles=[q.lower()]+[t for t in terms if t.lower()!=q.lower()]
    temporal_clauses,temporal_params=_search_temporal_predicates(q)
    con=None
    try:
        con=db_read()
        clauses=[]; params=[]
        for needle in needles[:8]:
            like=f"%{needle.lower()}%"
            clauses.append("(lower(a.title) LIKE ? OR lower(COALESCE(a.description,'')) LIKE ? OR lower(COALESCE(a.domain,'')) LIKE ? OR lower(COALESCE(a.topic,'')) LIKE ? OR lower(COALESCE(s.name,'')) LIKE ? OR lower(COALESCE(e.title,'')) LIKE ? OR lower(COALESCE(e.summary,'')) LIKE ? OR lower(COALESCE(e.entities,'')) LIKE ? OR lower(COALESCE(e.locations,'')) LIKE ?)")
            params.extend([like,like,like,like,like,like,like,like,like])
        if temporal_clauses:
            clauses.append("("+" OR ".join(temporal_clauses)+")")
            params.extend(temporal_params)
        if not clauses:
            return []
        sql=f"""SELECT a.id article_id,a.title,a.description,a.canonical_url,a.domain,a.image_url,
                       a.published,a.fetched,a.language,a.country,a.topic,a.tier,
                       s.id source_id,s.name source_name,s.country source_country,s.tier source_tier,
                       ea.event_id,e.status event_status,e.last_seen event_last_seen,e.significance,
                       e.title event_title,e.summary event_summary,e.entities,e.locations,
                       e.india_relevance,e.financial_relevance,e.supply_chain_relevance,
                       e.geopolitical_relevance,e.social_relevance,e.source_count,e.article_count
                FROM articles a
                LEFT JOIN sources s ON s.id=a.source_id
                LEFT JOIN event_articles ea ON ea.article_id=a.id
                LEFT JOIN events e ON e.id=ea.event_id
                WHERE a.published IS NOT NULL AND length(trim(a.title))>=8
                  AND ({' OR '.join(clauses)})
                ORDER BY a.published DESC,a.fetched DESC
                LIMIT ?"""
        rows=con.execute(sql,params+[max(1,min(int(limit or 60),120))]).fetchall()
        out=[]
        seen_articles=set()
        ql=q.lower()
        for r in rows:
            d=dict(r)
            aid=d.get("article_id")
            if aid in seen_articles:
                continue
            seen_articles.add(aid)
            hay=" ".join([str(d.get("title") or ""),str(d.get("description") or ""),str(d.get("domain") or ""),str(d.get("topic") or ""),str(d.get("source_name") or ""),str(d.get("event_title") or ""),str(d.get("event_summary") or ""),str(d.get("entities") or ""),str(d.get("locations") or "")]).lower()
            hits=(3 if ql in hay else 0)+sum(1 for t in terms if t.lower() in hay)
            pub=float(d.get("published") or 0)
            out.append({
                "id":d.get("article_id"),
                "article_id":d.get("article_id"),
                "event_id":d.get("event_id"),
                "title":d.get("title") or "",
                "description":(d.get("description") or "")[:PRIMARY_DESCRIPTION_LIMIT],
                "url":safe_url(d.get("canonical_url") or ""),
                "canonical_url":safe_url(d.get("canonical_url") or ""),
                "domain":d.get("domain") or "",
                "image_url":safe_url(d.get("image_url") or ""),
                "published":pub,
                "published_utc":datetime.fromtimestamp(pub,timezone.utc).isoformat() if pub else None,
                "fetched":float(d.get("fetched") or 0),
                "language":d.get("language") or "",
                "country":d.get("country") or d.get("source_country") or "",
                "topic":d.get("topic") or "World",
                "tier":d.get("tier") or d.get("source_tier") or "",
                "source":{"id":d.get("source_id"),"name":d.get("source_name") or d.get("domain") or "Unknown","domain":d.get("domain") or "","country":d.get("source_country") or "","tier":d.get("source_tier") or d.get("tier") or ""},
                "event":{"id":d.get("event_id"),"status":d.get("event_status"),"last_seen":float(d.get("event_last_seen") or 0),"significance":float(d.get("significance") or 0),"india_relevance":float(d.get("india_relevance") or 0),"financial_relevance":float(d.get("financial_relevance") or 0),"supply_chain_relevance":float(d.get("supply_chain_relevance") or 0),"geopolitical_relevance":float(d.get("geopolitical_relevance") or 0),"social_relevance":float(d.get("social_relevance") or 0),"sources":int(d.get("source_count") or 0),"article_count":int(d.get("article_count") or 0)},
                "score":hits
            })
        return out
    except Exception as exc:
        print(f"[Aetheria article search warning] {type(exc).__name__}: {str(exc)[:180]}",flush=True)
        return []
    finally:
        if con:
            con.close()


def search_events(query,limit=60):
    q=clean_text(str(query or "")).strip()
    if not q or len(q)<1:
        return []
    q_lower=q.lower()
    terms=[x for x in tokens(q) if len(x)>1][:10]
    results_map={}

    # 1. Search in-memory snapshot for instant, fresh matching across all fields
    with SNAPSHOT_LOCK:
        snap_pool=list(SNAPSHOT.get("latest") or []) + list(SNAPSHOT.get("events") or [])
    for e in snap_pool:
        eid=e.get("id")
        if not eid or eid in results_map:
            continue
        hay=" ".join([
            str(e.get("title") or ""),
            str(e.get("summary") or ""),
            str(e.get("topic") or ""),
            str(e.get("domain") or ""),
            " ".join(str(x) for x in (e.get("entities") or [])),
            " ".join(str(x) for x in (e.get("locations") or [])),
            " ".join(str(x) for x in (e.get("key_phrases") or [])),
        ]).lower()
        if q_lower in hay or any(t in hay for t in terms):
            hits=sum(1 for t in terms if t in hay) + (3 if q_lower in hay else 0)
            score=hits*25 + float((e.get("intelligence") or {}).get("confidence") or 0.5)*40 + float((e.get("intelligence") or {}).get("impact") or 0.5)*35
            ec=dict(e)
            ec["score"]=round(score,1)
            results_map[eid]=ec

    # 2. Database search across title, summary, topic, entities, locations, domain
    cutoff=now()-30*86400
    con=None
    try:
        con=db_read()
        is_pg = getattr(con, "is_postgres", False)
        rows=[]
        if terms and not is_pg:
            try:
                match=" OR ".join('"'+t.replace('"','')+'"*' for t in terms)
                rows=con.execute("SELECT e.id FROM event_fts f JOIN events e ON e.id=f.event_id WHERE f MATCH ? AND e.last_seen>? ORDER BY bm25(f) LIMIT 120",(match,cutoff)).fetchall()
            except Exception:
                rows=[]

        clauses=[]; params=[cutoff]
        search_needles = [q_lower] + [t for t in terms if t != q_lower]
        for needle in search_needles[:6]:
            clauses.append("(lower(e.title) LIKE ? OR lower(COALESCE(e.summary,'')) LIKE ? OR lower(COALESCE(e.topic,'')) LIKE ? OR lower(COALESCE(e.entities,'')) LIKE ?)")
            params += [f"%{needle}%"]*4

        try:
            db_rows=con.execute(f"SELECT DISTINCT e.id FROM events e WHERE e.last_seen>? AND ({' OR '.join(clauses)}) ORDER BY e.last_seen DESC LIMIT 120",params).fetchall()
        except Exception as q_exc:
            if is_pg:
                try: con._conn.rollback()
                except Exception: pass
            db_rows=[]

        # Also search articles title for deep match
        if len(db_rows) < 40 and terms:
            try:
                art_clauses = []
                art_params = [cutoff]
                for needle in search_needles[:4]:
                    art_clauses.append("lower(a.title) LIKE ?")
                    art_params.append(f"%{needle}%")
                art_rows = con.execute(f"SELECT DISTINCT ea.event_id as id FROM articles a JOIN event_articles ea ON ea.article_id=a.id JOIN events e ON e.id=ea.event_id WHERE e.last_seen>? AND ({' OR '.join(art_clauses)}) LIMIT 80", art_params).fetchall()
                db_rows.extend(art_rows)
            except Exception:
                if is_pg:
                    try: con._conn.rollback()
                    except Exception: pass

        all_ids=list(dict.fromkeys([r["id"] for r in (rows+db_rows)]))
        needed_ids=[x for x in all_ids if x not in results_map][:80]

        if needed_ids:
            marks=",".join("?" for _ in needed_ids)
            erows=con.execute(f"SELECT * FROM events WHERE id IN ({marks})",needed_ids).fetchall()
            group_fn = "STRING_AGG(DISTINCT a.domain, ',')" if is_pg else "GROUP_CONCAT(DISTINCT a.domain)"
            lang_fn = "STRING_AGG(DISTINCT a.language, ',')" if is_pg else "GROUP_CONCAT(DISTINCT a.language)"
            try:
                meta=con.execute(f"""SELECT ea.event_id,
                  MAX(CASE WHEN a.id=e.primary_article_id THEN a.canonical_url END) primary_url,
                  MAX(CASE WHEN a.id=e.primary_article_id THEN a.domain END) primary_domain,
                  MAX(CASE WHEN a.id=e.primary_article_id THEN a.image_url END) image_url,
                  MAX(CASE WHEN a.id=e.primary_article_id THEN a.published END) published,
                  MAX(CASE WHEN a.id=e.primary_article_id THEN a.description END) description,
                  {group_fn} domains, {lang_fn} languages
                FROM event_articles ea JOIN articles a ON a.id=ea.article_id JOIN events e ON e.id=ea.event_id WHERE ea.event_id IN ({marks}) GROUP BY ea.event_id, e.id, e.primary_article_id""",needed_ids).fetchall()
                meta_map={m["event_id"]:m for m in meta}
            except Exception:
                if is_pg:
                    try: con._conn.rollback()
                    except Exception: pass
                meta_map={}

            for r in erows:
                o=_serialize_event(dict(r),meta_map)
                hay=" ".join([
                    str(o.get("title") or ""),
                    str(o.get("summary") or ""),
                    str(o.get("topic") or ""),
                    str(o.get("domain") or ""),
                    str(o.get("description") or ""),
                ]).lower()
                hits=sum(1 for t in terms if t in hay) + (3 if q_lower in hay else 0)
                o["score"]=round((hits*20+float((o.get("intelligence") or {}).get("confidence") or 0.5)*40+float((o.get("intelligence") or {}).get("impact") or 0.5)*35),1)
                results_map[o["id"]]=o
    except Exception as exc:
        print(f"[Aetheria search warning] {type(exc).__name__}: {str(exc)[:180]}", flush=True)
    finally:
        if con:
            con.close()

    enriched=list(results_map.values())
    enriched.sort(key=lambda x:(x.get("score",0),x.get("last_seen") or x.get("published") or 0),reverse=True)
    return enriched[:max(1,min(60,limit))]


def suggest_events(query, limit=8):
    q=clean_text(str(query or "")).strip()
    if len(q)<1:
        return []
    # Prefer current snapshot so suggestions are instant and never wait on ingestion.
    with SNAPSHOT_LOCK:
        pool=list(SNAPSHOT.get("latest") or SNAPSHOT.get("events") or [])[:600]
    terms=tokens(q)
    scored=[]
    for e in pool:
        title=clean_text(e.get("title") or "")
        hay=clean_text(" ".join([
            str(e.get("title") or ""),str(e.get("summary") or ""),str(e.get("topic") or ""),
            str(e.get("domain") or ""),str(e.get("latest_domain") or ""),
            " ".join(str(x) for x in (e.get("entities") or [])),
            " ".join(str(x) for x in (e.get("locations") or [])),
            " ".join(str(x) for x in (e.get("key_phrases") or []))
        ]))
        hay_tokens=tokens(hay)
        hits=len(terms & hay_tokens) if terms else 0
        prefix=1 if q.lower() in hay.lower() else 0
        if not hits and not prefix:
            continue
        score=(prefix*50)+(hits/max(1,len(terms)))*40+float(e.get("india_lens_score") or 0)*6+float(e.get("velocity") or 0)*4
        scored.append((score,e))
    # When an event headline is translated/summarized differently from the
    # reporting source, look directly at current article titles for suggestions.
    if not scored:
        con=None
        try:
            con=db_read()
            clauses=[]; params=[]
            for t in terms or [q.lower()]:
                clauses.append("(lower(a.title) LIKE ? OR lower(COALESCE(a.description,'')) LIKE ?)")
                params += [f"%{t}%",f"%{t}%"]
            sql="""SELECT DISTINCT e.id
                FROM event_articles ea JOIN articles a ON a.id=ea.article_id
                JOIN events e ON e.id=ea.event_id
                WHERE e.last_seen>? AND (""" + " OR ".join(clauses) + ") ORDER BY e.last_seen DESC LIMIT 60"
            rows=con.execute(sql,[now()-30*86400,*params]).fetchall()
            ids=[r["id"] for r in rows]
            if ids:
                marks=",".join("?" for _ in ids)
                erows=con.execute(f"SELECT * FROM events WHERE id IN ({marks})",ids).fetchall()
                meta=con.execute(f"SELECT ea.event_id, MAX(CASE WHEN a.id=e.primary_article_id THEN a.canonical_url END) primary_url, MAX(CASE WHEN a.id=e.primary_article_id THEN a.domain END) primary_domain, MAX(CASE WHEN a.id=e.primary_article_id THEN a.image_url END) image_url, MAX(CASE WHEN a.id=e.primary_article_id THEN a.published END) published, MAX(CASE WHEN a.id=e.primary_article_id THEN a.description END) description, GROUP_CONCAT(DISTINCT a.domain) domains, GROUP_CONCAT(DISTINCT a.language) languages FROM event_articles ea JOIN articles a ON a.id=ea.article_id JOIN events e ON e.id=ea.event_id WHERE ea.event_id IN ({marks}) GROUP BY ea.event_id",ids).fetchall()
                mm={m["event_id"]:m for m in meta}
                for r in erows:
                    e=_serialize_event(dict(r),mm)
                    title=clean_text(e.get("title") or "")
                    score=12+float(e.get("india_lens_score") or 0)*6+float(e.get("velocity") or 0)*4
                    scored.append((score,e))
        except Exception:
            pass
        finally:
            if con: con.close()
    scored.sort(key=lambda x:x[0],reverse=True)
    return [{"id":e.get("id"),"title":e.get("title"),"topic":e.get("topic"),"status":e.get("status"),"last_seen":e.get("last_seen"),"url":e.get("url"),"domain":e.get("latest_domain") or e.get("domain") or ((e.get("source_domains") or [""])[0])} for _,e in scored[:max(1,min(12,limit))]]


def replay_day(date_str, limit=160):
    try:
        dt=datetime.strptime(str(date_str),"%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    except Exception:
        return {"date":date_str,"events":[],"available":False,"error":"date must be YYYY-MM-DD"}
    start=dt.timestamp(); end=(dt+timedelta(days=1)).timestamp()
    con=None
    try:
        con=db_read()
        rows=con.execute("SELECT * FROM events WHERE last_seen>=? AND last_seen<? ORDER BY last_seen ASC LIMIT ?",(start,end,max(1,min(500,limit)))).fetchall()
        meta_map={}
        ids=[r["id"] for r in rows]
        if ids:
            marks=",".join("?" for _ in ids)
            mrows=con.execute(f"""SELECT ea.event_id,
              MAX(CASE WHEN a.id=e.primary_article_id THEN a.canonical_url END) primary_url,
              MAX(CASE WHEN a.id=e.primary_article_id THEN a.domain END) primary_domain,
              MAX(CASE WHEN a.id=e.primary_article_id THEN a.image_url END) image_url,
              MAX(CASE WHEN a.id=e.primary_article_id THEN a.published END) published,
              MAX(CASE WHEN a.id=e.primary_article_id THEN a.description END) description,
              GROUP_CONCAT(DISTINCT a.domain) domains,
              GROUP_CONCAT(DISTINCT a.language) languages
            FROM event_articles ea JOIN articles a ON a.id=ea.article_id JOIN events e ON e.id=ea.event_id
            WHERE ea.event_id IN ({marks}) GROUP BY ea.event_id, e.id, e.primary_article_id""",ids).fetchall()
            meta_map={r["event_id"]:r for r in mrows}
        events=[_serialize_event(dict(r),meta_map) for r in rows]
        # Preserve chronology and add a compact activity bucket for the UI.
        for e in events:
            e["replay_time"]=e.get("last_seen") or e.get("published")
        return {"date":date_str,"events":events,"available":bool(events),"count":len(events),"timezone":"Asia/Kolkata"}
    except Exception as exc:
        return {"date":date_str,"events":[],"available":False,"error":str(exc)[:200]}
    finally:
        if con: con.close()


def knowledge_gap(eid):
    con=None
    try:
        con=db_read()
        e=con.execute("SELECT * FROM events WHERE id=?",(eid,)).fetchone()
        if not e: return None
        evidence=evidence_for_event(con,eid)
        related=related_events(eid,8)
        old=[r for r in related if float(r.get("last_seen") or 0) < float(e["first_seen"] or now())]
        topic=e["topic"] or "World"
        bridge=[]
        if old:
            bridge=old[:3]
        # Build the gap from observed story context, not canned subject matter.
        reason=[]
        if evidence["independent_sources"]<2: reason.append("This is still an early or single-source story.")
        if evidence["conflicts"]: reason.append("Reporting contains conflicting claims, so the surrounding context matters.")
        if topic in ("Markets","Economy","Business","Finance","Commodities","Energy"): reason.append("Understanding the recent context helps distinguish a new development from normal market movement.")
        elif topic in ("Geopolitics","Politics","World"): reason.append("The recent sequence of events helps explain what changed now.")
        else: reason.append("The recent story chain provides useful context before reading the latest update.")
        background=" ".join(reason)
        return {"event_id":eid,"headline":e["title"],"gap":background,"background":bridge,"evidence":evidence,"ready":bool(bridge or evidence["reports"]>0)}
    except Exception:
        return None
    finally:
        if con: con.close()



# Category-specific adaptive reporting baselines (seconds)
# A Supreme Court case, regulatory probe, or bilateral treaty does not update every 6 hours.
CATEGORY_BASELINES = {
    "Legal": 10 * 86400,          # 10 days natural update cycle
    "Geopolitics": 6 * 86400,     # 6 days natural cycle
    "Business": 4 * 86400,        # 4 days natural cycle
    "Technology": 4 * 86400,      # 4 days natural cycle
    "Markets": 1.5 * 86400,       # 1.5 days natural cycle
    "Sports": 1 * 86400,          # 1 day natural cycle
    "Weather": 0.75 * 86400,      # 18 hours natural cycle
    "Local": 1.5 * 86400,         # 1.5 days natural cycle
    "World": 3 * 86400,           # 3 days natural cycle
    "India": 2 * 86400            # 2 days natural cycle
}

def classify_story_lifecycle(event: dict, updates: list) -> dict:
    t = now()
    first_seen = float(event.get("first_seen") or t)
    last_seen = float(event.get("last_seen") or t)
    source_count = int(event.get("source_count") or len(event.get("source_domains") or []) or 1)
    velocity = float(event.get("velocity") or 0.0)
    status = str(event.get("status") or "DEVELOPING").upper()
    title = str(event.get("title") or "")
    topic = str(event.get("topic") or "World")
    
    time_since_last = max(0.0, t - last_seen)
    total_span = max(0.0, last_seen - first_seen)
    expected_interval = CATEGORY_BASELINES.get(topic, 3 * 86400)
    
    # 1. Story Revival Detection (Adaptive):
    # A story is revived if it had an inactive gap relative to its category baseline
    # and has received fresh corroborating reporting within the last 48 hours.
    is_revived = False
    revived_gap_days = 0
    if len(updates) >= 2 and time_since_last <= 48 * 3600:
        u_times = sorted([float(u.get("observed_at") or 0) for u in updates if u.get("observed_at")], reverse=True)
        if len(u_times) >= 2:
            gap = u_times[0] - u_times[1]
            if gap >= expected_interval * 0.8:
                is_revived = True
                revived_gap_days = max(2, int(gap / 86400))
    elif time_since_last <= 48 * 3600 and (t - first_seen) >= (expected_interval * 2) and source_count >= 3:
        is_revived = True
        revived_gap_days = max(3, int((t - first_seen) / 86400))

    # 2. DIMENSION A: Story Lifecycle State (EMERGING, DEVELOPING, QUIET, REVIVED, RESOLVED)
    # HOT is intentionally decoupled from lifecycle state and tracked under attention_state.
    if status == "RESOLVED":
        lifecycle = "RESOLVED"
    elif is_revived:
        lifecycle = "REVIVED"
    elif total_span < (expected_interval * 0.35) and source_count <= 2:
        lifecycle = "EMERGING"
    elif time_since_last <= expected_interval:
        lifecycle = "DEVELOPING"
    else:
        lifecycle = "QUIET"

    # 3. DIMENSION B: Attention State (LOW, RISING, PEAK, FALLING)
    # Measures current media velocity, acceleration, and cross-source reporting momentum
    if velocity >= 0.35 and source_count >= 5:
        attention_state = "PEAK"
    elif velocity >= 0.18 or (source_count >= 4 and time_since_last <= 86400):
        attention_state = "RISING"
    elif time_since_last > expected_interval * 0.7:
        attention_state = "FALLING"
    else:
        attention_state = "LOW"

    # 4. DIMENSION C: Importance State (LOW, MEDIUM, HIGH, CRITICAL)
    # Decoupled from media attention/hype — reflects real-world impact and policy/legal significance
    intel = event.get("intelligence") or {}
    impact = float(intel.get("impact") or event.get("significance") or 0.5)
    india_lens = float(event.get("india_relevance") or 0.0)
    
    if impact >= 0.78 or (impact >= 0.6 and india_lens >= 0.7):
        importance_state = "CRITICAL"
    elif impact >= 0.52 or india_lens >= 0.48 or source_count >= 5:
        importance_state = "HIGH"
    elif impact >= 0.32:
        importance_state = "MEDIUM"
    else:
        importance_state = "LOW"

    # 5. Why Aetheria is still monitoring (evidence-grounded reason)
    combined_text = f"{title} {topic} {event.get('summary') or ''}".lower()
    if any(k in combined_text for k in ("court", "judge", "verdict", "trial", "bail", "hearing", "sc", "hc", "bench", "litigation")):
        why_monitoring = "Judicial proceedings continuing; formal judgment or subsequent hearing pending."
    elif any(k in combined_text for k in ("talks", "deal", "trade", "bilateral", "summit", "accord", "treaty", "negotiat", "pact")):
        why_monitoring = "Bilateral negotiations ongoing; implementation milestone pending."
    elif any(k in combined_text for k in ("policy", "regulat", "rbi", "sebi", "sec", "approval", "bill", "cabinet", "parliament")):
        why_monitoring = "Regulatory framework or formal gazette notification pending."
    elif any(k in combined_text for k in ("investigat", "probe", "cbi", "ed", "police", "inquiry", "charge", "arrest")):
        why_monitoring = "Investigation continuing; agency submission or inquiry report pending."
    elif any(k in combined_text for k in ("project", "corridor", "metro", "semiconductor", "plant", "expressway", "infra", "facility")):
        why_monitoring = "Project construction timeline and phase milestone approaching."
    elif any(k in combined_text for k in ("market", "stock", "ipo", "merger", "acquisition", "earnings", "securities")):
        why_monitoring = "Corporate action and regulatory clearance timeline pending."
    elif any(k in combined_text for k in ("border", "tensions", "ceasefire", "defense", "military", "treaty", "geopolitic")):
        why_monitoring = "Geopolitical situation remains active; diplomatic monitoring continuing."
    else:
        why_monitoring = "Underlying event remains unresolved; monitoring for verified official updates."

    what_changed = None
    previous_state = None
    if updates:
        latest_u = updates[0]
        what_changed = latest_u.get("note") or latest_u.get("change_type") or "New verified report linked to living event."
        if len(updates) > 1:
            prev_u = updates[1]
            previous_state = prev_u.get("note") or prev_u.get("change_type") or "Story was in previous monitoring baseline."
        else:
            previous_state = "Story entered initial discovery phase."
    else:
        what_changed = event.get("last_reason") or "Recent coverage observed across independent sources."
        previous_state = "Story monitored under standard event tracking."

    days_quiet = max(1, int(time_since_last / 86400))
    ratio = time_since_last / max(86400.0, expected_interval)
    if lifecycle == "QUIET":
        coverage_drop_pct = min(95, max(30, int(35 + (ratio * 25))))
    elif attention_state == "FALLING":
        coverage_drop_pct = min(60, max(20, int(20 + (ratio * 15))))
    else:
        coverage_drop_pct = 0

    return {
        "lifecycle": lifecycle,
        "attention_state": attention_state,
        "importance_state": importance_state,
        "why_monitoring": why_monitoring,
        "what_changed": what_changed,
        "previous_state": previous_state,
        "days_quiet": days_quiet,
        "coverage_drop_pct": coverage_drop_pct,
        "revived_gap_days": revived_gap_days,
        "source_count": source_count,
        "expected_interval": expected_interval,
        "time_since_last_sec": time_since_last
    }


def get_follow_up_data(session: str, client_followed_ids: list | None = None) -> dict:
    t = now()
    followed_set = set(client_followed_ids or [])
    last_checked = t - 86400
    
    con = None
    try:
        con = db()
        if session:
            rows = con.execute("SELECT event_id, followed_at, last_checked FROM user_follows WHERE session=?", (session,)).fetchall()
            for r in rows:
                followed_set.add(str(r["event_id"]))
                if r.get("last_checked"):
                    last_checked = min(last_checked, float(r["last_checked"]))
            con.execute("UPDATE user_follows SET last_checked=? WHERE session=?", (t, session))
            con.commit()
    except Exception:
        pass

    followed_list = list(followed_set)
    active = []
    quiet = []
    revived = []
    recent_changes = []
    
    events_map = {}
    with SNAPSHOT_LOCK:
        for ev in (SNAPSHOT.get("events") or []):
            events_map[str(ev.get("id"))] = ev

    for eid in followed_list:
        ev = events_map.get(eid)
        if not ev and con:
            try:
                row = con.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
                if row: ev = dict(row)
            except Exception: pass
        if not ev: continue
            
        updates = []
        if con:
            try:
                u_rows = con.execute("SELECT observed_at, change_type, note FROM event_updates WHERE event_id=? ORDER BY observed_at DESC LIMIT 5", (eid,)).fetchall()
                updates = [dict(u) for u in u_rows]
            except Exception: pass
                
        meta = classify_story_lifecycle(ev, updates)
        item = {
            "id": ev.get("id"),
            "title": ev.get("title"),
            "topic": ev.get("topic") or "WORLD",
            "first_seen": ev.get("first_seen"),
            "last_seen": ev.get("last_seen"),
            "source_count": ev.get("source_count") or len(ev.get("source_domains") or []) or 1,
            "sources": ev.get("sources") or 1,
            "source_domains": (ev.get("source_domains") or [])[:3],
            "lifecycle": meta["lifecycle"],
            "attention": meta["attention_state"],
            "importance": meta["importance_state"],
            "expected_interval_days": round(meta["expected_interval"] / 86400, 1),
            "why_monitoring": meta["why_monitoring"],
            "what_changed": meta["what_changed"],
            "previous_state": meta["previous_state"],
            "days_quiet": meta["days_quiet"],
            "coverage_drop_pct": meta["coverage_drop_pct"],
            "revived_gap_days": meta["revived_gap_days"],
            "url": ev.get("latest_url") or ev.get("url") or ev.get("canonical_url"),
            "latest_url": ev.get("latest_url") or ev.get("url") or ev.get("canonical_url"),
            "published": ev.get("latest_published") or ev.get("published"),
            "latest_published": ev.get("latest_published") or ev.get("published"),
            "domain": ev.get("latest_domain") or ev.get("domain") or "",
            "summary": ev.get("summary") or ev.get("description")
        }

        ev_last_seen = float(ev.get("last_seen") or 0)
        if ev_last_seen > last_checked:
            recent_changes.append({
                "id": ev.get("id"),
                "title": ev.get("title"),
                "delta": meta["what_changed"],
                "last_seen": ev_last_seen
            })

        if meta["lifecycle"] == "REVIVED":
            revived.append(item)
        elif meta["lifecycle"] == "QUIET":
            quiet.append(item)
        else:
            active.append(item)

    if con:
        try: con.close()
        except Exception: pass

    suggestions = []
    with SNAPSHOT_LOCK:
        candidate_events = SNAPSHOT.get("events") or []
    sorted_candidates = sorted(candidate_events, key=lambda x: (float(x.get("velocity") or 0) * 1.5 + float(x.get("significance") or 0) + min(1.0, float(x.get("sources") or 1)/10)), reverse=True)
    
    for c in sorted_candidates:
        cid = str(c.get("id"))
        if cid in followed_set: continue
        sc = int(c.get("sources") or len(c.get("source_domains") or []) or 1)
        if sc < 2: continue
        suggestions.append({
            "id": cid,
            "title": c.get("title"),
            "topic": c.get("topic") or "WORLD",
            "source_count": sc,
            "source_domains": (c.get("source_domains") or [])[:3],
            "published": c.get("latest_published") or c.get("published") or None,
            "why_suggest": f"{sc} independent sources · High momentum · Ongoing developments",
            "summary": c.get("description") or c.get("summary") or "Observed major event trajectory across independent reporting."
        })
        if len(suggestions) >= 4:
            break

    recent_changes.sort(key=lambda x: x.get("last_seen", 0), reverse=True)
    top_3_changes = recent_changes[:3]
    count_changes = len(recent_changes)
    
    if count_changes > 0:
        summary_sentence = f"Since you last checked, {count_changes} important thing{'s' if count_changes != 1 else ''} changed."
        trailing_sentence = "Nothing else important changed in the stories you're following."
    elif followed_list:
        summary_sentence = "Since you last checked, no new changes were detected."
        trailing_sentence = "All followed stories remain under continuous background monitoring."
    else:
        summary_sentence = "You are not following any stories yet."
        trailing_sentence = "Follow major events to track developments and revivals as they happen."

    return {
        "digest": {
            "count": count_changes,
            "summary_sentence": summary_sentence,
            "trailing_sentence": trailing_sentence,
            "items": top_3_changes
        },
        "active": active,
        "quiet": quiet,
        "revived": revived,
        "suggestions": suggestions,
        "followed_ids": followed_list
    }


def toggle_follow(session: str, event_id: str, action: str = "follow") -> dict:
    t = now()
    try:
        con = db()
        if action == "unfollow":
            con.execute("DELETE FROM user_follows WHERE session=? AND event_id=?", (session, event_id))
            con.commit(); con.close()
            return {"following": False, "event_id": event_id}
        else:
            con.execute("INSERT OR REPLACE INTO user_follows(session, event_id, followed_at, last_seen_change, last_checked) VALUES(?,?,?,?,?)", (session, event_id, t, t, t))
            con.commit(); con.close()
            return {"following": True, "event_id": event_id}
    except Exception as exc:
        return {"following": action != "unfollow", "event_id": event_id, "error": str(exc)}



class Handler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def send_json(self,status,payload,etag=None,send_body=True):
        body=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")
        accept=str(self.headers.get("Accept-Encoding","") if hasattr(self,"headers") and self.headers else "").lower()
        use_gzip="gzip" in accept and len(body)>1024
        if use_gzip:
            body=gzip.compress(body,compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        if use_gzip:
            self.send_header("Content-Encoding","gzip")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Access-Control-Allow-Origin","*")
        if etag: self.send_header("ETag",etag)
        self.end_headers()
        if status!=304 and send_body: self.wfile.write(body)
    def do_POST(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=="/api/follow":
            try:
                n=int(self.headers.get("Content-Length","0"))
                data=json.loads(self.rfile.read(n) or b"{}")
                session=str(data.get("session") or "").strip()
                event_id=str(data.get("event_id") or "").strip()
                action=str(data.get("action") or "follow").strip().lower()
                if not session or not event_id:
                    self.send_json(400,{"ok":False,"error":"session and event_id required"}); return
                res=toggle_follow(session,event_id,action)
                self.send_json(200,{"ok":True,**res}); return
            except Exception as exc:
                self.send_json(500,{"ok":False,"error":str(exc)}); return
        if path=="/api/telemetry":
            try:
                n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}");
                if data.get("event_id") and data.get("action"): queue_telemetry({**data,"at":now()}); self.send_json(202,{"ok":True}); return
            except Exception: pass
            self.send_json(400,{"ok":False}); return
        self.send_json(404,{"ok":False,"error":"not found"})
    def do_HEAD(self):
        self._route_request(send_body=False)

    def do_GET(self):
        self._route_request(send_body=True)

    def _route_request(self, send_body: bool = True):
        p=urllib.parse.urlsplit(self.path); path=p.path
        if path=="/api/version":
            self.send_json(200,{"ok":True,"version":VERSION,"build":"world-experience","started_at":STARTED_AT},send_body=send_body); return
        if path=="/api/health":
            self.send_json(200,{"ok":True,"version":VERSION,"state":system_state()},send_body=send_body); return
        if path in ("/api/bootstrap","/api/news"):
            with SNAPSHOT_LOCK: snap=SNAPSHOT.copy()
            rev=str(snap.get("revision",0)); inm=self.headers.get("If-None-Match")
            if inm and inm.strip('"')==rev:
                self.send_response(304); self.send_header("ETag",f'"{rev}"'); self.end_headers(); return
            has_events=bool(snap.get("events"))
            sys_st=snap.get("state") or system_state()
            is_ready=has_events or bool(sys_st.get("ready"))
            payload={"ok":is_ready,"version":VERSION,"ready":is_ready,"warming_up":not is_ready,"revision":snap.get("revision",0),"updated":datetime.now(timezone.utc).isoformat(),"events":snap.get("events",[]),"flash":snap.get("flash",[]),"important":snap.get("important",[]),"impact":snap.get("impact",[]),"latest":snap.get("latest",[]),"moving":snap.get("moving",[]),"sections":snap.get("sections",[]),"categories":snap.get("categories",[]),"future":snap.get("future",[]),"market":snap.get("market",{}),"home":snap.get("home",{}),"state":sys_st}
            self.send_json(200,payload,rev,send_body=send_body); return
        if path=="/api/articles":
            qs=urllib.parse.parse_qs(p.query)
            limit=qs.get("limit",["60"])[0]
            offset=qs.get("offset",["0"])[0]
            topic=qs.get("topic",[""])[0]
            india=str(qs.get("india",["0"])[0]).lower() in {"1","true","yes"}
            world=str(qs.get("world",["0"])[0]).lower() in {"1","true","yes"}
            rows=article_stream(limit=limit,offset=offset,topic=topic,india=india,world=world)
            self.send_json(200,{"ok":True,"articles":rows,"limit":int(limit) if str(limit).isdigit() else 60,"offset":int(offset) if str(offset).isdigit() else 0},send_body=send_body); return
        if path=="/api/search":
            q=urllib.parse.parse_qs(p.query).get("q",[""])[0]
            self.send_json(200,{"ok":True,"query":q,"results":search_articles(q)},send_body=send_body); return
        if path=="/api/suggest":
            q=urllib.parse.parse_qs(p.query).get("q",[""])[0]; self.send_json(200,{"ok":True,"query":q,"results":suggest_events(q)},send_body=send_body); return
        if path=="/api/replay":
            q=urllib.parse.parse_qs(p.query).get("date",[""])[0]; self.send_json(200,{"ok":True,**replay_day(q)},send_body=send_body); return
        if path=="/api/follow-up":
            qs=urllib.parse.parse_qs(p.query)
            session=(qs.get("session") or [""])[0]
            followed_raw=(qs.get("followed_ids") or [""])[0]
            followed_list=[x.strip() for x in followed_raw.split(",") if x.strip()]
            d=get_follow_up_data(session=session,client_followed_ids=followed_list)
            self.send_json(200,{"ok":True,**d},send_body=send_body); return
        if path=="/api/knowledge-gap/" or path.startswith("/api/knowledge-gap/"):
            eid=path.rsplit("/",1)[-1]; d=knowledge_gap(eid)
            if not d: self.send_json(404,{"ok":False,"error":"event not found"},send_body=send_body); return
            self.send_json(200,{"ok":True,**d},send_body=send_body); return
        if path=="/api/future":
            self.send_json(200,{"ok":True,"events":future_watch(40)},send_body=send_body); return
        if path=="/api/ready":
            with SNAPSHOT_LOCK: ready=bool(SNAPSHOT.get("events"))
            self.send_json(200,{"ok":ready,"version":VERSION,"snapshot_revision":SNAPSHOT.get("revision",0),"events":len(SNAPSHOT.get("events",[]))},send_body=send_body); return
        if path=="/api/market":
            self.send_json(200,{"ok":True,**request_market_refresh(force=False)},send_body=send_body); return
        if path=="/api/intelligence/status":
            self.send_json(200,{"ok":True,**intelligence_status()},send_body=send_body); return
        if path=="/api/deployment":
            self.send_json(200,{"ok":True,"version":VERSION,"host":HOST,"port":PORT,"always_on_ready":True,"admin_access":"Tailscale Serve supported","public_access":"Tailscale Funnel or Cloudflare Tunnel supported","note":"The engine still requires an always-on host; deployment scripts are included in this package."},send_body=send_body); return
        if path=="/api/sources":
            self.send_json(200,{"sources":source_status()},send_body=send_body); return
        if path=="/api/diagnostics":
            self.send_json(200,diagnostics_payload(),send_body=send_body); return
        if path=="/api/perf":
            with SNAPSHOT_LOCK:
                built_at=SNAPSHOT.get("built_at",now())
                age_ms=round((now()-built_at)*1000,1)
                freshest_age=SNAPSHOT.get("freshest_event_age_seconds",0)
                rev=SNAPSHOT.get("revision",0)
                latest_pub=SNAPSHOT.get("latest_article_published_at")
                latest_seen=SNAPSHOT.get("latest_event_last_seen")
                self.send_json(200,{
                    "ok":True,
                    "version":VERSION,
                    "snapshot_revision":rev,
                    "snapshot_age_ms":age_ms,
                    "freshest_event_age_seconds":freshest_age,
                    "latest_article_published_at":datetime.fromtimestamp(latest_pub,timezone.utc).isoformat() if latest_pub else None,
                    "latest_event_last_seen":datetime.fromtimestamp(latest_seen,timezone.utc).isoformat() if latest_seen else None,
                    "events_cached":len(SNAPSHOT.get("events",[])),
                    "workers":MAX_WORKERS
                },send_body=send_body); return
        if path=="/api/state":
            self.send_json(200,{"ok":True,"state":system_state()},send_body=send_body); return
        if path=="/api/event/" or path.startswith("/api/event/"):
            eid=path.rsplit("/",1)[-1]; d=event_detail(eid)
            if not d: self.send_json(404,{"ok":False},send_body=send_body); return
            self.send_json(200,{"ok":True,**d},send_body=send_body); return
        if path in ("/disclaimer", "/disclaimer.html"):
            target = WEB_DIR / "disclaimer.html"
        else:
            safe = path.lstrip("/") or "index.html"
            target = (WEB_DIR / safe).resolve()
            if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
                target = WEB_DIR / "index.html"
        ct = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json"}.get(target.suffix, "application/octet-stream")
        data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type",ct); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(data))); self.end_headers()
        if send_body:
            self.wfile.write(data)
    def log_message(self,fmt,*args): print(f"[Aetheria] {self.address_string()} - {fmt%args}")


def local_ip():
    for target in (("1.1.1.1",80),("8.8.8.8",80)):
        try:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(1); s.connect(target); ip=s.getsockname()[0]; s.close()
            if ip and not ip.startswith("127."): return ip
        except Exception: pass
    return None


STARTED_AT=now()

def main():
    global SOURCE_CONFIG_MTIME
    init_db(); sync_sources()
    try: SOURCE_CONFIG_MTIME=SOURCES_FILE.stat().st_mtime
    except Exception: SOURCE_CONFIG_MTIME=0
    FEED_INVALIDATED.set()
    try:
        rebuild_snapshot()
        print(" INITIAL SNAPSHOT: READY", flush=True)
    except Exception as exc:
        print(f" INITIAL SNAPSHOT: deferred ({type(exc).__name__}: {str(exc)[:160]})", flush=True)
    pc=f"http://127.0.0.1:{PORT}"; ip=local_ip(); lan=f"http://{ip}:{PORT}" if ip else "not detected"
    print("="*74); print(f" AETHERIA CORE {VERSION} — WORLD EXPERIENCE ENGINE"); print("="*74); print(f" Windows PC: {pc}"); print(f" iPhone/LAN: http://{ip}:{PORT}" if ip else " iPhone/LAN: not detected"); print(f" App: {BASE_DIR}"); print(f" DB:  {DB_FILE}"); print(f" Sources: {SOURCES_FILE}"); print(f" Workers: {MAX_WORKERS} · Source timeout: {FEED_TIMEOUT}s · Snapshot: {SNAPSHOT_SECONDS}s · Sources: configured registry"); print(" API: /api/bootstrap /api/search /api/event/<id> /api/diagnostics /api/ready"); print(" AI: Local Aetheria intelligence engine active — evidence, clustering, trust, conflict detection, summarisation and learning."); print(f" Market: observed index/FX/bullion adapters refresh every {int(MARKET_POLL_SECONDS)}s; unavailable values remain unavailable."); print(" Ctrl+C to stop."); print("="*74)
    # Do not block server startup by trying to launch a desktop browser.
    # The browser-open behavior can be explicitly requested by the environment.
    if os.environ.get("AETHERIA_AUTO_OPEN_BROWSER", "0") == "1":
        try: webbrowser.open(pc,new=2)
        except Exception: pass
    try: httpd=ThreadingHTTPServer((HOST,PORT),Handler)
    except OSError as exc:
        print(f"ERROR: could not bind port {PORT}: {exc}", flush=True); print("Stop the previous Aetheria/Python process and start Aetheria again.", flush=True); STOP.set(); return
    print(f" HTTP READY: http://127.0.0.1:{PORT}", flush=True)
    if ip: print(f" LAN READY: http://{ip}:{PORT}", flush=True)
    threading.Thread(target=maintenance_loop,daemon=True,name="aetheria-maintenance").start()
    threading.Thread(target=telemetry_loop,daemon=True,name="aetheria-telemetry").start()
    threading.Thread(target=market_loop,daemon=True,name="aetheria-market").start()
    threading.Thread(target=catalog_loop,daemon=True,name="aetheria-catalog").start()
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        STOP.set(); flush_telemetry(); SOURCE_EXECUTOR.shutdown(wait=False,cancel_futures=True)


if __name__=="__main__": main()
