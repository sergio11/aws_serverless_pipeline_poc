"""Tests to verify DocumentStatus enum synchronization across services.

The DocumentStatus enum must stay synchronized between backend/app/domain.py
and lambda/handler.py. This module provides tests to catch drift.
"""
import os
import pytest
from pathlib import Path
from app.domain import DocumentStatus as BackendDocumentStatus


def _find_lambda_handler_path():
    """Locate lambda/handler.py searching upward from the test file or via env var."""
    env_path = os.environ.get("LAMBDA_HANDLER_PATH")
    if env_path:
        p = Path(env_path)
        return p if p.exists() else None

    test_dir = Path(__file__).resolve().parent
    candidates = [
        test_dir.parent.parent / "lambda" / "handler.py",
        Path("/lambda/handler.py"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_lambda_document_status() -> dict[str, str]:
    """Load the DocumentStatus enum from lambda/handler.py by parsing the source file."""
    import ast

    lambda_handler_path = _find_lambda_handler_path()
    if lambda_handler_path is None:
        pytest.skip("lambda/handler.py not found (running inside container without lambda source)")
    source = lambda_handler_path.read_text()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "DocumentStatus":
            statuses = {}
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            if isinstance(item.value, ast.Constant):
                                statuses[target.id] = item.value.value
            return statuses
    raise AssertionError("DocumentStatus enum not found in lambda/handler.py")


def test_document_status_sync_with_lambda() -> None:
    """Verify backend DocumentStatus matches lambda DocumentStatus."""
    lambda_statuses = _load_lambda_document_status()
    backend_statuses = {member.name: member.value for member in BackendDocumentStatus}

    assert backend_statuses == lambda_statuses, (
        f"DocumentStatus drift detected!\n"
        f"  backend: {backend_statuses}\n"
        f"  lambda:  {lambda_statuses}\n"
        f"Update BOTH files to fix this: backend/app/domain.py and lambda/handler.py"
    )


def test_document_status_has_required_states() -> None:
    """Verify DocumentStatus contains all required states for the document lifecycle."""
    required_states = {"CREATED", "PROCESSING", "PROCESSED", "FAILED"}
    actual_states = {member.name for member in BackendDocumentStatus}

    missing = required_states - actual_states
    assert not missing, f"DocumentStatus is missing required states: {missing}"


def test_document_status_values_are_lowercase() -> None:
    """Verify DocumentStatus values are lowercase strings (stored in DynamoDB)."""
    for member in BackendDocumentStatus:
        assert member.value == member.value.lower(), (
            f"DocumentStatus.{member.name} value '{member.value}' should be lowercase"
        )


def test_lambda_handler_has_sync_comment() -> None:
    """Verify lambda/handler.py contains the sync warning comment above DocumentStatus."""
    lambda_handler_path = _find_lambda_handler_path()
    if lambda_handler_path is None:
        pytest.skip("lambda/handler.py not found (running inside container without lambda source)")
    source = lambda_handler_path.read_text()

    assert "CRITICAL: This enum MUST stay synchronized" in source, (
        "lambda/handler.py is missing the sync warning comment above DocumentStatus. "
        "Add a comment warning developers to update both files when modifying the enum."
    )
