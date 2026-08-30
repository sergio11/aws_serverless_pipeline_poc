"""Tests to verify shared DocumentStatus enum properties."""
from shared.domain import DocumentStatus


def test_document_status_has_required_states() -> None:
    """Verify DocumentStatus contains all required states for the document lifecycle."""
    required_states = {"CREATED", "PROCESSING", "PROCESSED", "FAILED"}
    actual_states = {member.name for member in DocumentStatus}

    missing = required_states - actual_states
    assert not missing, f"DocumentStatus is missing required states: {missing}"


def test_document_status_values_are_lowercase() -> None:
    """Verify DocumentStatus values are lowercase strings (stored in DynamoDB)."""
    for member in DocumentStatus:
        assert member.value == member.value.lower(), (
            f"DocumentStatus.{member.name} value '{member.value}' should be lowercase"
        )


def test_document_status_is_str_enum() -> None:
    """Verify DocumentStatus values can be used as strings in DynamoDB expressions."""
    assert DocumentStatus.CREATED == "created"
    assert DocumentStatus.PROCESSING == "processing"
    assert DocumentStatus.PROCESSED == "processed"
    assert DocumentStatus.FAILED == "failed"
