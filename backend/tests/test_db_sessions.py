from contextlib import contextmanager
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.application.pet_profile_service import PetProfileService
from app.infrastructure.db import app_db
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import PetArtifactModel, PetProfileModel
from app.infrastructure.db.schema import ensure_schema
from app.settings import Settings


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.enterContext(patch.object(app_db, "SessionLocal", self.factory))

    def test_request_and_workflow_sessions_commit_and_rollback(self):
        for scope in (app_db.db_session, contextmanager(app_db.get_session)):
            with self.subTest(scope=scope.__name__):
                pet_id = str(uuid4())
                with scope() as session:
                    session.add(PetProfileModel(pet_id=pet_id, name="saved", personality="calm", status="draft"))
                with self.assertRaisesRegex(RuntimeError, "rollback"):
                    with scope() as session:
                        session.get(PetProfileModel, pet_id).name = "unsaved"
                        session.flush()
                        raise RuntimeError("rollback")
                with self.factory() as session:
                    self.assertEqual(session.get(PetProfileModel, pet_id).name, "saved")

    def test_legacy_artifacts_gain_retryability_without_rebuilding(self):
        pet_id = str(uuid4())
        artifact_id = str(uuid4())
        with app_db.db_session() as session:
            session.add(PetProfileModel(pet_id=pet_id, name="legacy", personality="calm", status="draft"))
            session.flush()
            session.add(PetArtifactModel(
                artifact_id=artifact_id, pet_id=pet_id, kind="appearance", version=1,
                input_hash="old", status="failed", error_code="MODEL_REQUEST_FAILED", error_message="legacy failure",
            ))
        # 模拟尚未保存 retryable 的历史表结构。
        with self.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE pet_artifacts DROP COLUMN retryable")
        indexes_before = inspect(self.engine).get_indexes("pet_artifacts")
        with patch("app.infrastructure.db.schema._rebuild", side_effect=AssertionError("must not rebuild")):
            notes = ensure_schema(self.engine)
        self.assertEqual(len(notes), 1)
        self.assertEqual(inspect(self.engine).get_indexes("pet_artifacts"), indexes_before)
        self.assertEqual(ensure_schema(self.engine), [])
        with self.factory() as session:
            artifact = session.scalar(select(PetArtifactModel).where(PetArtifactModel.artifact_id == artifact_id))
            self.assertEqual(artifact.error_message, "legacy failure")
            self.assertIsNone(artifact.retryable)
            pet = PetProfileService(session, Settings(_env_file=None)).get(pet_id)
            self.assertTrue(pet.error.retryable)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])


if __name__ == "__main__":
    unittest.main()
