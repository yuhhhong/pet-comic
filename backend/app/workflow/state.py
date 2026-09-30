from typing import TypedDict


class PetGraphState(TypedDict, total=False):
    """建档图在节点间传递的状态；节点只返回需要更新的字段。"""

    pet_id: str
    # 单独重试角色卡时为 True，跳过已有角色卡的复用判断。
    force_character_card: bool
    # 非空错误码使后续节点转入 finalize_pet_profile。
    error_code: str | None
    error_message: str | None
    retryable: bool
