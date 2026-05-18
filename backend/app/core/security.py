import re
from dataclasses import dataclass

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from app.core.config import get_settings

_settings = get_settings()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# PII patterns
_PII_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN-REDACTED]"),
    (r"\b\d{3}\s\d{2}\s\d{4}\b", "[SSN-REDACTED]"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL-REDACTED]"),
    (r"\b(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", "[PHONE-REDACTED]"),
    (r"\b\d{16}\b", "[CARD-REDACTED]"),
    (r"\b4[0-9]{12}(?:[0-9]{3})?\b", "[CARD-REDACTED]"),
    (r"\b5[1-5][0-9]{14}\b", "[CARD-REDACTED]"),
]

# Prompt injection signals
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(everything|all|your|the)\s+(previous\s+)?(instructions|context|rules)",
        r"you\s+are\s+now\s+(?:a|an|my)",
        r"act\s+as\s+(?:a|an|if)\s+you",
        r"disregard\s+(your|all|the)\s+(previous\s+)?(instructions|training|rules|guidelines)",
        r"system\s*prompt\s*:?\s*\n",
        r"<\s*/?system\s*>",
        r"\[\s*system\s*\]",
        r"jailbreak",
        r"do\s+anything\s+now",
        r"developer\s+mode",
    ]
]


@dataclass
class PIIResult:
    redacted_text: str
    pii_detected: bool
    patterns_found: list[str]


def redact_pii(text: str) -> PIIResult:
    patterns_found: list[str] = []
    result = text
    for pattern, replacement in _PII_PATTERNS:
        new_result, n = re.subn(pattern, replacement, result)
        if n > 0:
            patterns_found.append(replacement)
        result = new_result
    return PIIResult(
        redacted_text=result,
        pii_detected=len(patterns_found) > 0,
        patterns_found=patterns_found,
    )


def detect_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if api_key is None or api_key != _settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
