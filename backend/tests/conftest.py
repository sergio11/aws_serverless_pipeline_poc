# Backend test configuration.
#
# Shared pytest fixtures for backend tests.
# Currently, each test file defines its own test doubles (FakeS3Client, FakeTable, etc.)
# to keep tests self-contained and explicit. If shared fixtures are needed in the future,
# define them here as @pytest.fixture functions.
