"""
db.connection — PostgreSQL connection manager for PolicyChecker.

Reads POSTGRES_* env vars from .env and provides:
  - get_connection()  → context-managed psycopg2 connection
  - db_health()       → quick connectivity check
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _conn_params() -> dict:
    """Build psycopg2 connection kwargs from environment."""
    return {
        "host":     os.getenv("POSTGRES_HOST", "localhost"),
        "port":     int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname":   os.getenv("POSTGRES_DB", "ait_database"),
        "user":     os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "mysecretpassword"),
    }


@contextmanager
def get_connection():
    """Yield a psycopg2 connection; auto-commit on clean exit, rollback on error."""
    conn = psycopg2.connect(**_conn_params())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_health() -> dict:
    """
    Quick health check.  Returns:
        {"ok": True,  "entities": <count>}   on success
        {"ok": False, "error": "<message>"}  on failure
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check if the students table exists (core table)
                cur.execute(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables"
                    "  WHERE table_name = 'students'"
                    ")"
                )
                tables_exist = cur.fetchone()[0]
                if not tables_exist:
                    return {"ok": True, "entities": 0, "tables_exist": False}

                # Count all entity types
                cur.execute("""
                    SELECT
                        (SELECT COUNT(*) FROM students) +
                        (SELECT COUNT(*) FROM faculty) +
                        (SELECT COUNT(*) FROM staff) +
                        (SELECT COUNT(*) FROM committees)
                """)
                count = cur.fetchone()[0]
                return {"ok": True, "entities": count, "tables_exist": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

