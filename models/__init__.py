import os

from dotenv import load_dotenv
from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, Unicode
from sqlalchemy.dialects.postgresql import HSTORE
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql.functions import now

load_dotenv()

Base = declarative_base()


class Clown(Base):
    __tablename__ = "clowns"
    guild_id: int = Column(BigInteger, primary_key=True)
    clown_id: int = Column(BigInteger)
    previous_clown_id: int = Column(BigInteger)
    nomination_date: Date = Column(Date, server_default=now(), server_onupdate=now())
    join_time: DateTime = Column(DateTime(timezone=True), server_default=now(), server_onupdate=now())


class Reminder(Base):
    __tablename__ = "reminders"
    reminder_id: int = Column(Integer, primary_key=True)
    reminder_text: str = Column(Unicode)
    reminder_time: DateTime = Column(DateTime(timezone=True))
    user_id: int = Column(BigInteger)
    channel_id: int = Column(BigInteger)


class Nickname(Base):
    __tablename__ = "nicknames"
    guild_id: int = Column(BigInteger, primary_key=True)
    nicknames: dict = Column(MutableDict.as_mutable(HSTORE), nullable=False, default={}, server_default="")


user = os.environ.get("POSTGRES_USER")
pw = os.environ.get("POSTGRES_PASSWORD")
db = os.environ.get("POSTGRES_DB")
db_host = os.environ.get("POSTGRES_HOST")
db_port = os.environ.get("POSTGRES_PORT")
database_url = os.environ.get("DATABASE_URL") or f"postgresql+asyncpg://{user}:{pw}@{db_host}:{db_port}/{db}"
if database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif os.environ.get("DATABASE_URL") is None:
    if None in (user, pw, db, db_host, db_port):
        raise ValueError("Missing database environment variable")

engine = create_async_engine(
    database_url,
    # echo=True,
    future=True,
)
async_session = sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession, future=True)
