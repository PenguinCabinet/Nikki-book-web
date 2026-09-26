import datetime
import io
import os
import zipfile
from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from sqlmodel import Session, select

from app.auth.routes import get_current_active_user
from app.core.settings import jst
from app.storage import database
from app.storage.collaborative import open_collaborative, persist_collaborative
from app.storage.crdt import lock_writes, replace_text
from app.storage.database import SessionDep
from app.storage.models import Nikki, Nikki_for_client, Nikki_template, User

router = APIRouter()
logger = getLogger(__name__)


def nikki_to_json_for_client(v):
    return {
        "text":v.text
    }


@router.put("/nikki/{date_str}", response_model=Nikki_for_client)
async def update_nikki(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    date_str: Annotated[str, Path(title="The date")],
    nikki_for_client: Nikki_for_client
):
    raise HTTPException(409, "Please reload the app to use CRDT synchronization.")


@router.get("/nikki/{date_str}")
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


@router.post("/nikki-zip")
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

                        with Session(database.engine) as write_session:
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


@router.put("/template", response_model=Nikki_for_client)
async def update_nikki_template(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    nikki_for_client: Nikki_for_client
):
    raise HTTPException(409, "Please reload the app to use CRDT synchronization.")


@router.get("/template")
async def read_nikki_template(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    nikki_template = session.exec(select(Nikki_template).where(Nikki_template.user_id == current_user.id)).all()

    if len(nikki_template)==0:
        return nikki_to_json_for_client(Nikki_template(date=nikki_template))
    else:
        return nikki_to_json_for_client(nikki_template[0])


async def apply_nikki_template_to_today_nikki():
    with Session(database.engine) as session:
        date=datetime.datetime.now(jst).date()
        date_str=date.strftime('%Y-%m-%d')
        users=session.exec(select(User))
        for current_user in users:

            with Session(database.engine) as write_session:
                lock_writes(write_session)
                key, row, doc = open_collaborative(write_session, current_user.id, "nikki", date)
                template = write_session.exec(select(Nikki_template).where(Nikki_template.user_id == current_user.id)).first()
                addition = replace_start_icon_to_unfinished(select_today_nikki_from_template(template.text if template else ""))
                if addition:
                    previous = str(doc["text"])
                    replace_text(doc, previous + ("\n" if previous and not previous.endswith("\n") else "") + addition)
                    persist_collaborative(write_session, key, row, doc)
                write_session.commit()

