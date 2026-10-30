"""Prompt builder: the numbered Passages and the question handed to the Answer Model, under the
model's own system prompt (config/models.yaml)."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .retriever import RetrievedPassage

DISCLAIMER = (
    "This is regulatory information generated from the indexed Sources, not legal advice. "
    "Verify against the official text before relying on it."
)

LAYER_LABELS = {
    "eu_level_1": "EU Level 1: regulation or directive (binding law)",
    "eu_level_2": "EU Level 2: delegated or implementing act, technical standard (binding law)",
    "eu_level_3": "EU Level 3: guideline or Q&A of a European supervisory authority",
    "national_law": "German national law (binding law)",
    "supervisory_practice": "BaFin supervisory practice (supervisory expectation)",
}

STATUS_LABELS = {
    "in_force": "in force",
    "applies_later": "applies later",
    "pending_proposal": "pending proposal, not law",
}


def format_passages(passages: list[RetrievedPassage]) -> str:
    if not passages:
        return "No passages were found."
    blocks = []
    for n, hit in enumerate(passages, start=1):
        m = hit.document.metadata
        status = STATUS_LABELS.get(m.get("legal_status", "in_force"), "in force")
        blocks.append(
            f'<passage n="{n}" provision="{m.get("provision", "")}" source="{m["source_title"]}" '
            f'layer="{LAYER_LABELS.get(m["layer"], m["layer"])}" issuer="{m["issuer"]}" '
            f'status="{status}" language="{m["language"]}">\n'
            f"{hit.document.page_content}\n</passage>"
        )
    return "\n\n".join(blocks)


_GERMAN_WORDS = {
    "der",
    "die",
    "das",
    "und",
    "ist",
    "nach",
    "welche",
    "welcher",
    "wann",
    "wie",
    "was",
    "muss",
    "müssen",
    "für",
    "eines",
    "einer",
    "ein",
    "eine",
    "nicht",
    "gilt",
    "wer",
    "bei",
    "zur",
    "zum",
    "den",
    "dem",
    "des",
    "sind",
    "hat",
    "haben",
    "kann",
    "darf",
    "oder",
    "auch",
    "mit",
}
_ENGLISH_WORDS = {
    "the",
    "and",
    "is",
    "are",
    "what",
    "which",
    "when",
    "how",
    "must",
    "for",
    "of",
    "to",
    "under",
    "does",
    "do",
    "who",
    "a",
    "an",
    "with",
    "our",
    "may",
    "can",
    "should",
    "from",
    "apply",
}


def question_language(question: str) -> str:
    """ "German" or "English", from common function words; umlauts and ß count for German."""
    words = [w.strip(".,;:?!()\"'").lower() for w in question.split()]
    german = sum(w in _GERMAN_WORDS for w in words) + 2 * sum(c in "äöüß" for c in question.lower())
    english = sum(w in _ENGLISH_WORDS for w in words)
    return "German" if german > english else "English"


def build_messages(
    question: str,
    passages: list[RetrievedPassage],
    profile_text: str = "",
    system_prompt: str = "",
) -> list[BaseMessage]:
    """The Answer Model's own system prompt, then the Firm Profile, the Passages and the
    question. Without a system prompt, as in tests, only the latter."""
    profile_block = (
        f"Firm Profile (stated by the user): {profile_text}\n\n"
        if profile_text
        else "No Firm Profile is set.\n\n"
    )
    question_message = HumanMessage(
        f"{profile_block}Passages:\n\n{format_passages(passages)}\n\n"
        f"<question>\n{question}\n</question>\n\n"
        f"The question is in {question_language(question)}. "
        f"Write the whole answer in {question_language(question)}."
    )
    return [SystemMessage(system_prompt), question_message] if system_prompt else [question_message]
