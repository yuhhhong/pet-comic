from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from openai import APIStatusError
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.pet_profile_service import PetProfileService
from app.domain.pets import PetAppearance, PetProfileStatus
from app.infrastructure.db import app_db
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import ModelBindingModel, ProviderModel
from app.infrastructure.providers.errors import model_call_error
from app.infrastructure.providers.langchain_responses import StructuredResult
from app.settings import Settings
from app.workflow.graph import build_pet_profile_graph


class PetGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.settings = Settings(_env_file=None, data_dir=Path(directory))
        engine = create_engine("sqlite:///" + (Path(directory) / "test.db").as_posix())
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.enterContext(patch.object(app_db, "SessionLocal", sessionmaker(engine, expire_on_commit=False)))
        self.enterContext(patch("app.workflow.nodes.pet_profile.get_settings", return_value=self.settings))
        vision = self.enterContext(patch("app.workflow.nodes.pet_profile.LangChainResponsesProvider"))
        image = self.enterContext(patch("app.workflow.nodes.pet_profile.ImageProviderAdapter"))
        appearance = PetAppearance(
            species="猫", breed="未知", coat_color="白色", coat_pattern="纯色",
            eye_color="蓝色", body_size="小型", distinctive_marks=[], summary="白色小猫",
        )
        self.parse = vision.return_value.parse = AsyncMock(return_value=StructuredResult(appearance, {}, "vision"))
        buffer = BytesIO()
        Image.new("RGBA", (16, 16), "white").save(buffer, format="PNG")
        self.photo = buffer.getvalue()
        self.edit = image.return_value.edit = AsyncMock(return_value=self.photo)
        with app_db.db_session() as session:
            provider_id = str(uuid4())
            session.add(ProviderModel(id=provider_id, display_name="Test", base_url="https://example.invalid/v1", api_key="test", enabled=True))
            session.flush()
            for role in ("vision", "image"):
                session.add(ModelBindingModel(role=role, provider_id=provider_id, model_id=role))

    async def create_pet(self):
        with app_db.db_session() as session:
            return await PetProfileService(session, self.settings).create(name="小白", personality="活泼", photos=[("photo.png", self.photo)])

    async def test_create_reuses_results_and_force_retry_creates_new_card(self):
        pet = await self.create_pet()
        self.assertEqual(pet.status, PetProfileStatus.READY)
        self.assertEqual(pet.appearance.summary, "白色小猫")
        self.assertTrue((self.settings.pet_dir / pet.pet_id / "appearance.json").is_file())
        with app_db.db_session() as session:
            service = PetProfileService(session, self.settings)
            retried = await service.retry(pet.pet_id)
            self.assertEqual(retried.active_character_card_id, pet.active_character_card_id)
            self.parse.assert_awaited_once()
            self.edit.assert_awaited_once()
            regenerated = await service.retry_character_card(pet.pet_id)
            self.assertEqual(len(regenerated.character_cards), 2)
            self.assertNotEqual(regenerated.active_character_card_id, pet.active_character_card_id)
            self.assertTrue(service.resolve_file(pet.pet_id, regenerated.character_cards[0].path).is_file())
        self.parse.assert_awaited_once()
        self.assertEqual(self.edit.await_count, 2)

    async def test_persisted_retryability_matches_provider_status(self):
        for status, retryable in ((401, False), (429, True)):
            with self.subTest(status=status):
                response = httpx.Response(status, request=httpx.Request("POST", "https://example.invalid/v1/responses"))
                failure = APIStatusError("model failed", response=response, body=None)
                self.parse.side_effect = model_call_error(failure, secret="test", image=False)
                pet = await self.create_pet()
                self.assertEqual(pet.status, PetProfileStatus.DRAFT)
                self.assertEqual(pet.error.code, "MODEL_REQUEST_FAILED")
                self.assertEqual(pet.error.retryable, retryable)
                with app_db.db_session() as session:
                    loaded = PetProfileService(session, self.settings).get(pet.pet_id)
                    self.assertEqual(loaded.error.retryable, retryable)
        self.edit.assert_not_awaited()

    async def test_card_failure_retries_without_repeating_appearance(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid/v1/images/edits"))
        failure = APIStatusError("rate limited", response=response, body=None)
        self.edit.side_effect = model_call_error(failure, secret="test", image=True)
        pet = await self.create_pet()
        self.assertIsNotNone(pet.appearance)
        self.assertEqual(pet.status, PetProfileStatus.DRAFT)
        self.assertTrue(pet.error.retryable)
        self.edit.side_effect = None
        with app_db.db_session() as session:
            retried = await PetProfileService(session, self.settings).retry(pet.pet_id)
        self.assertEqual(retried.status, PetProfileStatus.READY)
        self.assertIsNone(retried.error)
        self.assertEqual([card.status.value for card in retried.character_cards], ["succeeded", "failed"])
        self.parse.assert_awaited_once()
        self.assertEqual(self.edit.await_count, 2)

    async def test_regeneration_preserves_disabled_status_and_skips_trashed_pet(self):
        pet = await self.create_pet()
        with app_db.db_session() as session:
            service = PetProfileService(session, self.settings)
            await service.update(pet.pet_id, name=None, personality=None, enabled=False)
            regenerated = await service.retry_character_card(pet.pet_id)
            self.assertEqual(regenerated.status, PetProfileStatus.DISABLED)
            service.trash(pet.pet_id)
        result = await build_pet_profile_graph().ainvoke({"pet_id": pet.pet_id, "force_character_card": True})
        self.assertEqual(result["error_code"], "PET_DELETED")
        self.parse.assert_awaited_once()
        self.assertEqual(self.edit.await_count, 2)


if __name__ == "__main__":
    unittest.main()
