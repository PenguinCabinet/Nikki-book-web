import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pycrdt import Doc, Map
from sqlmodel import Session, select

from app.auth.routes import get_current_active_user
from app.core.settings import jst
from app.storage import database
from app.storage.crdt import CollaborativeDocument, lock_writes, save_document
from app.storage.database import SessionDep
from app.storage.models import HabitKeyword, Nikki, User

router = APIRouter()


def open_habit_collaborative(session, user_id):
    key = f"{user_id}:habit:v2"
    stored = session.get(CollaborativeDocument, key)
    doc = Doc({"habits": Map(), "habitMetadata": Map()})
    if stored is not None:
        doc.apply_update(stored.state)
    else:
        # Migrate once from DB rows, preserving IDs even when keywords are duplicates.
        # Keep the old JSON document intact; its broken merge history is not reused.
        keywords = session.exec(
            select(HabitKeyword).where(HabitKeyword.user_id == user_id).order_by(HabitKeyword.id)
        ).all()
        with doc.transaction():
            for order, keyword in enumerate(keywords):
                if keyword.sync_id is None:
                    keyword.sync_id = uuid.uuid4().hex
                    session.add(keyword)
                doc["habits"][keyword.sync_id] = Map({
                    "keyword": keyword.keyword,
                    "isPublic": keyword.is_public,
                    "order": order,
                })
        hydrate_habit_keyword_metadata(session, user_id, doc)
    return key, None, doc


def persist_habit_collaborative(session, key, _row, doc, user_id):
    keywords = parse_habit_keywords(doc)
    replace_habit_keywords(session, user_id, keywords)
    session.flush()
    hydrate_habit_keyword_metadata(session, user_id, doc)
    save_document(session, key, doc)


def parse_habit_keywords(doc):
    keywords = []
    for sync_id, item in doc["habits"].items():
        if not sync_id or len(sync_id) > 128 or not isinstance(item, Map):
            raise HTTPException(400, "習慣キーワードのデータ形式が不正です。")

        keyword = item.get("keyword")
        if not isinstance(keyword, str):
            raise HTTPException(400, "習慣キーワードのデータ形式が不正です。")
        is_public = item.get("isPublic", False)
        if not isinstance(is_public, bool):
            raise HTTPException(400, "習慣キーワードの公開設定が不正です。")

        keywords.append({
            "sync_id": sync_id,
            "keyword": keyword.strip(),
            "is_public": is_public,
        })

    return keywords


def replace_habit_keywords(session: Session, user_id: int, keywords):
    existing_keywords = session.exec(
        select(HabitKeyword).where(HabitKeyword.user_id == user_id)
    ).all()
    existing_by_sync_id = {habit_keyword.sync_id: habit_keyword for habit_keyword in existing_keywords}
    active_ids = {keyword["sync_id"] for keyword in keywords}

    for keyword in keywords:
        habit_keyword = existing_by_sync_id.get(keyword["sync_id"])
        if habit_keyword is not None:
            if habit_keyword.keyword != keyword["keyword"]:
                habit_keyword.total_count = 0
            habit_keyword.keyword = keyword["keyword"]
            habit_keyword.is_public = keyword["is_public"]
            session.add(habit_keyword)
        else:
            session.add(HabitKeyword(user_id=user_id, **keyword))

    for habit_keyword in existing_keywords:
        if habit_keyword.sync_id not in active_ids:
            session.delete(habit_keyword)


def hydrate_habit_keyword_metadata(session: Session, user_id: int, doc):
    habit_keywords = {
        habit_keyword.sync_id: habit_keyword
        for habit_keyword in session.exec(
            select(HabitKeyword).where(HabitKeyword.user_id == user_id)
        )
    }
    # Server-owned values never rewrite editable fields or identify rows by keyword.
    metadata = doc["habitMetadata"]
    with doc.transaction():
        for sync_id in doc["habits"]:
            habit_keyword = habit_keywords.get(sync_id)
            value = {
                "habitKeywordId": habit_keyword.id if habit_keyword else None,
                "totalCount": habit_keyword.total_count if habit_keyword else 0,
            }
            if metadata.get(sync_id) != value:
                metadata[sync_id] = value
        for sync_id in list(metadata):
            if sync_id not in doc["habits"]:
                del metadata[sync_id]


def line_contains_habit_keyword(text: str, keyword: str) -> bool:
    return bool(keyword) and any("✅" in line and keyword in line for line in text.splitlines())


def count_habit_keyword_continuations():
    with Session(database.engine) as session:
        lock_writes(session)
        today = datetime.datetime.now(jst).date()
        diaries_by_user = {}
        for nikki in session.exec(select(Nikki)):
            diaries_by_user.setdefault(nikki.user_id, []).append(nikki)

        for habit_keyword in session.exec(select(HabitKeyword)):
            continued_dates = {
                nikki.date
                for nikki in diaries_by_user.get(habit_keyword.user_id, [])
                if nikki.date <= today
                if line_contains_habit_keyword(nikki.text, habit_keyword.keyword)
            }
            habit_keyword.total_count = len(continued_dates)
            session.add(habit_keyword)

        user_ids = {
            habit_keyword.user_id
            for habit_keyword in session.exec(select(HabitKeyword))
        }
        for user_id in user_ids:
            key, _row, doc = open_habit_collaborative(session, user_id)
            hydrate_habit_keyword_metadata(session, user_id, doc)
            save_document(session, key, doc)

        session.commit()


@router.get("/{user_name}/habit/{habit_keyword_id}")
async def read_public_habit_total_count(
    user_name: str,
    habit_keyword_id: int,
    session: SessionDep,
    response: Response,
):
    total_count = session.exec(
        select(HabitKeyword.total_count)
        .join(User, HabitKeyword.user_id == User.id)
        .where(
            HabitKeyword.id == habit_keyword_id,
            User.username == user_name,
            HabitKeyword.is_public.is_(True),
        )
    ).first()
    if total_count is None:
        raise HTTPException(status_code=404, detail="Habit keyword not found")

    response.headers["Cache-Control"] = "no-store"
    return {"total_count": total_count}

