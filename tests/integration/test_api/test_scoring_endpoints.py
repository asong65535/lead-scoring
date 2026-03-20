"""Integration tests for scoring endpoints with real model and DB."""

from uuid import uuid4


class TestScoreSingle:
    def test_scores_existing_lead(self, api_client, seeded_leads):
        lead_id = seeded_leads[0]
        resp = api_client.post(f"/score/{lead_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["lead_id"] == str(lead_id)
        assert 0.0 <= data["score"] <= 1.0
        assert data["bucket"] in ("A", "B", "C", "D")
        assert data["model_version"] == "v99.0"
        assert len(data["top_factors"]) > 0

    def test_404_for_nonexistent_lead(self, api_client):
        resp = api_client.post(f"/score/{uuid4()}")
        assert resp.status_code == 404


class TestScoreBatch:
    def test_batch_scores_multiple_leads(self, api_client, seeded_leads):
        ids = [str(lid) for lid in seeded_leads[:3]]
        resp = api_client.post("/score/batch", json={"lead_ids": ids})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 3
        assert len(data["errors"]) == 0

    def test_batch_with_missing_leads(self, api_client, seeded_leads):
        ids = [str(seeded_leads[0]), str(uuid4())]
        resp = api_client.post("/score/batch", json={"lead_ids": ids})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert len(data["errors"]) == 1
