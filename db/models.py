from datetime import datetime, timezone

import pytz
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import Column, BigInteger, Text, ForeignKey, Boolean, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from config import MSK

DATABASE_URL = "postgresql+asyncpg://postgres:Пароль от БД@127.0.0.1:5432/Имя БД"
engine = create_async_engine(DATABASE_URL, echo=False)

Base = declarative_base()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, dict: dict):
        async with async_session() as session:
            dict["session"] = session
            return await handler(event, dict)


class Mailings(Base):
    __tablename__ = "mailings"
    id = Column(BigInteger, primary_key=True)
    text = Column(Text)
    media = Column(Text)
    per = Column(Text)
    globalper = Column(Text)
    status = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(MSK))
    last_sent = Column(DateTime(timezone=True), nullable=True)
    last_message_id = Column(BigInteger, nullable=True)

    buttons = relationship("Buttons", backref="mailing", cascade="all, delete-orphan")

class Buttons(Base):
    __tablename__ = "buttons"
    id = Column(BigInteger, primary_key=True)
    mailing_id = Column(BigInteger, ForeignKey("mailings.id"), nullable=False)
    text = Column(Text)
    url = Column(Text)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
