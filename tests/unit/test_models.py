from src.models.base import Base, TimestampMixin


def test_base_has_metadata():
    assert hasattr(Base, "metadata")


def test_timestamp_mixin_has_expected_columns():
    assert hasattr(TimestampMixin, "id")
    assert hasattr(TimestampMixin, "created_at")
    assert hasattr(TimestampMixin, "updated_at")


from src.models.lead import Lead


def test_lead_table_name():
    assert Lead.__tablename__ == "leads"


def test_lead_has_expected_columns():
    col_names = {c.name for c in Lead.__table__.columns}
    expected = {
        "id", "external_id", "source_system", "lead_origin", "lead_source",
        "country", "city", "current_occupation", "specialization",
        "do_not_email", "do_not_call", "total_visits", "total_time_spent",
        "page_views_per_visit", "last_activity", "tags", "converted",
        "created_at", "updated_at",
    }
    assert expected == col_names


def test_lead_external_id_is_unique():
    col = Lead.__table__.c.external_id
    # Check unique constraint exists via index or unique flag
    assert col.unique or any(
        idx.unique for idx in Lead.__table__.indexes if "external_id" in {c.name for c in idx.columns}
    )


from src.models.prediction import Prediction


def test_prediction_table_name():
    assert Prediction.__tablename__ == "predictions"


def test_prediction_has_expected_columns():
    col_names = {c.name for c in Prediction.__table__.columns}
    expected = {
        "id", "lead_id", "score", "bucket", "model_version",
        "feature_snapshot", "top_factors", "scored_at",
        "created_at", "updated_at",
    }
    assert expected == col_names


def test_prediction_bucket_has_check_constraint():
    # Verify CHECK constraint exists on the table
    check_constraints = [
        c for c in Prediction.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    assert len(check_constraints) > 0


from src.models.model_registry import ModelRegistry


def test_model_registry_table_name():
    assert ModelRegistry.__tablename__ == "model_registry"


def test_model_registry_has_expected_columns():
    col_names = {c.name for c in ModelRegistry.__table__.columns}
    expected = {
        "id", "version", "artifact_path", "metrics", "hyperparameters",
        "feature_columns", "is_active", "trained_at",
        "created_at", "updated_at",
    }
    assert expected == col_names


def test_model_registry_version_is_unique():
    col = ModelRegistry.__table__.c.version
    assert col.unique or any(
        idx.unique for idx in ModelRegistry.__table__.indexes if "version" in {c.name for c in idx.columns}
    )


def test_model_registry_has_partial_index_on_is_active():
    partial_indexes = [
        idx for idx in ModelRegistry.__table__.indexes
        if "is_active" in {c.name for c in idx.columns if hasattr(c, "name")}
        and idx.dialect_kwargs.get("postgresql_where") is not None
    ]
    assert len(partial_indexes) > 0
