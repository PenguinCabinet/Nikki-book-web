import asyncio
import datetime
import io
import json
import os
import tempfile
import unittest
import zipfile
import base64
import json
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("NIKKI_BOOK_SECRET_KEY", "test-only")
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from pycrdt import Doc, Map, Text
import main
from app.core.settings import jst
from app.nikki import routes as nikki
from app.habits import routes as habits
from app.storage import database, models
from app.storage.crdt import update_crdt_text_preserving_unchanged_chars


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_engine = database.engine
        database.engine = create_engine(f"sqlite:///{self.directory.name}/test.db", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(database.engine)
        with Session(database.engine) as session:
            for uid in (1, 2):
                session.add(models.User(id=uid, username=str(uid), hashed_password="unused"))
                session.add(models.UserSession(session_id=f"test-{uid}", user_id=uid))
            session.add(models.Nikki(user_id=1, date=datetime.date(2026, 9, 8), text="日記😀\n"))
            session.commit()
        self.client = TestClient(main.app)
        self.client.cookies.set("session_id", "test-1")
        self.path = "/nikki/2026-09-08/sync"

    def tearDown(self):
        self.client.close()
        database.engine.dispose()
        database.engine = self.previous_engine
        self.directory.cleanup()

    def sync(self, doc=None, path=None, user=1):
        response = self.client.post(path or self.path, content=doc.get_update() if doc else b"", headers={"X-Sync-User": str(user)})
        self.assertEqual(response.status_code, 200, response.text if response.status_code != 200 else "")
        result = doc if doc is not None else Doc({"text": Text()})
        result.apply_update(response.content)
        return result

    def test_stale_device_merges_and_retries_after_restart(self):
        phone, pc = self.sync(), self.sync()
        update_crdt_text_preserving_unchanged_chars(phone, "スマホ\n日記😀\n")
        update_crdt_text_preserving_unchanged_chars(pc, "日記😀\nPC\n")
        self.sync(phone)
        database.engine.dispose()  # No in-memory document is needed to recover.
        self.sync(pc)
        self.sync(phone)
        self.assertEqual(str(phone["text"]), "スマホ\n日記😀\nPC\n")
        self.assertEqual(str(pc["text"]), str(phone["text"]))
        self.sync(pc)
        self.assertEqual(self.client.get('/nikki/2026-09-08').json()['text'], str(pc['text']))

    def test_concurrent_transactions_keep_both_edits(self):
        a, b = self.sync(), self.sync()
        update_crdt_text_preserving_unchanged_chars(a, "A日記😀\n")
        update_crdt_text_preserving_unchanged_chars(b, "日記😀\nB")
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(self.sync, [a, b]))
        self.assertEqual(str(self.sync()["text"]), "A日記😀\nB")

    def test_delete_does_not_resurrect_on_stale_sync(self):
        stale, current = self.sync(), self.sync()
        update_crdt_text_preserving_unchanged_chars(current, "")
        self.sync(current)
        self.assertEqual(str(self.sync(stale)["text"]), "")

    def test_unicode_replace(self):
        doc = self.sync()
        for value in ["日記😃\n", "今日は晴れ☀️", "", "👨‍👩‍👧‍👦"]:
            update_crdt_text_preserving_unchanged_chars(doc, value)
            self.assertEqual(str(self.sync(doc)["text"]), value)

    def test_yjs_python_wire_compatibility(self):
        doc = self.sync()
        def javascript_peer(append=""):
            process = subprocess.run(
                ["node", str(Path(__file__).resolve().parent.parent.parent / "frontend/tests/yjs-peer.mjs")],
                input=json.dumps({"update": base64.b64encode(doc.get_update()).decode(), "append": append}),
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            return json.loads(process.stdout)
        js = javascript_peer("スマホ😃")
        doc.apply_update(base64.b64decode(js['update']))
        self.sync(doc)
        self.assertEqual(str(doc['text']), "日記😀\nスマホ😃")
        update_crdt_text_preserving_unchanged_chars(doc, "日記☀️\nスマホ😃")
        self.sync(doc)
        self.assertEqual(javascript_peer()['text'], "日記☀️\nスマホ😃")

    def test_template_and_legacy_put(self):
        template = self.sync(path='/template/sync')
        update_crdt_text_preserving_unchanged_chars(template, "▶️買い物😀")
        self.sync(template, '/template/sync')
        self.assertEqual(self.client.get('/template').json()['text'], "▶️買い物😀")
        asyncio.run(nikki.apply_nikki_template_to_today_nikki())
        today = datetime.datetime.now(jst).date().isoformat()
        self.assertIn("・買い物😀", str(self.sync(path=f'/nikki/{today}/sync')['text']))

    def test_habit_sync_materializes_keywords(self):
        habit = Doc({"habits": Map(), "habitMetadata": Map()})
        habit["habits"]["reading"] = Map({"isPublic": True, "keyword": "読書"})
        habit["habits"]["exercise"] = Map({"isPublic": False, "keyword": "運動"})

        response = self.client.post(
            "/habit/v2/sync",
            content=habit.get_update(),
            headers={"X-Sync-User": "1"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        synchronized = Doc({"habits": Map(), "habitMetadata": Map()})
        synchronized.apply_update(response.content)
        self.assertEqual(
            [item["totalCount"] for item in synchronized["habitMetadata"].values()],
            [0, 0],
        )

        with Session(database.engine) as session:
            keywords = session.exec(
                select(models.HabitKeyword).where(models.HabitKeyword.user_id == 1)
            ).all()

        self.assertEqual(
            {
                synchronized["habits"][sync_id]["keyword"]: item["habitKeywordId"]
                for sync_id, item in synchronized["habitMetadata"].items()
            },
            {keyword.keyword: keyword.id for keyword in keywords},
        )
        self.assertEqual(
            {keyword.keyword: keyword.is_public for keyword in keywords},
            {"読書": True, "運動": False},
        )

        ids = {keyword.keyword: keyword.id for keyword in keywords}
        habit.apply_update(response.content)
        habit["habits"]["reading"]["keyword"] = "読書習慣"
        response = self.client.post(
            "/habit/v2/sync",
            content=habit.get_update(),
            headers={"X-Sync-User": "1"},
        )
        self.assertEqual(response.status_code, 200, response.text)

        with Session(database.engine) as session:
            keywords = session.exec(
                select(models.HabitKeyword).where(models.HabitKeyword.user_id == 1)
            ).all()

        self.assertEqual(
            {keyword.keyword: keyword.id for keyword in keywords},
            {"読書習慣": ids["読書"], "運動": ids["運動"]},
        )

    def test_habit_keyword_count_uses_matching_lines_and_distinct_dates(self):
        with Session(database.engine) as session:
            session.add_all([
                models.HabitKeyword(user_id=1, keyword="読書"),
                models.HabitKeyword(user_id=1, keyword="運動"),
                models.Nikki(user_id=1, date=datetime.date(2026, 9, 1), text="✅ 読書"),
                models.Nikki(user_id=1, date=datetime.date(2026, 9, 2), text="✅ 運動\n読書"),
                models.Nikki(user_id=1, date=datetime.date(2026, 9, 3), text="読書\n✅ 運動"),
                models.Nikki(user_id=1, date=datetime.date(2026, 9, 4), text="✅ 読書"),
                models.Nikki(user_id=1, date=datetime.date(2026, 9, 4), text="✅ 読書"),
            ])
            session.commit()

        habits.recalculate_habit_keyword_total_counts()

        with Session(database.engine) as session:
            keywords = session.exec(
                select(models.HabitKeyword).where(models.HabitKeyword.user_id == 1)
            ).all()

        self.assertEqual(
            {keyword.keyword: keyword.total_count for keyword in keywords},
            {"読書": 2, "運動": 2},
        )

    def test_zip_updates_existing_crdt(self):
        stale = self.sync()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('2026年09月08日.txt', '取り込み😀')
        response = self.client.post('/nikki-zip', files={'file': ('nikki.zip', buffer.getvalue(), 'application/zip')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(self.sync(stale)['text']), '取り込み😀')

    def test_auth_isolation_invalid_payload_and_date(self):
        self.sync()
        self.client.cookies.set('session_id', 'test-2')
        self.assertEqual(self.client.post(self.path, headers={'X-Sync-User':'1'}).status_code, 403)
        self.assertEqual(str(self.sync(user=2)['text']), '')
        self.assertEqual(self.client.post(self.path, content=b'bad', headers={'X-Sync-User':'2'}).status_code, 400)
        self.assertEqual(self.client.post('/nikki/invalid/sync', headers={'X-Sync-User':'2'}).status_code, 400)
        self.client.cookies.clear()
        self.assertEqual(self.client.post(self.path).status_code, 401)


if __name__ == '__main__':
    unittest.main()
