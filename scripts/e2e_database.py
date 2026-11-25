#!/usr/bin/env python3
"""Create or drop the disposable PostgreSQL database used by browser (end-to-end) test runs.

The name is fixed to ``positron_e2e`` and cannot be changed: this script must never be able to
touch positron_db, agenda_db or any other database in the shared container.

    python scripts/e2e_database.py reset   # drop if present, then create empty
    python scripts/e2e_database.py drop    # remove it after the run

Then start an instance against it, e.g.:
    PG_LOCAL_DATABASE=positron_e2e BACKEND_PORT=8031 EMAIL_ENABLED=false python start_server.py --build
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

E2E_DATABASE = "positron_e2e"  # fixed on purpose
ROOT = Path(__file__).resolve().parent.parent


def connect() -> psycopg.Connection:
    """Maintenance connection (database "postgres") with the local container credentials."""
    load_dotenv(ROOT / ".env")
    return psycopg.connect(
        host=os.getenv("PG_LOCAL_HOST", "localhost"), port=int(os.getenv("PG_LOCAL_PORT", "5432")),
        user=os.environ["PG_LOCAL_USER"], password=os.environ["PG_LOCAL_PASSWORD"],
        dbname="postgres", autocommit=True, connect_timeout=5,
    )


def drop(connection: psycopg.Connection) -> None:
    connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(E2E_DATABASE)))


def create(connection: psycopg.Connection) -> None:
    connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(E2E_DATABASE)))


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Manage the disposable {E2E_DATABASE} database.")
    parser.add_argument("action", choices=["reset", "drop"])
    args = parser.parse_args()
    with connect() as connection:
        drop(connection)
        if args.action == "reset":
            create(connection)
    print(f"{E2E_DATABASE}: {'recreated empty' if args.action == 'reset' else 'dropped'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
