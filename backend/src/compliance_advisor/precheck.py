"""Question pre-check: removes obvious personal data before anything leaves the app."""

import re

# Order matters: IBANs contain digit runs that would otherwise look like phone numbers.
_PATTERNS = [
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")),
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    (
        "phone number",
        re.compile(r"(?<![\w€$])(?:\+\d{1,3}[\s/-]?|\b0)\d{2,5}(?:[\s/-]?\d{2,}){2,}\b"),
    ),
]


def redact(question: str) -> tuple[str, list[str]]:
    """Returns the question with personal data replaced, and what kinds were removed."""
    removed: list[str] = []
    for kind, pattern in _PATTERNS:
        question, count = pattern.subn(f"[{kind} removed]", question)
        if count:
            removed.append(kind)
    return question, removed
