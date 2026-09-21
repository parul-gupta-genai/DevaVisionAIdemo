import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from config.config import config

# SQLAlchemy Synchronous Engine
sync_db_url = config.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite:///", "sqlite:///")
is_sqlite = "sqlite" in sync_db_url

engine_kwargs = {"pool_pre_ping": True}
if not is_sqlite:
    engine_kwargs.update({"pool_size": 5, "max_overflow": 10})

try:
    engine = create_engine(sync_db_url, **engine_kwargs)
    # Test connection
    with engine.connect() as conn:
        pass
except Exception:
    # Graceful fallback to SQLite when PostgreSQL is offline/unreachable
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sqlite_file = os.path.join(base_dir, "devavision.db")
    sync_db_url = f"sqlite:///{sqlite_file}"
    is_sqlite = True
    engine_kwargs = {"pool_pre_ping": True}
    engine = create_engine(sync_db_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# SQLAlchemy Asynchronous Engine (For new Auth / Web endpoints)
if is_sqlite:
    sqlite_path = sync_db_url.replace("sqlite:///", "")
    async_db_url = f"sqlite+aiosqlite:///{sqlite_path}"
else:
    async_db_url = config.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
    if "postgres" in async_db_url and "asyncpg" not in async_db_url:
        async_db_url = async_db_url.replace("postgresql://", "postgresql+asyncpg://")

async_is_sqlite = "sqlite" in async_db_url
async_kwargs = {"pool_pre_ping": True}
if not async_is_sqlite:
    async_kwargs.update({"pool_size": 5, "max_overflow": 10})

async_engine = create_async_engine(async_db_url, **async_kwargs)

AsyncSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=async_engine, 
    class_=AsyncSession
)

async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session

# Auto-create tables for SQLite fallback
if is_sqlite:
    try:
        import database.models.models
        import database.models.auth
        import app.plugins.fire.models
        Base.metadata.create_all(bind=engine)
    except Exception as err:
        print(f"Database table creation notice: {err}")

