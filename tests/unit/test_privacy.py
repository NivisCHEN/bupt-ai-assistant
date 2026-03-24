"""Tests for PII detection and masking utilities."""

from unittest.mock import patch, MagicMock

import pytest


def _make_privacy_settings():
    """Return a mock settings object with PII patterns."""
    return {
        "student_id": r"\b\d{10}\b",
        "phone": r"1[3-9]\d{9}",
        "id_card": r"\d{17}[\dXx]",
    }


@pytest.fixture()
def detector():
    """Create a PIIDetector with standard patterns, bypassing config import."""
    mock_settings = MagicMock()
    mock_settings.privacy.pii_patterns = _make_privacy_settings()
    with patch("src.utils.privacy.settings", mock_settings):
        from src.utils.privacy import PIIDetector
        return PIIDetector()


class TestPIIDetectorDetect:
    """Tests for PIIDetector.detect()."""

    def test_detect_student_id(self, detector):
        # \b word boundary requires ASCII word chars on both sides;
        # surround with spaces so the boundary fires correctly.
        text = "我的学号是 2021210001 请帮我查一下"
        findings = detector.detect(text)
        assert len(findings) == 1
        assert findings[0]["type"] == "student_id"
        assert findings[0]["value"] == "2021210001"

    def test_detect_phone_number(self, detector):
        text = "联系电话13812345678"
        findings = detector.detect(text)
        types = {f["type"] for f in findings}
        assert "phone" in types
        phone_findings = [f for f in findings if f["type"] == "phone"]
        assert phone_findings[0]["value"] == "13812345678"

    def test_detect_id_card(self, detector):
        text = "身份证号110101199901011234"
        findings = detector.detect(text)
        types = {f["type"] for f in findings}
        assert "id_card" in types

    def test_detect_id_card_with_x(self, detector):
        text = "身份证: 11010119990101123X"
        findings = detector.detect(text)
        id_card_findings = [f for f in findings if f["type"] == "id_card"]
        assert len(id_card_findings) >= 1
        assert id_card_findings[0]["value"].endswith("X")

    def test_no_pii(self, detector):
        text = "北邮图书馆几点开门？"
        findings = detector.detect(text)
        assert findings == []

    def test_mixed_pii_types(self, detector):
        # Use spaces around student_id so \b word boundary matches
        text = "学号 2021210001 手机13912345678 身份证110101199901011234"
        findings = detector.detect(text)
        types = {f["type"] for f in findings}
        assert "student_id" in types
        assert "phone" in types
        assert "id_card" in types

    def test_findings_sorted_by_position(self, detector):
        text = "手机13912345678学号2021210001"
        findings = detector.detect(text)
        starts = [f["start"] for f in findings]
        assert starts == sorted(starts)


class TestPIIDetectorMask:
    """Tests for PIIDetector.mask()."""

    def test_mask_student_id(self, detector):
        text = "我的学号是 2021210001 "
        masked = detector.mask(text)
        assert "2021210001" not in masked
        assert "[MASKED_STUDENT_ID]" in masked

    def test_mask_phone(self, detector):
        text = "电话13812345678"
        masked = detector.mask(text)
        assert "13812345678" not in masked
        assert "[MASKED_PHONE]" in masked

    def test_mask_id_card(self, detector):
        text = "身份证110101199901011234"
        masked = detector.mask(text)
        assert "110101199901011234" not in masked
        assert "[MASKED_ID_CARD]" in masked

    def test_mask_preserves_clean_text(self, detector):
        text = "今天天气真好"
        masked = detector.mask(text)
        assert masked == text

    def test_mask_mixed_pii(self, detector):
        text = "学号 2021210001 电话13912345678"
        masked = detector.mask(text)
        assert "2021210001" not in masked
        assert "13912345678" not in masked
        assert "[MASKED_STUDENT_ID]" in masked
        assert "[MASKED_PHONE]" in masked
