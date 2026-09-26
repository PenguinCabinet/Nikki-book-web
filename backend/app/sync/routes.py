import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.auth.routes import get_current_user
from app.habits.routes import load_or_migrate_habit_document, persist_habit_collaborative
from app.storage import database
from app.storage.collaborative import load_or_create_nikki_or_template_document, save_nikki_or_template_document_to_session
from app.storage.crdt import lock_writes
from app.storage.models import User

router = APIRouter()


@router.get("/sync-identity")
async def sync_identity(current_user: Annotated[User, Depends(get_current_user)]):
    return JSONResponse({"user_id": current_user.id}, headers={"Cache-Control": "no-store"})


async def read_and_validate_sync_payload(request: Request, user_id: int):
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
        # Rust製デコーダーは不正な入力でPanicExceptionを送出することがある。
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise HTTPException(400, "Invalid CRDT update") from exc


async def sync_crdt_document(request, user_id, open_document, persist_document):
    payload = await read_and_validate_sync_payload(request, user_id)
    with Session(database.engine) as write_session:
        # SQLiteの書き込みロックで、プロセス間の読み込み・マージ・保存を直列化する。
        lock_writes(write_session)
        key, row, doc = open_document(write_session, user_id)
        apply_sync_payload(doc, payload)
        persist_document(write_session, key, row, doc, user_id)
        update = doc.get_update()
        write_session.commit()
    return Response(content=update, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


async def sync_nikki_or_template_document(request, user_id, kind, date=None):
    def open_document(session, current_user_id):
        return load_or_create_nikki_or_template_document(session, current_user_id, kind, date)

    return await sync_crdt_document(
        request,
        user_id,
        open_document,
        save_nikki_or_template_document_to_session,
    )


async def sync_habit_document(request, user_id):
    return await sync_crdt_document(
        request,
        user_id,
        load_or_migrate_habit_document,
        persist_habit_collaborative,
    )


@router.post("/nikki/{date_str}/sync")
async def sync_nikki(request: Request, date_str: str, current_user: Annotated[User, Depends(get_current_user)]):
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "The date format is incorrect.")
    return await sync_nikki_or_template_document(request, current_user.id, "nikki", date)


@router.post("/template/sync")
async def sync_template(request: Request, current_user: Annotated[User, Depends(get_current_user)]):
    return await sync_nikki_or_template_document(request, current_user.id, "template")

@router.post("/habit/v2/sync")
async def sync_habit(request: Request, current_user: Annotated[User, Depends(get_current_user)]):
    return await sync_habit_document(request, current_user.id)

