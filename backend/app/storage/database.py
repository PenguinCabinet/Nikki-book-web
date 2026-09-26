from typing import Annotated

from fastapi import Depends
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from app.storage.crdt import CollaborativeDocument  # CRDTのテーブルをSQLModelに登録する。
from app.storage.models import HabitKeyword, Nikki, Nikki_template, User, UserSession

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


def create_and_migrate_database_schema():
    SQLModel.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("habit_keyword")}
    with engine.begin() as connection:
        if "sync_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE habit_keyword ADD COLUMN sync_id TEXT")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_habit_keyword_user_sync_id "
            "ON habit_keyword (user_id, sync_id)"
        )
    if "total_count" not in columns:
        with engine.begin() as connection:
            if "continue_count" in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE habit_keyword ADD COLUMN total_count INTEGER NOT NULL DEFAULT 0"
                )
                connection.exec_driver_sql(
                    "UPDATE habit_keyword SET total_count = continue_count"
                )
            else:
                connection.exec_driver_sql(
                    "ALTER TABLE habit_keyword ADD COLUMN total_count INTEGER NOT NULL DEFAULT 0"
                )
    if "continue_count" in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE habit_keyword DROP COLUMN continue_count")
    if "continued_at" in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE habit_keyword DROP COLUMN continued_at")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE habit_keyword SET total_count = 0 WHERE total_count IS NULL"
        )


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

