import base64
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

os.environ.setdefault("NIKKI_BOOK_SECRET_KEY", "test-only")
from fastapi.testclient import TestClient
from pycrdt import Doc, Map
from sqlmodel import Session, SQLModel, create_engine, select
import main
from crdt import CollaborativeDocument


def habit_doc():
    return Doc({"habits": Map(), "habitMetadata": Map()})


class HabitSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_engine = main.engine
        main.engine = create_engine(f"sqlite:///{self.directory.name}/test.db", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(main.engine)
        with Session(main.engine) as session:
            for user_id in (1, 2):
                session.add(main.User(id=user_id, username=str(user_id), hashed_password="unused"))
                session.add(main.UserSession(session_id=f"test-{user_id}", user_id=user_id))
            session.commit()
        self.client = TestClient(main.app)
        self.client.cookies.set("session_id", "test-1")

    def tearDown(self):
        self.client.close()
        main.engine.dispose()
        main.engine = self.previous_engine
        self.directory.cleanup()

    def post(self, doc):
        response = self.client.post("/habit/v2/sync", content=doc.get_update(), headers={"X-Sync-User": "1"})
        self.assertEqual(response.status_code, 200, response.text if response.status_code != 200 else "")
        return response.content

    def sync(self, doc=None):
        doc = doc if doc is not None else habit_doc()
        doc.apply_update(self.post(doc))
        return doc

    def add(self, doc, key, keyword=""):
        doc["habits"][key] = Map({"keyword": keyword, "isPublic": False, "order": 1})

    def rows(self):
        with Session(main.engine) as session:
            return session.exec(select(main.HabitKeyword).order_by(main.HabitKeyword.id)).all()

    def test_edit_before_create_response_and_retry_keep_one_id(self):
        doc = self.sync()
        self.add(doc, "draft", "読")
        delayed_response = self.post(doc)
        first_id = self.rows()[0].id
        doc["habits"]["draft"]["keyword"] = "読書😀"
        doc.apply_update(delayed_response)
        self.assertEqual(doc["habits"]["draft"]["keyword"], "読書😀")
        for _ in range(3):
            self.sync(doc)
            self.assertEqual(doc["habitMetadata"]["draft"]["habitKeywordId"], first_id)
        self.assertEqual([(row.id, row.keyword) for row in self.rows()], [(first_id, "読書😀")])

    def test_blank_rows_and_clear_then_retype_keep_identity(self):
        doc = self.sync()
        self.add(doc, "a")
        self.add(doc, "b")
        self.sync(doc)
        self.assertEqual(set(doc["habits"]), {"a", "b"})
        self.assertEqual(self.rows(), [])
        doc["habits"]["a"]["keyword"] = "読書"
        self.sync(doc)
        first_id = self.rows()[0].id
        doc["habits"]["a"]["keyword"] = ""
        self.sync(doc)
        main.count_habit_keyword_continuations()
        doc["habits"]["a"]["keyword"] = "運動"
        self.sync(doc)
        self.assertEqual([(row.id, row.keyword) for row in self.rows()], [(first_id, "運動")])
        self.assertEqual(set(doc["habits"]), {"a", "b"})

    def test_duplicate_keywords_have_distinct_stable_database_ids(self):
        doc = self.sync()
        self.add(doc, "a", "読書")
        self.add(doc, "b", "読書")
        self.sync(doc)
        ids = {key: value["habitKeywordId"] for key, value in doc["habitMetadata"].items()}
        self.assertEqual(len(set(ids.values())), 2)
        doc["habits"]["a"]["isPublic"] = True
        self.sync(doc)
        self.assertEqual(ids, {key: value["habitKeywordId"] for key, value in doc["habitMetadata"].items()})
        self.assertEqual({row.sync_id: row.is_public for row in self.rows()}, {"a": True, "b": False})

    def test_concurrent_additions_and_fields_merge_without_lost_rows(self):
        pc, phone = self.sync(), self.sync()
        self.add(pc, "pc", "読書")
        self.add(phone, "phone", "運動")
        self.sync(pc)
        self.sync(phone)
        self.sync(pc)
        pc["habits"]["pc"]["keyword"] = "読書習慣"
        phone["habits"]["pc"]["isPublic"] = True
        self.sync(pc)
        self.sync(phone)
        self.sync(pc)
        self.assertEqual(pc["habits"].to_py(), phone["habits"].to_py())
        self.assertEqual(pc["habits"]["pc"]["keyword"], "読書習慣")
        self.assertTrue(pc["habits"]["pc"]["isPublic"])
        self.assertEqual(len(self.rows()), 2)

    def test_delete_wins_against_stale_edits_and_retries(self):
        current = self.sync()
        self.add(current, "a", "読書")
        self.sync(current)
        stale = self.sync()
        del current["habits"]["a"]
        self.sync(current)
        stale["habits"]["a"]["keyword"] = "読書習慣"
        for _ in range(2):
            self.sync(stale)
            self.assertEqual(len(stale["habits"]), 0)
            self.assertEqual(self.rows(), [])

    def test_batch_metadata_does_not_overwrite_in_flight_edits(self):
        doc = self.sync()
        self.add(doc, "a", "読書")
        self.sync(doc)
        with Session(main.engine) as session:
            session.add(main.Nikki(user_id=1, date=datetime.date(2020, 1, 1), text="✅ 読書\n✅ 読書"))
            session.commit()
        main.count_habit_keyword_continuations()
        doc["habits"]["a"]["isPublic"] = True
        self.sync(doc)
        self.assertEqual(doc["habitMetadata"]["a"]["totalCount"], 1)
        self.assertTrue(doc["habits"]["a"]["isPublic"])

    def test_migration_preserves_database_ids_counts_and_old_document(self):
        with Session(main.engine) as session:
            session.add_all([
                main.HabitKeyword(id=41, user_id=1, keyword="読書", total_count=4),
                main.HabitKeyword(id=42, user_id=1, keyword="読書", total_count=4),
                CollaborativeDocument(key="1:habit", state=b"legacy-state-kept"),
            ])
            session.commit()
        doc = self.sync()
        self.assertEqual({item["habitKeywordId"] for item in doc["habitMetadata"].values()}, {41, 42})
        self.assertEqual([item["totalCount"] for item in doc["habitMetadata"].values()], [4, 4])
        self.sync(doc)
        self.assertEqual([row.id for row in self.rows()], [41, 42])
        with Session(main.engine) as session:
            self.assertEqual(session.get(CollaborativeDocument, "1:habit").state, b"legacy-state-kept")
        self.assertEqual(self.client.post("/habit/sync").status_code, 409)

    def test_schema_upgrade_is_repeatable_and_preserves_rows(self):
        with main.engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX ix_habit_keyword_user_sync_id")
            connection.exec_driver_sql("ALTER TABLE habit_keyword DROP COLUMN sync_id")
            connection.exec_driver_sql("INSERT INTO habit_keyword (id, user_id, is_public, keyword, total_count) VALUES (9, 1, 0, 'test', 7)")
        main.create_db_and_tables()
        main.create_db_and_tables()
        self.assertEqual([(row.id, row.total_count) for row in self.rows()], [(9, 7)])
        doc = self.sync()
        self.assertEqual(next(iter(doc["habitMetadata"].values()))["habitKeywordId"], 9)

    def test_invalid_update_rolls_back_and_metadata_cannot_select_another_users_row(self):
        doc = self.sync()
        self.add(doc, "a", "読書")
        self.sync(doc)
        with Session(main.engine) as session:
            session.add(main.HabitKeyword(id=999, user_id=2, sync_id="a", keyword="private", total_count=99))
            session.commit()
        doc["habitMetadata"]["a"] = {"habitKeywordId": 999, "totalCount": 999}
        self.sync(doc)
        self.assertNotEqual(doc["habitMetadata"]["a"]["habitKeywordId"], 999)
        self.assertEqual(doc["habitMetadata"]["a"]["totalCount"], 0)
        doc["habits"]["a"]["isPublic"] = "invalid"
        response = self.client.post("/habit/v2/sync", content=doc.get_update(), headers={"X-Sync-User": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual([(row.keyword, row.total_count) for row in self.rows()], [("読書", 0), ("private", 99)])
        self.assertEqual(self.client.post("/habit/v2/sync", headers={"X-Sync-User": "2"}).status_code, 403)

    def test_real_yjs_map_wire_compatibility(self):
        doc = self.sync()
        self.add(doc, "a", "読書")
        self.sync(doc)
        process = subprocess.run(
            ["node", str(Path(__file__).resolve().parent.parent / "frontend/tests/yjs-peer.mjs")],
            input=json.dumps({"update": base64.b64encode(doc.get_update()).decode(), "habitKey": "a", "keyword": "読書😀"}),
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        result = json.loads(process.stdout)
        self.assertEqual(result["habits"]["a"]["keyword"], "読書😀")
        self.assertEqual(result["habitMetadata"]["a"]["habitKeywordId"], self.rows()[0].id)
        doc.apply_update(base64.b64decode(result["update"]))
        self.sync(doc)
        self.assertEqual(self.rows()[0].keyword, "読書😀")
