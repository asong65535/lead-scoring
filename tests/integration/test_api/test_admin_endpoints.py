"""Integration tests for admin endpoints."""


class TestGetModel:
    def test_returns_active_model_info(self, api_client):
        resp = api_client.get("/admin/model")

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "v99.0"
        assert data["is_active"] is True
        assert "auc_roc" in data["metrics"]


class TestReloadModel:
    def test_reloads_active_model(self, api_client):
        resp = api_client.post("/admin/reload-model")

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "v99.0"
        assert "loaded successfully" in data["message"]
