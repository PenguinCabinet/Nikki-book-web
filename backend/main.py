from typing import Annotated
import datetime
import secrets
import uuid
import io
import zipfile
import re
import os
from crdt import CollaborativeDocument, lock_writes, load_document, save_document, replace_text
from pycrdt import Doc, Map
from logging import getLogger
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = getLogger(__name__)
logger.info('system log')

from fastapi import Depends, FastAPI, HTTPException, status, Path, Query, File, UploadFile, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Index, inspect
from sqlmodel import Field, Session, SQLModel, create_engine, select
from dotenv import load_dotenv

load_dotenv()

jst = ZoneInfo("Asia/Tokyo")
scheduler = AsyncIOScheduler(timezone=jst)

def create_template_batch_trigger():
    return CronTrigger(hour=0, minute=0, timezone=jst)

SECRET_KEY = os.getenv("NIKKI_BOOK_SECRET_KEY", None)
if SECRET_KEY is None:
    raise EnvironmentError("NIKKI_BOOK_SECRET_KEY is None")

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

#ユーザー登録数の上限値
LIMIT_USER_LENGTH=1

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

def create_db_and_tables():
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


password_hash = PasswordHash.recommended()

DUMMY_HASH = password_hash.hash("dummypassword")

app = FastAPI()

allow_origins=["http://localhost:5173"]
frontend_url = os.getenv("frontend_url", None)
if frontend_url is not None:
    allow_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    scheduler.add_job(
        apply_nikki_template_to_today_nikki,
        create_template_batch_trigger()
    )
    scheduler.add_job(
        count_habit_keyword_continuations,
        create_template_batch_trigger()
    )

    scheduler.start()

    create_db_and_tables()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

def get_session():
    with Session(engine) as session:
        yield session

def nikki_to_json_for_client(v):
    return {
        "text":v.text
    }

SessionDep = Annotated[Session, Depends(get_session)]

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


def get_user(session: SessionDep, username: str):
    user = session.exec(select(User).where(User.username == username)).all()
    if len(user)==1:
        return user[0]
    elif len(user)>=2:
        logger.error("There are two or more users with the same username.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="",
        )


def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_session_id():
    return secrets.token_urlsafe(32)

async def get_current_user(request: Request, session: SessionDep):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    user_session = session.exec(select(UserSession).where(UserSession.session_id == session_id)).first()
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    
    user = session.get(User, user_session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@app.post("/token")
async def login_for_access_token(
    response: Response,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    session_id = create_session_id()
    new_session = UserSession(session_id=session_id, user_id=user.id)
    session.add(new_session)
    session.commit()
    
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=2147483647,
        samesite="lax",
        secure=(os.getenv("ENV") == "production"),
    )
    return {"status": "success"}

@app.post("/register")
async def register(
    response: Response,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    #登録ユーザー数が上限に達しているかチェック
    user = session.exec(select(User)).all()
    if len(user)>=LIMIT_USER_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_510_NOT_EXTENDED,
            detail="The number of registered users has reached the limit.",
        )

    #同一のユーザーが既に登録されていないか検索
    user = session.exec(select(User).where(User.username == form_data.username)).all()
    if len(user)==0:
        new_user=User(username=form_data.username,hashed_password=password_hash.hash(form_data.password))
        session.add(new_user)
        session.commit()
        session.refresh(new_user) 
    elif len(user)==1:
        pass
    else:
        logger.error("There are two or more users with the same username.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="",
        )

    return await login_for_access_token(response, session, form_data)

@app.put("/nikki/{date_str}", response_model=Nikki_for_client)
async def update_nikki(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    date_str: Annotated[str, Path(title="The date")],
    nikki_for_client: Nikki_for_client
):
    raise HTTPException(409, "Please reload the app to use CRDT synchronization.")


@app.get("/nikki/{date_str}")
async def read_nikki(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    date_str: Annotated[str, Path(title="The date")],
):
    try:
        temp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The date format is incorrect.",
        )
    date=datetime.date(temp.year,temp.month,temp.day)


    nikki = session.exec(select(Nikki).where(Nikki.user_id == current_user.id , Nikki.date==date)).all()

    if len(nikki)==0:
        return nikki_to_json_for_client(Nikki(date=date))
    else:
        return nikki_to_json_for_client(nikki[0])

def nikki_zip_fname_parser(v:str):
    temp = datetime.datetime.strptime(v, '%Y年%m月%d日')

    return datetime.date(temp.year, temp.month, temp.day)

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(exc.errors())
    raise exc

@app.post("/nikki-zip")
async def nikki_upload_zip(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...)
):   
    zip_buffer = io.BytesIO(await file.read())
    
    with zipfile.ZipFile(zip_buffer) as z:
        for filename in z.namelist():
            if filename.endswith(".txt"):
                with z.open(filename) as f:
                    try:
                        date=nikki_zip_fname_parser(os.path.splitext(os.path.basename(filename))[0])
                        nikki_text_zip = f.read().decode("utf-8")

                        with Session(engine) as write_session:
                            lock_writes(write_session)
                            key, row, doc = open_collaborative(write_session, current_user.id, "nikki", date)
                            replace_text(doc, nikki_text_zip)
                            persist_collaborative(write_session, key, row, doc)
                            write_session.commit()

                    except Exception as e:
                        logger.error(f"Error parsing filename {filename}: {e}")
                        pass
    
    session.commit()
    
    return {}

