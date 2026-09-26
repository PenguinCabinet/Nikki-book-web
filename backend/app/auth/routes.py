import os
import secrets
from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from sqlmodel import select

from app.storage.database import SessionDep
from app.storage.models import User, UserSession

router = APIRouter()
logger = getLogger(__name__)
LIMIT_USER_LENGTH = 1
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


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


@router.post("/token")
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


@router.post("/register")
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

