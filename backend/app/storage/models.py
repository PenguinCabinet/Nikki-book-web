import datetime

from pydantic import BaseModel
from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str
    hashed_password: str


class UserSession(SQLModel, table=True):
    session_id: str = Field(primary_key=True)
    user_id: int = Field(index=True)
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class Nikki(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None
    date: datetime.date
    text: str = Field(default="")


class Nikki_template(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None
    text: str = Field(default="")


class HabitKeyword(SQLModel, table=True):
    __tablename__ = "habit_keyword"
    __table_args__ = (Index("ix_habit_keyword_user_sync_id", "user_id", "sync_id", unique=True),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    sync_id: str | None = Field(default=None)
    is_public: bool = Field(default=False)
    total_count: int = Field(default=0)
    keyword: str


class Nikki_for_client(BaseModel):
    text: str = Field(default="")

