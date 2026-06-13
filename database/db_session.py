from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from .models import Base
import config
from config.db_config import mysql_db_config, postgres_db_config, sqlite_db_config

# Keep a cache of engines
_engines = {}


async def _ensure_weibo_creator_note_count_column(conn, db_type: str):
    if db_type == "sqlite":
        result = await conn.execute(text("PRAGMA table_info(weibo_creator)"))
        columns = [row[1] for row in result.fetchall()]
        if "note_count" not in columns:
            await conn.execute(text("ALTER TABLE weibo_creator ADD COLUMN note_count INTEGER NOT NULL DEFAULT 0"))
    elif db_type == "mysql":
        result = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'weibo_creator' AND column_name = 'note_count'"
            ),
            {"schema": mysql_db_config["db_name"]},
        )
        if result.scalar_one() == 0:
            await conn.execute(text("ALTER TABLE weibo_creator ADD COLUMN note_count INT NOT NULL DEFAULT 0"))
    elif db_type == "postgres" or db_type == "db":
        result = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'weibo_creator' AND column_name = 'note_count'"
            )
        )
        if result.scalar_one() == 0:
            await conn.execute(text("ALTER TABLE public.weibo_creator ADD COLUMN note_count INTEGER NOT NULL DEFAULT 0"))

    await conn.execute(
        text(
            "UPDATE weibo_creator SET note_count = ("
            "SELECT COUNT(*) FROM weibo_note WHERE weibo_note.user_id = weibo_creator.user_id"
            ")"
        )
    )


async def create_database_if_not_exists(db_type: str):
    """
    尝试创建数据库（如果不存在）。
    如果用户没有创建数据库的权限，会捕获异常并返回False。
    返回True表示数据库已存在或创建成功，False表示创建失败（通常是因为权限不足）。
    """
    try:
        if db_type == "mysql":
            # Connect to the server without a database
            server_url = f"mysql+asyncmy://{mysql_db_config['user']}:{mysql_db_config['password']}@{mysql_db_config['host']}:{mysql_db_config['port']}"
            engine = create_async_engine(server_url, echo=False)
            async with engine.connect() as conn:
                await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {mysql_db_config['db_name']}"))
            await engine.dispose()
            return True
        elif db_type == "postgres" or db_type == "db":
            # 尝试连接到postgres数据库来创建目标数据库
            # 如果连接失败（权限问题），则跳过创建步骤
            try:
                # 尝试连接到postgres数据库（默认数据库）
                server_url = f"postgresql+asyncpg://{postgres_db_config['user']}:{postgres_db_config['password']}@{postgres_db_config['host']}:{postgres_db_config['port']}/postgres"
                engine = create_async_engine(server_url, echo=False, isolation_level="AUTOCOMMIT")
                async with engine.connect() as conn:
                    # Check if database exists
                    result = await conn.execute(
                        text(f"SELECT 1 FROM pg_database WHERE datname = '{postgres_db_config['db_name']}'")
                    )
                    row = result.fetchone()
                    if not row:
                        # Create database if it doesn't exist
                        try:
                            await conn.execute(text(f"CREATE DATABASE {postgres_db_config['db_name']}"))
                        except Exception as create_error:
                            # 如果创建失败（通常是权限问题），记录警告但继续
                            from tools import utils
                            utils.logger.warning(
                                f"无法创建数据库 {postgres_db_config['db_name']}: {create_error}. "
                                f"请确保数据库已存在，或联系数据库管理员创建数据库。"
                            )
                            await engine.dispose()
                            return False
                await engine.dispose()
                return True
            except Exception as connect_error:
                # 如果无法连接到postgres数据库（可能是权限问题或配置问题），跳过创建步骤
                from tools import utils
                utils.logger.warning(
                    f"无法连接到postgres数据库来检查/创建目标数据库: {connect_error}. "
                    f"将尝试直接连接到目标数据库 {postgres_db_config['db_name']}。"
                )
                return False
    except Exception as e:
        # 捕获所有异常，记录警告
        from tools import utils
        utils.logger.warning(
            f"创建数据库时出错: {e}. 将尝试直接连接现有数据库。"
        )
        return False


def get_async_engine(db_type: str = None):
    if db_type is None:
        db_type = config.SAVE_DATA_OPTION

    if db_type in _engines:
        return _engines[db_type]

    if db_type in ["json", "csv"]:
        return None

    if db_type == "sqlite":
        db_url = f"sqlite+aiosqlite:///{sqlite_db_config['db_path']}"
    elif db_type == "mysql":
        db_url = f"mysql+asyncmy://{mysql_db_config['user']}:{mysql_db_config['password']}@{mysql_db_config['host']}:{mysql_db_config['port']}/{mysql_db_config['db_name']}"
    elif db_type == "postgres" or db_type == "db":
        db_url = f"postgresql+asyncpg://{postgres_db_config['user']}:{postgres_db_config['password']}@{postgres_db_config['host']}:{postgres_db_config['port']}/{postgres_db_config['db_name']}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

    engine = create_async_engine(db_url, echo=False)
    _engines[db_type] = engine
    return engine


async def create_tables(db_type: str = None):
    if db_type is None:
        db_type = config.SAVE_DATA_OPTION
    await create_database_if_not_exists(db_type)
    engine = get_async_engine(db_type)
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _ensure_weibo_creator_note_count_column(conn, db_type)


# Track if tables have been created to avoid repeated checks
_tables_created = set()

@asynccontextmanager
async def get_session() -> AsyncSession:
    db_type = config.SAVE_DATA_OPTION
    # Ensure database exists before creating engine
    if db_type not in ["json", "csv", "sqlite"]:
        await create_database_if_not_exists(db_type)
    
    engine = get_async_engine(db_type)
    if not engine:
        yield None
        return
    
    # Auto-create tables if not already created for this db_type
    if db_type not in _tables_created:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await _ensure_weibo_creator_note_count_column(conn, db_type)
            _tables_created.add(db_type)
        except Exception as e:
            # If table creation fails, log but continue (tables might already exist)
            from tools import utils
            utils.logger.warning(f"创建表时出错（表可能已存在）: {e}")
            _tables_created.add(db_type)  # Mark as created to avoid repeated attempts
    
    AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
        # 记录提交成功（仅在DEBUG模式下）
        from tools import utils
        if hasattr(utils, 'logger'):
            utils.logger.debug(f"[get_session] 事务提交成功 (db_type={db_type})")
    except Exception as e:
        await session.rollback()
        from tools import utils
        if hasattr(utils, 'logger'):
            utils.logger.error(f"[get_session] 事务回滚: {e}")
        raise e
    finally:
        await session.close()