def select_today_nikki_from_template(template:str):
    template_arr=[e.lstrip() for e in template.split("\n") if "▶️" in e]
    return "\n".join(template_arr)

def replace_start_icon_to_unfinished(template:str):
    return template.replace("▶️","・")

@app.put("/template", response_model=Nikki_for_client)
async def update_nikki_template(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    nikki_for_client: Nikki_for_client
):
    raise HTTPException(409, "Please reload the app to use CRDT synchronization.")


@app.get("/template")
async def read_nikki_template(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    nikki_template = session.exec(select(Nikki_template).where(Nikki_template.user_id == current_user.id)).all()

    if len(nikki_template)==0:
        return nikki_to_json_for_client(Nikki_template(date=nikki_template))
    else:
        return nikki_to_json_for_client(nikki_template[0])

#すべてのユーザーに対して、日記テンプレートを今日の日記に適用するバッチ処理
async def apply_nikki_template_to_today_nikki():
    with Session(engine) as session:
        date=datetime.datetime.now(jst).date()
        date_str=date.strftime('%Y-%m-%d')
        users=session.exec(select(User))
        for current_user in users:

            with Session(engine) as write_session:
                lock_writes(write_session)
                key, row, doc = open_collaborative(write_session, current_user.id, "nikki", date)
                template = write_session.exec(select(Nikki_template).where(Nikki_template.user_id == current_user.id)).first()
                addition = replace_start_icon_to_unfinished(select_today_nikki_from_template(template.text if template else ""))
                if addition:
                    previous = str(doc["text"])
                    replace_text(doc, previous + ("\n" if previous and not previous.endswith("\n") else "") + addition)
                    persist_collaborative(write_session, key, row, doc)
                write_session.commit()


@app.get("/sync-identity")
async def sync_identity(current_user: Annotated[User, Depends(get_current_active_user)]):
    from fastapi.responses import JSONResponse
    return JSONResponse({"user_id": current_user.id}, headers={"Cache-Control": "no-store"})


def open_collaborative(session, user_id, kind, date=None):
    if kind == "nikki":
        row = session.exec(select(Nikki).where(Nikki.user_id == user_id, Nikki.date == date)).first()
        row = row if row is not None else Nikki(user_id=user_id, date=date)
        key = f"{user_id}:nikki:{date.isoformat()}"
    elif kind == "template":
        row = session.exec(select(Nikki_template).where(Nikki_template.user_id == user_id)).first()
        row = row if row is not None else Nikki_template(user_id=user_id)
        key = f"{user_id}:template"
    else:
        raise ValueError(f"Unknown collaborative document kind: {kind}")
    return key, row, load_document(session, key, row.text)


def persist_collaborative(session, key, row, doc, _user_id=None):
    save_document(session, key, doc)
    row.text = str(doc["text"])
    session.add(row)


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
    with Session(engine) as session:
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


async def read_sync_payload(request: Request, user_id: int):
    if request.headers.get("X-Sync-User") != str(user_id):
        raise HTTPException(403, "The signed-in account changed. Please reload.")

    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 8 * 1024 * 1024:
            raise HTTPException(413, "Document update too large")
    return bytes(payload)


def apply_sync_payload(doc, payload):
    if not payload:
        return
    try:
        doc.apply_update(payload)
    except BaseException as exc:
        # The Rust decoder may raise a PanicException for malformed input.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise HTTPException(400, "Invalid CRDT update") from exc


async def sync_crdt_document(request, user_id, open_document, persist_document):
    payload = await read_sync_payload(request, user_id)
    with Session(engine) as write_session:
        # SQLite serializes read/merge/write across processes, not just coroutines.
        lock_writes(write_session)
        key, row, doc = open_document(write_session, user_id)
        apply_sync_payload(doc, payload)
        persist_document(write_session, key, row, doc, user_id)
        update = doc.get_update()
        write_session.commit()
    return Response(content=update, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


async def sync_document(request, user_id, kind, date=None):
    def open_document(session, current_user_id):
        return open_collaborative(session, current_user_id, kind, date)

    return await sync_crdt_document(
        request,
        user_id,
        open_document,
        persist_collaborative,
    )


async def sync_habit_document(request, user_id):
    return await sync_crdt_document(
        request,
        user_id,
        open_habit_collaborative,
        persist_habit_collaborative,
    )


@app.post("/nikki/{date_str}/sync")
async def sync_nikki(request: Request, date_str: str, current_user: Annotated[User, Depends(get_current_active_user)]):
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "The date format is incorrect.")
    return await sync_document(request, current_user.id, "nikki", date)


@app.post("/template/sync")
async def sync_template(request: Request, current_user: Annotated[User, Depends(get_current_active_user)]):
    return await sync_document(request, current_user.id, "template")


@app.post("/habit/sync")
async def sync_habit_legacy(current_user: Annotated[User, Depends(get_current_active_user)]):
    raise HTTPException(409, "習慣の同期方式が更新されました。画面を再読み込みしてください。")


@app.post("/habit/v2/sync")
async def sync_habit(request: Request, current_user: Annotated[User, Depends(get_current_active_user)]):
    return await sync_habit_document(request, current_user.id)


@app.get("/{user_name}/habit/{habit_keyword_id}")
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
