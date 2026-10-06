"""
AETHERIA DATABASE ADAPTER (db_adapter.py)
----------------------------------------
This module provides a unified database interface for Aetheria.
It acts as a "universal travel adapter":
- Locally (default): Connects to local SQLite (data/aetheria.db) using Python's built-in sqlite3.
- In Cloud (when DATABASE_URL is set): Connects to PostgreSQL (e.g., Neon.tech, Supabase) using psycopg2.

Key features:
1. Translates '?' parameter syntax to '%s' when running on PostgreSQL.
2. Translates SQLite-specific DDL (e.g., 'INTEGER PRIMARY KEY AUTOINCREMENT' -> 'SERIAL PRIMARY KEY').
3. Gracefully handles SQLite-specific PRAGMA and FTS5 statements (safely handled on Postgres).
4. Translates 'INSERT OR IGNORE' and 'INSERT OR REPLACE' into standard PostgreSQL 'ON CONFLICT'.
5. Provides dict-like row access (row["column"] and row[index]) across both engines.
6. Auto-detects environment: 100% backward compatible with local development.
"""

from __future__ import annotations
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

# Read environment settings
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Standardize postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL)


class UniversalRow:
    """
    Wraps a database row so that columns can be accessed either:
    - by column name as a string: row['title']
    - by numeric index: row[0]
    - as a standard dict: dict(row)
    - via .get('col', default)
    Works identical to sqlite3.Row across both SQLite and PostgreSQL.
    """
    def __init__(self, data: dict, description: Optional[list] = None, tuple_data: Optional[tuple] = None):
        self._data = data
        if description and tuple_data:
            self._keys = [d[0] for d in description]
            self._values = tuple_data
        else:
            self._keys = list(data.keys())
            self._values = tuple(data.values())

    def __getitem__(self, key: Union[str, int]) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self) -> List[str]:
        return self._keys

    def values(self) -> Tuple[Any, ...]:
        return self._values

    def items(self):
        return self._data.items()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"UniversalRow({self._data})"


class DatabaseConnection:
    """
    Unified database connection wrapping either sqlite3 or psycopg2.
    """
    def __init__(self, raw_conn, is_postgres: bool = False):
        self._conn = raw_conn
        self.is_postgres = is_postgres

    def _translate_query(self, query: str) -> str:
        """
        Translates query syntax between database engines.
        """
        if not self.is_postgres:
            return query

        q = query.strip()

        # Safely ignore SQLite-specific PRAGMA commands on PostgreSQL
        if q.upper().startswith("PRAGMA "):
            return ""

        # Safely ignore SQLite FTS5 virtual table commands on PostgreSQL
        if "CREATE VIRTUAL TABLE" in q.upper() and "FTS5" in q.upper():
            return ""

        # Translate SQLite AUTOINCREMENT to Postgres SERIAL
        q = re.sub(
            r"(?i)\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
            "SERIAL PRIMARY KEY",
            q
        )

        # Replace '?' parameter placeholders with '%s' for PostgreSQL
        # We do this carefully so we don't replace '?' inside literal quotes,
        # and escape any existing '%' in the query as '%%' so psycopg2 doesn't misinterpret them
        parts = []
        in_single_quote = False
        in_double_quote = False
        for ch in q:
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                parts.append(ch)
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                parts.append(ch)
            elif ch == '?' and not in_single_quote and not in_double_quote:
                parts.append('%s')
            elif ch == '%':
                parts.append('%%')
            else:
                parts.append(ch)
        q = "".join(parts)

        # Translate SQLite-specific INSERT OR IGNORE INTO to standard ON CONFLICT
        if re.match(r"(?i)^INSERT\s+OR\s+IGNORE\s+INTO\s+", q):
            q = re.sub(r"(?i)^INSERT\s+OR\s+IGNORE\s+INTO\s+", "INSERT INTO ", q)
            if "ON CONFLICT" not in q.upper():
                q = q.rstrip(";") + " ON CONFLICT DO NOTHING"

        # Translate SQLite-specific INSERT OR REPLACE INTO system_metrics
        if re.match(r"(?i)^INSERT\s+OR\s+REPLACE\s+INTO\s+system_metrics\b", q):
            q = re.sub(r"(?i)^INSERT\s+OR\s+REPLACE\s+INTO\s+system_metrics\b", "INSERT INTO system_metrics", q)
            if "ON CONFLICT" not in q.upper():
                q = q.rstrip(";") + " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at"

        # Translate SQLite GROUP_CONCAT to PostgreSQL STRING_AGG
        # Two arguments: GROUP_CONCAT(expr, 'sep') -> STRING_AGG(expr, 'sep')
        q = re.sub(r"(?i)\bGROUP_CONCAT\s*\(\s*([^,]+?)\s*,\s*('[^']+'|\"[^\"]+\")\s*\)", r"STRING_AGG(\1, \2)", q)
                # One argument: GROUP_CONCAT(expr) -> STRING_AGG(expr, ',')
        q = re.sub(r"(?i)\bGROUP_CONCAT\s*\(\s*([^\)]+?)\s*\)", r"STRING_AGG(\1, ',')", q)

        # Replace SQLite scalar two‑argument MAX() with PostgreSQL GREATEST()
        # Matches MAX(expr1, expr2) where expr1/expr2 do not contain commas or parentheses.
        q = re.sub(r"(?i)\bMAX\s*\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)", r"GREATEST(\1, \2)", q)

        return q

    def execute(self, query: str, params: Union[tuple, list] = ()):
        sql = self._translate_query(query)
        if not sql:
            return DummyCursor()

        if self.is_postgres:
            cur = self._conn.cursor()
            if params:
                cur.execute(sql, tuple(params))
            else:
                cur.execute(sql.replace("%%", "%"))
            return PostgresCursorWrapper(cur)
        else:
            return self._conn.execute(sql, tuple(params))

    def executemany(self, query: str, seq_of_params):
        sql = self._translate_query(query)
        if not sql:
            return DummyCursor()

        if self.is_postgres:
            cur = self._conn.cursor()
            cur.executemany(sql, seq_of_params)
            return PostgresCursorWrapper(cur)
        else:
            return self._conn.executemany(sql, seq_of_params)

    def executescript(self, script: str):
        if self.is_postgres:
            cur = self._conn.cursor()
            statements = [s.strip() for s in script.split(";") if s.strip()]
            for s in statements:
                translated = self._translate_query(s)
                if translated:
                    try:
                        cur.execute(translated)
                    except Exception as e:
                        print(f"[DB Adapter PG executescript warning]: {e} on: {translated[:80]}")
            self._conn.commit()
        else:
            self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


