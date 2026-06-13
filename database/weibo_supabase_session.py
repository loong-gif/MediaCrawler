import os
import ssl
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .weibo_supabase_models import SupabaseWeiboBase

_supabase_engine = None
_supabase_session_factory = None
_tables_initialized = False


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _load_linked_pooler_parts() -> dict:
    pooler_path = Path(__file__).resolve().parents[1] / "supabase" / ".temp" / "pooler-url"
    if not pooler_path.exists():
        return {}

    raw_url = pooler_path.read_text(encoding="utf-8").strip()
    if not raw_url:
        return {}

    parsed = urlparse(raw_url)
    return {
        "host": parsed.hostname or "",
        "port": parsed.port or 5432,
        "user": parsed.username or "",
        "db_name": parsed.path.lstrip("/") or "postgres",
    }


def _build_supabase_engine():
    linked_parts = _load_linked_pooler_parts()

    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    sslmode = os.getenv("SUPABASE_DB_SSLMODE", "require").strip().lower()
    connect_args = {}

    ssl_arg = _build_ssl_arg(sslmode)
    if ssl_arg is not None:
        connect_args["ssl"] = ssl_arg

    if db_url:
        return create_async_engine(db_url, echo=False, pool_pre_ping=True, connect_args=connect_args)

    host = os.getenv("SUPABASE_DB_HOST", linked_parts.get("host", "")).strip()
    port = int(os.getenv("SUPABASE_DB_PORT", str(linked_parts.get("port", 5432))))
    user = os.getenv("SUPABASE_DB_USER", linked_parts.get("user", "")).strip()
    password = os.getenv("SUPABASE_DB_PWD", os.getenv("SUPABASE_DB_PASSWORD", "")).strip()
    db_name = os.getenv("SUPABASE_DB_NAME", linked_parts.get("db_name", "postgres")).strip()

    if not host or not user or not password or not db_name:
        raise RuntimeError(
            "Supabase connection info is incomplete. "
            "Set SUPABASE_DB_URL or provide SUPABASE_DB_HOST, SUPABASE_DB_USER, SUPABASE_DB_PWD, and SUPABASE_DB_NAME."
        )

    url = URL.create(
        "postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=db_name,
    )
    return create_async_engine(url, echo=False, pool_pre_ping=True, connect_args=connect_args)


def _build_ssl_arg(sslmode: str):
    if sslmode in {"", "disable", "false", "0", "off"}:
        return None

    if sslmode in {"allow", "prefer", "require"}:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    if sslmode in {"verify-ca", "verify-full"}:
        return ssl.create_default_context()

    raise RuntimeError(f"Unsupported SUPABASE_DB_SSLMODE: {sslmode}")


def get_supabase_async_engine():
    global _supabase_engine
    if _supabase_engine is None:
        _supabase_engine = _build_supabase_engine()
    return _supabase_engine


def get_supabase_session_factory():
    global _supabase_session_factory
    if _supabase_session_factory is None:
        engine = get_supabase_async_engine()
        _supabase_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _supabase_session_factory


async def init_supabase_weibo_tables():
    global _tables_initialized
    if _tables_initialized:
        return

    engine = get_supabase_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SupabaseWeiboBase.metadata.create_all)
    _tables_initialized = True


@asynccontextmanager
async def get_supabase_session():
    if _is_truthy(os.getenv("SUPABASE_AUTO_CREATE_TABLES", "false")):
        await init_supabase_weibo_tables()

    session = get_supabase_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
