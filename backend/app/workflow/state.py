from typing import TypedDict


class PetGraphState(TypedDict, total=False):
    pet_id: str
    force_character_card: bool
    error_code: str | None
    error_message: str | None
    retryable: bool
