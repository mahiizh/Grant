import re

REDACTION_RULES: list[tuple[re.Pattern[str], str]] = [
    # Google API Keys (e.g. AIzaSy...)
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_GEMINI_KEY]"),
    # OpenAI / generic API keys (e.g. sk-...)
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_API_KEY]"),
    # HTTP Bearer tokens
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Credit Card numbers (4 groups of 4 digits)
    (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "[REDACTED_CARD_NUMBER]"),
    # Database connection passwords in URIs (e.g. postgres://user:password@host)
    (re.compile(r"(://[^:]+:)([^@]+)(@)"), r"\1[REDACTED_PASSWORD]\3"),
]


def redact_sensitive_data(text: str) -> str:
    """Mask credentials, API keys, tokens, and payment card numbers from logs and traces."""
    redacted = text
    for pattern, replacement in REDACTION_RULES:
        redacted = pattern.sub(replacement, redacted)
    return redacted
