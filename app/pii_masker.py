"""
PII Masker — detects and masks Protected Health Information (PHI/PII)
before text ever reaches any LLM API.

Uses two layers:
  1. Custom regex for healthcare-specific identifiers (MRN, NPI, DEA, Member ID, Group #, NDC)
  2. Microsoft Presidio (NLP-based) for standard PII (names, DOB, SSN, phone, email, address)

Design principle: masking is architecturally enforced — the Groq client
is NEVER called with unmasked text.
"""
import re
import logging
from typing import Tuple, List, Dict

logger = logging.getLogger(__name__)

# Lazy-load Presidio so tests that don't need it can still import this module
_analyzer = None
_anonymizer = None


def _get_presidio():
    """Lazy initialization of Presidio engines."""
    global _analyzer, _anonymizer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            _analyzer = AnalyzerEngine()
            _anonymizer = AnonymizerEngine()
            logger.info("Presidio NLP engine initialized.")
        except Exception as e:
            logger.warning(f"Presidio unavailable ({e}). Falling back to regex-only PII masking.")
            _analyzer = False   # Sentinel: don't retry
            _anonymizer = False
    return _analyzer, _anonymizer


# ---------------------------------------------------------------------------
# Healthcare-specific regex patterns not covered by Presidio
# ---------------------------------------------------------------------------
HEALTHCARE_PATTERNS: Dict[str, str] = {
    # Medical Record Number — typically 6–12 digits, often prefixed
    "MRN": r"\bMRN[:\s#]*\d{4,12}\b",

    # National Provider Identifier — exactly 10 digits, often prefixed
    "NPI": r"\bNPI[:\s]*\d{10}\b",

    # DEA Registration Number — 2 letters + 7 digits (e.g., AB1234563)
    "DEA": r"\b[A-Z]{2}\d{7}\b",

    # Insurance Member ID — alphanumeric, 8–15 chars
    "MEMBER_ID": r"\b(?:Member(?:\s+ID)?|MemberID|Subscriber\s+ID)[:\s]*[A-Z0-9]{6,15}\b",

    # Group Number — numeric, 5–10 digits
    "GROUP_NUMBER": r"\b(?:Group(?:\s+Number)?|GroupNum)[:\s]*\d{5,10}\b",

    # National Drug Code — 5-4-2 or 5-3-2 format
    "NDC": r"\b\d{5}-\d{3,4}-\d{1,2}\b",

    # Medicaid/Medicare ID — alphanumeric 10–11 chars
    "MEDICAID_ID": r"\b(?:Medicaid|Medicare)\s+ID[:\s]*[A-Z0-9]{8,11}\b",
}

# Prompt injection patterns — check before processing
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|all\s+prior)\s+instructions",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"new\s+instructions",
    r"jailbreak",
    r"DAN\s+mode",
    r"override\s+safety",
    r"act\s+as\s+if",
]


class PIIMasker:
    """
    Detects and masks PHI/PII in free text before it reaches any LLM.

    Usage:
        masker = PIIMasker()
        masked_text, pii_types = masker.mask("Patient John Smith MRN: 123456")
        # → ("<PERSON> MRN: [MRN]", ["PERSON", "MRN"])
    """

    def __init__(self):
        # Pre-compile all regex patterns for performance
        self._compiled = {
            label: re.compile(pattern, re.IGNORECASE)
            for label, pattern in HEALTHCARE_PATTERNS.items()
        }
        self._injection_patterns = [
            re.compile(p, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS
        ]

    def check_prompt_injection(self, text: str) -> bool:
        """Returns True if a prompt injection attempt is detected."""
        return any(p.search(text) for p in self._injection_patterns)

    def mask(self, text: str) -> Tuple[str, List[str]]:
        """
        Mask all PHI/PII in text.

        Returns:
            (masked_text, list_of_pii_types_detected)

        Two-pass approach:
          Pass 1 — custom healthcare regex (fast, domain-specific)
          Pass 2 — Presidio NLP (catches contextual PII regex misses)
        """
        detected_types: List[str] = []

        # --- Pass 1: Healthcare-specific regex ---
        for label, pattern in self._compiled.items():
            if pattern.search(text):
                detected_types.append(label)
                text = pattern.sub(f"[{label}]", text)

        # --- Pass 2: Presidio NLP ---
        analyzer, anonymizer = _get_presidio()
        if analyzer and anonymizer:
            try:
                results = analyzer.analyze(text=text, language="en")
                for result in results:
                    if result.entity_type not in detected_types:
                        detected_types.append(result.entity_type)
                if results:
                    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
                    text = anonymized.text
            except Exception as e:
                logger.warning(f"Presidio analysis error: {e}. Regex masking still applied.")

        logger.info(f"PII masking complete. Types detected: {detected_types}")
        return text, detected_types
