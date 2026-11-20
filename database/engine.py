from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from database.config import get_db_settings
from functools import lru_cache
@lru_cache
def get_engine()->Engine:
    settings = get_db_settings()
    url = (
        f"postgresql+psycopg2://{settings['pguser']}:{settings['pgpassword']}"
        f"@{settings['pghost']}:{settings['pgport']}/{settings['pgdb']}"
    )
    # 10 + 20 connections per process; Postgres allows 100 in total, so keep processes x 30 below that (plan, phase 6)
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20, pool_timeout=30, echo=False)
