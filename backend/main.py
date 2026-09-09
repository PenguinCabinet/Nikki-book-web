from typing import Annotated
import datetime
import secrets
import io
import zipfile
import re
import os
from crdt import lock_writes, load_document, save_document, replace_text
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
from sqlmodel import Field, Session, SQLModel, create_engine, select
from dotenv import load_dotenv

load_dotenv()

jst = datetime.timezone(datetime.timedelta(hours=9))
scheduler = AsyncIOScheduler(
    timezone=ZoneInfo("Asia/Tokyo")
)


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
        CronTrigger(hour=0, minute=0)
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
    else:
        row = session.exec(select(Nikki_template).where(Nikki_template.user_id == user_id)).first()
        row = row if row is not None else Nikki_template(user_id=user_id)
        key = f"{user_id}:template"
    return key, row, load_document(session, key, row.text)


def persist_collaborative(session, key, row, doc):
    save_document(session, key, doc)
    row.text = str(doc["text"])
    session.add(row)


async def sync_document(request, user_id, kind, date=None):
    if request.headers.get("X-Sync-User") != str(user_id):
        raise HTTPException(403, "The signed-in account changed. Please reload.")
    # Limit input before parsing it as an untrusted CRDT update.
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 8 * 1024 * 1024:
            raise HTTPException(413, "Document update too large")
    with Session(engine) as write_session:
        # SQLite serializes read/merge/write across processes, not just coroutines.
        lock_writes(write_session)
        key, row, doc = open_collaborative(write_session, user_id, kind, date)
        if payload:
            try:
                doc.apply_update(bytes(payload))
            except BaseException as exc:
                # The Rust decoder may raise a PanicException for malformed input.
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                raise HTTPException(400, "Invalid CRDT update") from exc
        persist_collaborative(write_session, key, row, doc)
        update = doc.get_update()
        write_session.commit()
    return Response(content=update, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


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
