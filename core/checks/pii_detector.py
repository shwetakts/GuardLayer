import re
import logging
from typing import Dict, Tuple, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex definitions
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Phone regex matches common forms:
# +1-234-567-8901
# (234) 567-8901
# 234-567-8901
# 2345678901
PHONE_REGEX = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s])?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
    r"|(?<!\d)\d{10}(?!\d)"
)

# Credit-card candidates: 13-19 digits with optional spaces/dashes between them.
# The separator is placed BEFORE each subsequent digit so the match never
# includes a trailing space or dash.
CARD_CANDIDATE_REGEX = re.compile(
    r"\b\d(?:[ -]?\d){12,18}\b"
)


def luhn_checksum(number_str: str) -> bool:
    """
    Verify a number using the Luhn algorithm.

    This reduces false positives when detecting credit-card numbers.
    """
    digits = [int(c) for c in number_str if c.isdigit()]

    if len(digits) < 13 or len(digits) > 19:
        return False

    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]

    checksum = sum(odd_digits)

    for digit in even_digits:
        doubled = digit * 2
        checksum += doubled if doubled < 10 else doubled - 9

    return checksum % 10 == 0


class PIIDetector:
    """
    Hybrid PII detector.

    Detection consists of:
      1. Regex detection for email, phone, and credit-card numbers.
      2. Optional Hugging Face NER detection for person, organization,
         and location entities.
      3. Automatic regex-only fallback if NER is disabled, unavailable,
         or inference fails.

    The Hugging Face pipeline is loaded lazily.
    """

    pipeline = None

    @classmethod
    def set_pipeline(cls, pipe: Any) -> None:
        """
        Inject a custom pipeline.

        Primarily useful for tests so that no Hugging Face model download
        is required.
        """
        cls.pipeline = pipe

    @classmethod
    def _get_pipeline(cls) -> Any:
        """
        Return the configured NER pipeline.

        Behavior:
        - If HF NER is disabled, use regex-only fallback.
        - If a pipeline has been explicitly injected, use it.
        - If the pipeline has explicitly been set to FALLBACK, respect that
        and do not attempt a Hugging Face download.
        - Otherwise, lazily load the configured Hugging Face model.
        - If loading fails, permanently fall back to regex-only detection
        for the current process.
        """
        from app.config import settings

        # Explicit configuration: never attempt HF when disabled.
        if not settings.USE_HF_PII_NER:
            cls.pipeline = "FALLBACK"
            return cls.pipeline

        # Explicit fallback state must be respected.
        #
        # This is important for tests and callers that intentionally want
        # regex-only detection. Do NOT clear FALLBACK and trigger a model
        # download.
        if cls.pipeline == "FALLBACK":
            return cls.pipeline

        # Reuse an injected or already-loaded real pipeline.
        if cls.pipeline is not None:
            return cls.pipeline

        # Lazy-load Hugging Face NER only when actually needed.
        try:
            from transformers import pipeline as hf_pipeline

            logger.info(
                "Loading Hugging Face NER pipeline: %s...",
                settings.PII_NER_MODEL_NAME,
            )

            cls.pipeline = hf_pipeline(
                "ner",
                model=settings.PII_NER_MODEL_NAME,
                aggregation_strategy="simple",
                device="cpu",
            )

        except Exception as exc:
            logger.warning(
                "Could not load Hugging Face NER pipeline: %s. "
                "Falling back to regex-only detection.",
                exc,
            )
            cls.pipeline = "FALLBACK"

        return cls.pipeline

    @classmethod
    def detect(cls, text: str) -> Dict[str, Any]:
        """
        Scan text for PII.

        Detects:
          - email
          - phone
          - credit_card
          - person
          - org
          - location
        """
        findings = []
        types_set = set()

        # ---------------------------------------------------------------
        # Helper: prevent overlapping findings
        # ---------------------------------------------------------------

        def has_overlap(start: int, end: int) -> bool:
            return any(
                not (end <= finding["start"] or start >= finding["end"])
                for finding in findings
            )

        # ---------------------------------------------------------------
        # 1. Regex PII scanning
        # ---------------------------------------------------------------

        # Email
        for match in EMAIL_REGEX.finditer(text):
            findings.append(
                {
                    "type": "email",
                    "start": match.start(),
                    "end": match.end(),
                    "action": "redact",
                }
            )
            types_set.add("email")

        # Phone
        for match in PHONE_REGEX.finditer(text):
            start, end = match.start(), match.end()

            if not has_overlap(start, end):
                findings.append(
                    {
                        "type": "phone",
                        "start": start,
                        "end": end,
                        "action": "redact",
                    }
                )
                types_set.add("phone")

        # Credit cards
        for match in CARD_CANDIDATE_REGEX.finditer(text):
            start, end = match.start(), match.end()
            candidate = match.group(0)

            digit_only = "".join(
                character for character in candidate if character.isdigit()
            )

            if luhn_checksum(digit_only):
                if not has_overlap(start, end):
                    findings.append(
                        {
                            "type": "credit_card",
                            "start": start,
                            "end": end,
                            "action": "redact",
                        }
                    )
                    types_set.add("credit_card")

        # ---------------------------------------------------------------
        # 2. Hugging Face NER scanning
        # ---------------------------------------------------------------

        pipe = cls._get_pipeline()

        # FALLBACK means regex-only detection.
        if pipe is not None and pipe != "FALLBACK":
            try:
                ner_results = pipe(text)

                entity_map = {
                    "per": "person",
                    "person": "person",
                    "org": "org",
                    "organization": "org",
                    "loc": "location",
                    "location": "location",
                    "gpe": "location",
                }

                for entity in ner_results:
                    group = entity.get(
                        "entity_group",
                        entity.get("entity", ""),
                    )

                    if not group:
                        continue

                    group = group.lower()
                    mapped_type = entity_map.get(group)

                    if not mapped_type:
                        continue

                    start = entity.get("start")
                    end = entity.get("end")

                    if start is None or end is None:
                        continue

                    if not has_overlap(start, end):
                        findings.append(
                            {
                                "type": mapped_type,
                                "start": start,
                                "end": end,
                                "action": "redact",
                            }
                        )
                        types_set.add(mapped_type)

            except Exception as exc:
                logger.warning(
                    "NER inference failed; using regex-only detection: %s",
                    exc,
                )

        # ---------------------------------------------------------------
        # 3. Normalize result
        # ---------------------------------------------------------------

        findings.sort(key=lambda finding: finding["start"])

        return {
            "detected": len(findings) > 0,
            "types": list(types_set),
            "count": len(findings),
            "findings": findings,
        }

    @classmethod
    def redact(cls, text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Redact detected PII.

        Returns:
            Tuple[str, Dict[str, Any]]:
                - redacted text
                - detection summary
        """
        summary = cls.detect(text)
        findings = summary["findings"]

        if not findings:
            return text, summary

        # Replace from back to front so original offsets remain valid.
        redacted_text = text

        for finding in reversed(findings):
            start = finding["start"]
            end = finding["end"]

            redacted_text = (
                redacted_text[:start]
                + "[REDACTED]"
                + redacted_text[end:]
            )

        return redacted_text, summary