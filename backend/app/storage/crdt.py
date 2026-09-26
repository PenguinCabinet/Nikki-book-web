"""Yjs-compatible storage. Callers hold SQLite's write lock until commit."""
from pycrdt import Doc, Text
from sqlmodel import SQLModel, Field, Session
from sqlalchemy import text as sql_text


class CollaborativeDocument(SQLModel, table=True):
    key: str = Field(primary_key=True)
    state: bytes


def lock_writes(session: Session):
    session.execute(sql_text("BEGIN IMMEDIATE"))


def load_document(session: Session, key: str, initial: str):
    stored = session.get(CollaborativeDocument, key)
    doc = Doc({"text": Text()})
    if stored is None:
        doc["text"].insert(0, initial)
    else:
        doc.apply_update(stored.state)
    return doc


def save_document(session: Session, key: str, doc: Doc):
    stored = session.get(CollaborativeDocument, key)
    if stored is None:
        stored = CollaborativeDocument(key=key, state=doc.get_update())
    else:
        stored.state = doc.get_update()
    session.add(stored)


def update_crdt_text_preserving_unchanged_chars(doc: Doc, value: str):
    # 変更のない文字（絵文字を含む）の識別子を維持する。
    old = str(doc["text"])
    start = 0
    while start < min(len(old), len(value)) and old[start] == value[start]:
        start += 1
    end = 0
    while end < min(len(old), len(value)) - start and old[-1-end] == value[-1-end]:
        end += 1
    # pycrdtのテキスト位置はUTF-8のバイト数で指定する。
    offset = len(old[:start].encode("utf-8"))
    stop = len(old[:len(old)-end].encode("utf-8"))
    with doc.transaction():
        if stop > offset:
            del doc["text"][offset:stop]
        added = value[start:len(value)-end if end else len(value)]
        if added:
            doc["text"].insert(offset, added)
