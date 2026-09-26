from sqlmodel import select

from app.storage.crdt import load_document, save_document
from app.storage.models import Nikki, Nikki_template


def load_or_create_nikki_or_template_document(session, user_id, kind, date=None):
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


def save_nikki_or_template_document_to_session(session, key, row, doc, _user_id=None):
    save_document(session, key, doc)
    row.text = str(doc["text"])
    session.add(row)

