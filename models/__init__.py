import os

from dotenv import load_dotenv
from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, Unicode
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql.functions import now

load_dotenv()

Base = declarative_base()


class Clown(Base):
    __tablename__ = "clowns"
    guild_id = Column(BigInteger, primary_key=True)
    clown_id = Column(BigInteger)
    previous_clown_id = Column(BigInteger)
    nomination_date = Column(Date, server_default=now(), server_onupdate=now())
    join_time = Column(DateTime(timezone=True), server_default=now(), server_onupdate=now())


class Reminder(Base):
    __tablename__ = "reminders"
    reminder_id = Column(Integer, primary_key=True)
    reminder_text = Column(Unicode)
    reminder_time = Column(DateTime(timezone=True))
    user_id = Column(BigInteger)
    channel_id = Column(BigInteger)


user = os.environ.get("POSTGRES_USER")
pw = os.environ.get("POSTGRES_PASSWORD")
db_host = os.environ.get("POSTGRES_HOST")
db_port = os.environ.get("POSTGRES_PORT")
database_url = os.environ.get("DATABASE_URL") or f"postgresql+asyncpg://{user}:{pw}@{db_host}{db_port}/{user}"
if database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    database_url,
    # echo=True,
    future=True,
)
async_session = sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession, future=True)
