"""Run Alembic migrations on startup.

Handles the one-time transition from init_db() (which we used before
introducing Alembic) to alembic-managed migrations:

  * If the application tables already exist but `alembic_version` does not,
    we stamp HEAD instead of running the initial migration — the schema is
    already there from create_all(), running CREATE TABLE again would fail.
  * Otherwise just `alembic upgrade head`, which is a no-op when already at
    HEAD and runs any pending migrations otherwise.

Intended to be invoked from the Docker entrypoint before uvicorn starts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from src.db import get_engine

log = logging.getLogger("feedbridge.migrate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
APP_TABLE_MARKER = "jd_orders"
ALEMBIC_VERSION_TABLE = "alembic_version"


def main() -> None:
    cfg = Config(str(ALEMBIC_INI))
    tables = inspect(get_engine()).get_table_names()

    if APP_TABLE_MARKER in tables and ALEMBIC_VERSION_TABLE not in tables:
        log.info("Existing schema without alembic_version — stamping head.")
        command.stamp(cfg, "head")

    log.info("alembic upgrade head...")
    command.upgrade(cfg, "head")
    log.info("Migrations complete.")


if __name__ == "__main__":
    main()
