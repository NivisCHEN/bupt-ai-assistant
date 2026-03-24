"""Personally Identifiable Information (PII) detection and masking utilities.

Uses regex patterns defined in ``config.settings`` to locate and redact
sensitive data such as student IDs, phone numbers, and national ID card
numbers before the text enters the LLM or gets persisted.
"""

from __future__ import annotations

import re
from typing import Any

from config.settings import settings


class PIIDetector:
    """Detect and mask PII in free-form text.

    The detector is initialised from the regex patterns stored in
    :pyattr:`config.settings.privacy.pii_patterns`.  Each pattern maps a
    human-readable PII type name (e.g. ``"phone"``) to a regular
    expression string.
    """

    def __init__(self) -> None:
        self._patterns: dict[str, re.Pattern[str]] = {
            pii_type: re.compile(pattern)
            for pii_type, pattern in settings.privacy.pii_patterns.items()
        }

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def detect(self, text: str) -> list[dict[str, Any]]:
        """Return every PII occurrence found in *text*.

        Each element is a dict with keys ``type``, ``value``, ``start``
        and ``end`` (character offsets).

        Args:
            text: The input string to scan.

        Returns:
            A list of dicts describing each detected PII span.
        """
        findings: list[dict[str, Any]] = []
        for pii_type, pattern in self._patterns.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "type": pii_type,
                        "value": match.group(),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        # Sort by position so callers can iterate left-to-right.
        findings.sort(key=lambda f: f["start"])
        return findings

    def mask(self, text: str) -> str:
        """Replace every PII span with a ``[MASKED_<TYPE>]`` placeholder.

        Replacements are applied right-to-left so that character offsets
        remain valid throughout the process.

        Args:
            text: The input string to sanitise.

        Returns:
            A copy of *text* with all detected PII replaced.
        """
        findings = self.detect(text)
        # Process in reverse order to keep offsets stable.
        for finding in reversed(findings):
            masked_label = f"[MASKED_{finding['type'].upper()}]"
            text = text[: finding["start"]] + masked_label + text[finding["end"] :]
        return text
