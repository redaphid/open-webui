from test.util.abstract_integration_test import AbstractPostgresTest
from test.util.mock_user import mock_webui_user


class TestTemplates(AbstractPostgresTest):
    BASE_PATH = "/api/v1/templates"

    def test_templates_crud(self):
        # Get all templates (should be empty initially)
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        assert len(response.json()) == 0

        # Create a new template
        with mock_webui_user(id="2"):
            response = self.fast_api_client.post(
                self.create_url("/create"),
                json={
                    "name": "Home Automation",
                    "description": "Control smart home devices",
                    "system_prompt": "You are a helpful assistant for home automation.",
                    "tool_ids": ["direct_server:http://localhost:3100/mcp"],
                    "feature_ids": ["web_search"],
                },
            )
        assert response.status_code == 200
        data = response.json()
        template_id = data["id"]
        assert data["name"] == "Home Automation"
        assert data["description"] == "Control smart home devices"
        assert data["system_prompt"] == "You are a helpful assistant for home automation."
        assert data["tool_ids"] == ["direct_server:http://localhost:3100/mcp"]
        assert data["feature_ids"] == ["web_search"]
        assert data["user_id"] == "2"

        # Create another template with different user
        with mock_webui_user(id="3"):
            response = self.fast_api_client.post(
                self.create_url("/create"),
                json={
                    "name": "Code Assistant",
                    "description": "Help with coding tasks",
                },
            )
        assert response.status_code == 200
        template2_id = response.json()["id"]

        # Get all templates for user 2 (should only see their own)
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        templates = response.json()
        assert len(templates) == 1
        assert templates[0]["name"] == "Home Automation"

        # Get all templates for user 3
        with mock_webui_user(id="3"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        templates = response.json()
        assert len(templates) == 1
        assert templates[0]["name"] == "Code Assistant"

        # Get template by ID
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url(f"/{template_id}"))
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == template_id
        assert data["name"] == "Home Automation"

        # Update template
        with mock_webui_user(id="2"):
            response = self.fast_api_client.post(
                self.create_url(f"/{template_id}/update"),
                json={
                    "name": "Smart Home",
                    "description": "Updated description",
                    "system_prompt": "Updated system prompt",
                    "tool_ids": ["tool1", "tool2"],
                    "feature_ids": ["image_generation"],
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Smart Home"
        assert data["description"] == "Updated description"
        assert data["system_prompt"] == "Updated system prompt"
        assert data["tool_ids"] == ["tool1", "tool2"]
        assert data["feature_ids"] == ["image_generation"]

        # Verify update persisted
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url(f"/{template_id}"))
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Smart Home"

        # Try to update another user's template (should fail)
        with mock_webui_user(id="2"):
            response = self.fast_api_client.post(
                self.create_url(f"/{template2_id}/update"),
                json={
                    "name": "Hacked Template",
                },
            )
        assert response.status_code == 401

        # Delete template
        with mock_webui_user(id="2"):
            response = self.fast_api_client.delete(
                self.create_url(f"/{template_id}/delete")
            )
        assert response.status_code == 200

        # Verify deletion
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        assert len(response.json()) == 0

        # Try to delete another user's template (should fail)
        with mock_webui_user(id="2"):
            response = self.fast_api_client.delete(
                self.create_url(f"/{template2_id}/delete")
            )
        assert response.status_code == 401

    def test_template_with_minimal_fields(self):
        # Create template with only required field (name)
        with mock_webui_user(id="4"):
            response = self.fast_api_client.post(
                self.create_url("/create"),
                json={
                    "name": "Minimal Template",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Minimal Template"
        assert data["description"] is None
        assert data["system_prompt"] is None
        assert data["tool_ids"] == []
        assert data["feature_ids"] == []
