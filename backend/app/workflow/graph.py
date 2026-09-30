from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.workflow.nodes.pet_profile import (
    extract_pet_appearance,
    finalize_pet_profile,
    generate_character_card,
    validate_pet_input,
)
from app.workflow.state import PetGraphState

def _route(next_node: str):
    def route(state: PetGraphState) -> str:
        if state.get("error_code"):
            return "finalize_pet_profile"
        return next_node

    return route


def build_pet_profile_graph():
    graph = StateGraph(PetGraphState)
    graph.add_node("validate_pet_input", validate_pet_input)
    graph.add_node("extract_pet_appearance", extract_pet_appearance)
    graph.add_node("generate_character_card", generate_character_card)
    graph.add_node("finalize_pet_profile", finalize_pet_profile)
    graph.add_edge(START, "validate_pet_input")
    graph.add_conditional_edges(
        "validate_pet_input",
        _route("extract_pet_appearance"),
        {"extract_pet_appearance": "extract_pet_appearance", "finalize_pet_profile": "finalize_pet_profile"},
    )
    graph.add_conditional_edges(
        "extract_pet_appearance",
        _route("generate_character_card"),
        {"generate_character_card": "generate_character_card", "finalize_pet_profile": "finalize_pet_profile"},
    )
    graph.add_edge("generate_character_card", "finalize_pet_profile")
    graph.add_edge("finalize_pet_profile", END)
    return graph.compile()


@lru_cache(maxsize=1)
def get_pet_profile_graph():
    return build_pet_profile_graph()
