"""
Mock user context manager for testing authenticated endpoints.
"""

import time
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

from open_webui.models.users import UserModel


def create_mock_user(
    id: str = "1",
    name: str = "John Doe",
    email: str = "john.doe@openwebui.com",
    role: str = "user",
    profile_image_url: str = "/user.png",
) -> UserModel:
    """Create a mock UserModel for testing."""
    current_time = int(time.time())
    return UserModel(
        id=id,
        name=name,
        email=email,
        role=role,
        profile_image_url=profile_image_url,
        last_active_at=current_time,
        updated_at=current_time,
        created_at=current_time,
    )


@contextmanager
def mock_webui_user(
    id: str = "1",
    name: str = "John Doe",
    email: str = "john.doe@openwebui.com",
    role: str = "user",
    profile_image_url: str = "/user.png",
):
    """
    Context manager to mock the authenticated user for testing.

    This uses FastAPI's dependency override mechanism to inject the mock user
    into all routes that use get_verified_user, get_current_user, or get_admin_user.

    Usage:
        with mock_webui_user(id="123"):
            response = client.get("/api/v1/some-endpoint")

    Args:
        id: User ID (default: "1")
        name: User name (default: "John Doe")
        email: User email (default: "john.doe@openwebui.com")
        role: User role (default: "user")
        profile_image_url: Profile image URL (default: "/user.png")
    """
    from open_webui.main import app
    from open_webui.utils.auth import get_current_user, get_verified_user, get_admin_user

    mock_user = create_mock_user(
        id=id,
        name=name,
        email=email,
        role=role,
        profile_image_url=profile_image_url,
    )

    # Create dependency override functions
    async def override_get_current_user():
        return mock_user

    async def override_get_verified_user():
        return mock_user

    async def override_get_admin_user():
        return mock_user

    # Override dependencies using FastAPI's mechanism
    original_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_verified_user] = override_get_verified_user
    app.dependency_overrides[get_admin_user] = override_get_admin_user

    try:
        yield mock_user
    finally:
        # Restore original dependency overrides
        app.dependency_overrides = original_overrides
