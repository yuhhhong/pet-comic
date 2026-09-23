from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.pet_profile_service import PetProfileService
from app.infrastructure.db.app_db import get_session
from app.settings import get_settings


def get_pet_service(session: Session = Depends(get_session)) -> PetProfileService:
    return PetProfileService(session=session, settings=get_settings())
