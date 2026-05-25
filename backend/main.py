from typing import Annotated
import datetime
import secrets
import io
import zipfile
import re
import os
from logging import getLogger
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

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
    try:
        temp = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The date format is incorrect.",
        )
    date=datetime.date(temp.year,temp.month,temp.day)

    nikki = session.exec(select(Nikki).where(Nikki.user_id == current_user.id , Nikki.date==date)).all()
    if nikki_for_client.text=="":
        if len(nikki)==0:
            #更新される日記に何も書いておらず、データベースに該当日記が存在しない場合、ダミーの空の日記データを返す
            nikki=[Nikki(user_id=current_user.id,date=date)]
        else:
            #更新される日記に何も書いておらず、データベースに該当日記が存在する場合、Rowのテキストを空にしたうえで、Rowを削除する
            nikki[0].text=nikki_for_client.text
            session.delete(nikki[0])
    else:
        if len(nikki)==0:
            #更新される日記に何か書かれており、データベースに該当日記が存在しない場合、Rowを新規作成する
            nikki=[Nikki(user_id=current_user.id,date=date,text=nikki_for_client.text)]
            session.add(nikki[0])
        else:
            #更新される日記に何か書かれており、データベースに該当日記が存在しない場合、Rowを更新する
            nikki[0].text=nikki_for_client.text
    
    session.commit()
            
    return nikki_to_json_for_client(nikki[0])


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
                    #print(filename)
                    try:
                        # zip内のファイル名解析(OSによって%mなどが使えない場合があるため標準的なフォーマットを試みる)
                        date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", os.path.splitext(os.path.basename(filename))[0])
                        if date_match:
                            year, month, day = map(int, date_match.groups())
                            date = datetime.date(year, month, day)
                            nikki_text_zip = f.read().decode("utf-8")

                            nikki = session.exec(select(Nikki).where(Nikki.user_id == current_user.id , Nikki.date==date)).all()
                            if len(nikki)==0:
                                session.add(Nikki(user_id=current_user.id,date=date,text=nikki_text_zip))
                            else:
                                nikki[0].text=nikki_text_zip
                        else:
                            pass

                    except Exception as e:
                        logger.error(f"Error parsing filename {filename}: {e}")
                        pass
    
    session.commit()
    
    return {}
