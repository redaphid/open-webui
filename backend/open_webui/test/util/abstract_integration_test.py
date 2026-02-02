"""
Abstract base class for integration tests with PostgreSQL/SQLite database support.

This module provides a base class for running integration tests against the Open WebUI
API with proper database setup and teardown.

Note: This module can be imported as either:
- `from test.util.abstract_integration_test import AbstractPostgresTest`
- `from open_webui.test.util.abstract_integration_test import AbstractPostgresTest`
"""

import os
import pytest
from typing import ClassVar
from fastapi.testclient import TestClient

# Set test environment before importing the app
os.environ["ENV"] = "test"
os.environ["WEBUI_AUTH"] = "False"  # Disable auth for easier testing
os.environ["DATABASE_URL"] = "sqlite:///./test_openwebui.db"  # Use SQLite for tests


class AbstractPostgresTest:
    """
    Abstract base class for integration tests.

    Provides:
    - A FastAPI TestClient connected to the app
    - Database setup and teardown
    - Helper methods for creating URLs

    Usage:
        class TestMyFeature(AbstractPostgresTest):
            BASE_PATH = "/api/v1/my-feature"

            def test_something(self):
                with mock_webui_user():
                    response = self.fast_api_client.get(self.create_url("/"))
                assert response.status_code == 200
    """

    BASE_PATH: ClassVar[str] = ""
    fast_api_client: ClassVar[TestClient] = None

    @classmethod
    def setup_class(cls):
        """Set up test fixtures before running tests in this class."""
        # Import here to ensure env vars are set first
        from open_webui.main import app
        from open_webui.internal.db import Session, engine

        cls.fast_api_client = TestClient(app)
        cls._engine = engine
        cls._session = Session

        # Import models to ensure tables are created
        # These imports may fail for some models that don't exist
        # in all versions, so we handle exceptions gracefully
        model_imports = [
            "open_webui.models.auths",
            "open_webui.models.users",
            "open_webui.models.chats",
            "open_webui.models.prompts",
            "open_webui.models.tools",
            "open_webui.models.functions",
            "open_webui.models.models",
            "open_webui.models.folders",
            "open_webui.models.files",
            "open_webui.models.groups",
            "open_webui.models.memories",
            "open_webui.models.knowledge",
            "open_webui.models.tags",
            "open_webui.models.feedbacks",
            "open_webui.models.templates",
        ]

        for module_name in model_imports:
            try:
                __import__(module_name)
            except ImportError:
                pass  # Model module may not exist in this version

    @classmethod
    def teardown_class(cls):
        """Clean up after tests in this class."""
        if hasattr(cls, "_session") and cls._session:
            cls._session.close_all()

    def setup_method(self, method):
        """Set up before each test method."""
        # Clean database tables before each test
        self._clean_database()

    def teardown_method(self, method):
        """Clean up after each test method."""
        pass

    def _clean_database(self):
        """Clean all database tables between tests."""
        from open_webui.internal.db import Session

        with Session() as session:
            # Get all table names and truncate them
            tables = [
                "auth",
                "user",
                "chat",
                "prompt",
                "tool",
                "function",
                "model",
                "folder",
                "file",
                "group",
                "memory",
                "knowledge",
                "tag",
                "chatidtag",
                "feedback",
                "template",
            ]

            for table in tables:
                try:
                    session.execute(f"DELETE FROM {table}")
                except Exception:
                    pass  # Table might not exist

            session.commit()

    def create_url(self, path: str = "") -> str:
        """
        Create a full URL path for the API endpoint.

        Args:
            path: The path suffix to append to BASE_PATH

        Returns:
            The full URL path

        Example:
            self.create_url("/items/123") -> "/api/v1/my-feature/items/123"
        """
        base = self.BASE_PATH.rstrip("/")
        suffix = path.lstrip("/") if path else ""

        if suffix:
            return f"{base}/{suffix}"
        return base