class DummyCursor:
    """Used when ignoring PRAGMA or FTS5 statements on Postgres."""
    def fetchone(self):
        return None
    def fetchall(self):
        return []
    def fetchmany(self, size=None):
        return []


class PostgresCursorWrapper:
    """
    Wraps psycopg2 cursor to return UniversalRow objects matching sqlite3.Row behavior.
    """
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        desc = self._cur.description
        data = {desc[i][0]: row[i] for i in range(len(desc))}
        return UniversalRow(data, desc, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        desc = self._cur.description
        out = []
        for r in rows:
            data = {desc[i][0]: r[i] for i in range(len(desc))}
            out.append(UniversalRow(data, desc, r))
        return out

    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size) if size else self._cur.fetchmany()
        if not rows:
            return []
        desc = self._cur.description
        out = []
        for r in rows:
            data = {desc[i][0]: r[i] for i in range(len(desc))}
            out.append(UniversalRow(data, desc, r))
        return out

    @property
    def rowcount(self):
        return self._cur.rowcount


def get_db(db_file: Optional[Path] = None, timeout: float = 60.0, query_only: bool = False) -> DatabaseConnection:
    """
    Factory function to obtain a database connection:
    - If DATABASE_URL is set -> connects to PostgreSQL
    - Otherwise -> connects to SQLite file (db_file or default data/aetheria.db)
    """
    if IS_POSTGRES:
        try:
            import psycopg2
            import psycopg2.extensions
        except ImportError:
            raise ImportError(
                "PostgreSQL connection requested via DATABASE_URL, but 'psycopg2' is not installed. "
                "Please run: pip install psycopg2-binary"
            )
        raw_conn = psycopg2.connect(DATABASE_URL, connect_timeout=int(timeout) or 10)
        raw_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
        return DatabaseConnection(raw_conn, is_postgres=True)
    else:
        target = db_file or (Path(__file__).resolve().parent / "data" / "aetheria.db")
        target.parent.mkdir(parents=True, exist_ok=True)
        raw_conn = sqlite3.connect(str(target), timeout=timeout, check_same_thread=False)
        raw_conn.row_factory = sqlite3.Row
        try:
            raw_conn.execute("PRAGMA busy_timeout=60000")
        except Exception:
            pass
        if query_only:
            try:
                raw_conn.execute("PRAGMA query_only=1")
            except Exception:
                pass
        return DatabaseConnection(raw_conn, is_postgres=False)
