"""Tests to verify DocumentStatus enum synchronization across services.

The DocumentStatus enum must stay synchronized between backend/app/domain.py
and lambda/handler.py. This module provides tests to catch drift.
"""
from app.domain import DocumentStatus as BackendDocumentStatus


def _load_lambda_document_status() -> dict[str, str]:
    """Load the DocumentStatus enum from lambda/handler.py by parsing the source file."""
    import ast
    from pathlib import Path

    lambda_handler_path = Path(__file__).resolve().parent.parent.parent / "lambda" / "handler.py"
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
