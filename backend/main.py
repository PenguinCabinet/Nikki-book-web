from typing import Annotated
import datetime

import jwt
from fastapi import Depends, FastAPI, HTTPException, status, Path, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Field, Session, SQLModel, create_engine, select


# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str
    hashed_password: str

class Nikki(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None
    date: datetime.date
    text: str = Field(default="")

class Nikki_for_client(BaseModel):
    text: str = Field(default="")

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


password_hash = PasswordHash.recommended()

DUMMY_HASH = password_hash.hash("dummypassword")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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


SessionDep = Annotated[Session, Depends(get_session)]

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


def get_user(session: SessionDep, username: str):
    user = session.exec(select(User).where(User.username == username)).all()
    if len(user)==1:
        return user[0]


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: datetime.timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(session: SessionDep,token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(session, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@app.post("/token")
async def login_for_access_token(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me/")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    return current_user


@app.get("/users/me/items/")
async def read_own_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return [{"item_id": "Foo", "owner": current_user.username}]

def nikki_to_json_for_client(v):
    return {
        "text":v.text
    }


@app.put("/nikki/{date_str}", response_model=Nikki_for_client)
async def read_nikki(
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

    nikki = session.exec(select(Nikki).where(Nikki.user_id == current_user.id and Nikki.date==date)).all()
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

    nikki = session.exec(select(Nikki).where(Nikki.user_id == current_user.id and Nikki.date==date)).all()

    if len(nikki)==0:
        return nikki_to_json_for_client(Nikki(date=date))
    else:
        return nikki_to_json_for_client(nikki[0])
