# db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker
from Models import Base

# Создание движка
engine = create_async_engine("sqlite+aiosqlite:///bot.db", echo=False)

# Создание сессии
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Создание таблиц
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
