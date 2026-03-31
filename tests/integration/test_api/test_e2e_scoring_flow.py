"""End-to-end scoring flow: seed -> score -> verify DB persistence."""

from sqlalchemy import text

from src.models.prediction import Prediction


class TestScoringFlowE2E:
    def test_score_is_persisted_to_predictions_table(self, api_client, seeded_leads):
        """Full flow: score a lead, then verify the prediction row exists in DB."""
        lead_id = seeded_leads[0]

        resp = api_client.post(f"/score/{lead_id}")
        assert resp.status_code == 200
        data = resp.json()

        # Verify the response has all expected fields with valid values
        assert data["lead_id"] == str(lead_id)
        assert 0.0 <= data["score"] <= 1.0
        assert data["bucket"] in ("A", "B", "C", "D")
        assert data["model_version"] == "v99.0"
        assert isinstance(data["top_factors"], list)
        assert len(data["top_factors"]) > 0

        # Verify the prediction was persisted to the database
        import sqlalchemy
        from config.settings import get_settings
        settings = get_settings()
        sync_engine = sqlalchemy.create_engine(
            settings.database.url.replace("postgresql+asyncpg", "postgresql+psycopg2")
        )
        with sync_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT score, bucket, model_version, feature_snapshot, top_factors "
                    "FROM predictions WHERE lead_id = :lid ORDER BY scored_at DESC LIMIT 1"
                ),
                {"lid": str(lead_id)},
            ).fetchone()

        sync_engine.dispose()

        assert row is not None, "Prediction row was not persisted"
        assert 0.0 <= row.score <= 1.0
        assert row.bucket == data["bucket"]
        assert row.model_version == "v99.0"
        assert row.feature_snapshot is not None, "Feature snapshot should be saved"
        assert row.top_factors is not None, "Top factors should be saved"

    def test_scoring_twice_creates_two_predictions(self, api_client, seeded_leads):
        """Each scoring call should create a new prediction row, not upsert."""
        lead_id = seeded_leads[1]

        resp1 = api_client.post(f"/score/{lead_id}")
        resp2 = api_client.post(f"/score/{lead_id}")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        import sqlalchemy
        from config.settings import get_settings
        settings = get_settings()
        sync_engine = sqlalchemy.create_engine(
            settings.database.url.replace("postgresql+asyncpg", "postgresql+psycopg2")
        )
        with sync_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM predictions WHERE lead_id = :lid"),
                {"lid": str(lead_id)},
            ).scalar()
        sync_engine.dispose()

        assert count >= 2, f"Expected at least 2 prediction rows, got {count}"

    def test_batch_score_persists_all_predictions(self, api_client, seeded_leads):
        """Batch scoring should persist a prediction for each successfully scored lead."""
        ids = [str(lid) for lid in seeded_leads[2:5]]

        resp = api_client.post("/score/batch", json={"lead_ids": ids})
        assert resp.status_code == 200
        data = resp.json()
        scored_count = len(data["results"])
        assert scored_count == 3

        import sqlalchemy
        from config.settings import get_settings
        settings = get_settings()
        sync_engine = sqlalchemy.create_engine(
            settings.database.url.replace("postgresql+asyncpg", "postgresql+psycopg2")
        )
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT lead_id, score, bucket FROM predictions "
                    f"WHERE lead_id::text IN ({placeholders}) ORDER BY scored_at DESC"
                ),
                {f"id{i}": v for i, v in enumerate(ids)},
            ).fetchall()
        sync_engine.dispose()

        assert len(rows) >= 3, f"Expected at least 3 prediction rows, got {len(rows)}"
        # Verify each scored lead has a prediction
        persisted_lead_ids = {str(r.lead_id) for r in rows}
        for lid in ids:
            assert lid in persisted_lead_ids, f"Missing prediction for lead {lid}"
