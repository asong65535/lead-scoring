"""Unit tests for SQLAlchemy model definitions.

These tests verify schema contracts that matter for correctness:
column types, nullability, constraints, relationships, and defaults.
They do NOT merely mirror the implementation — each test catches a
specific class of schema regression.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Float, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base, TimestampMixin
from src.models.lead import Lead
from src.models.prediction import Prediction
from src.models.model_registry import ModelRegistry
from src.models.crm_sync_log import CRMSyncLog


# ---------------------------------------------------------------------------
# TimestampMixin: verify PK and timestamp columns have correct server defaults
# ---------------------------------------------------------------------------

def test_timestamp_mixin_id_is_primary_key():
    col = Lead.__table__.c.id
    assert col.primary_key


def test_timestamp_mixin_id_has_server_default():
    """Server must generate UUIDs — not the app."""
    col = Lead.__table__.c.id
    assert col.server_default is not None


def test_timestamp_mixin_created_at_has_server_default():
    col = Lead.__table__.c.created_at
    assert col.server_default is not None


def test_timestamp_mixin_updated_at_has_onupdate():
    col = Lead.__table__.c.updated_at
    assert col.onupdate is not None


# ---------------------------------------------------------------------------
# Lead model
# ---------------------------------------------------------------------------

def test_lead_external_id_is_not_nullable():
    col = Lead.__table__.c.external_id
    assert col.nullable is False


def test_lead_external_id_is_unique():
    col = Lead.__table__.c.external_id
    assert col.unique is True


def test_lead_source_system_is_not_nullable():
    col = Lead.__table__.c.source_system
    assert col.nullable is False


def test_lead_optional_fields_are_nullable():
    """Fields like country, city, specialization should allow NULL."""
    nullable_columns = [
        "lead_origin", "lead_source", "country", "city",
        "current_occupation", "specialization", "total_visits",
        "total_time_spent", "page_views_per_visit", "last_activity",
        "tags", "converted",
    ]
    for name in nullable_columns:
        col = Lead.__table__.c[name]
        assert col.nullable is True, f"{name} should be nullable"


def test_lead_do_not_email_defaults_false():
    col = Lead.__table__.c.do_not_email
    assert col.server_default is not None
    assert col.server_default.arg == "false"


def test_lead_do_not_call_defaults_false():
    col = Lead.__table__.c.do_not_call
    assert col.server_default is not None
    assert col.server_default.arg == "false"


def test_lead_has_relationship_to_predictions():
    assert "predictions" in Lead.__mapper__.relationships
    rel = Lead.__mapper__.relationships["predictions"]
    assert rel.back_populates == "lead"


def test_lead_has_relationship_to_sync_logs():
    assert "sync_logs" in Lead.__mapper__.relationships
    rel = Lead.__mapper__.relationships["sync_logs"]
    assert rel.back_populates == "lead"


def test_lead_has_index_on_source_system():
    idx_names = {idx.name for idx in Lead.__table__.indexes}
    assert "ix_leads_source_system" in idx_names


def test_lead_has_index_on_converted():
    idx_names = {idx.name for idx in Lead.__table__.indexes}
    assert "ix_leads_converted" in idx_names


# ---------------------------------------------------------------------------
# Prediction model
# ---------------------------------------------------------------------------

def test_prediction_lead_id_is_foreign_key_to_leads():
    col = Prediction.__table__.c.lead_id
    fk = list(col.foreign_keys)
    assert len(fk) == 1
    assert fk[0].target_fullname == "leads.id"


def test_prediction_lead_id_fk_restricts_delete():
    col = Prediction.__table__.c.lead_id
    fk = list(col.foreign_keys)
    assert fk[0].ondelete == "RESTRICT"


def test_prediction_score_is_not_nullable():
    col = Prediction.__table__.c.score
    assert col.nullable is False


def test_prediction_bucket_check_constraint_values():
    """Verify the CHECK constraint allows only A/B/C/D."""
    checks = [
        c for c in Prediction.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_predictions_bucket"
    ]
    assert len(checks) == 1
    text = str(checks[0].sqltext)
    for bucket in ("A", "B", "C", "D"):
        assert bucket in text


def test_prediction_scored_at_has_server_default():
    col = Prediction.__table__.c.scored_at
    assert col.server_default is not None


def test_prediction_feature_snapshot_uses_jsonb():
    col = Prediction.__table__.c.feature_snapshot
    assert isinstance(col.type, JSONB)


def test_prediction_has_composite_index_lead_id_scored_at():
    idx_names = {idx.name for idx in Prediction.__table__.indexes}
    assert "ix_predictions_lead_id_scored_at" in idx_names


def test_prediction_has_relationship_back_to_lead():
    rel = Prediction.__mapper__.relationships["lead"]
    assert rel.back_populates == "predictions"


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------

def test_model_registry_version_is_unique_and_not_nullable():
    col = ModelRegistry.__table__.c.version
    assert col.unique is True
    assert col.nullable is False


def test_model_registry_artifact_path_is_not_nullable():
    col = ModelRegistry.__table__.c.artifact_path
    assert col.nullable is False


def test_model_registry_is_active_defaults_false():
    col = ModelRegistry.__table__.c.is_active
    assert col.server_default is not None
    assert col.server_default.arg == "false"


def test_model_registry_trained_at_is_not_nullable():
    col = ModelRegistry.__table__.c.trained_at
    assert col.nullable is False


def test_model_registry_has_partial_index_on_is_active():
    partial = [
        idx for idx in ModelRegistry.__table__.indexes
        if idx.name == "ix_model_registry_active"
        and idx.dialect_kwargs.get("postgresql_where") is not None
    ]
    assert len(partial) == 1


def test_model_registry_metrics_uses_jsonb():
    col = ModelRegistry.__table__.c.metrics
    assert isinstance(col.type, JSONB)


# ---------------------------------------------------------------------------
# CRMSyncLog
# ---------------------------------------------------------------------------

def test_crm_sync_log_lead_id_is_foreign_key():
    col = CRMSyncLog.__table__.c.lead_id
    fk = list(col.foreign_keys)
    assert len(fk) == 1
    assert fk[0].target_fullname == "leads.id"


def test_crm_sync_log_status_defaults_to_pending():
    col = CRMSyncLog.__table__.c.status
    assert col.server_default is not None
    assert col.server_default.arg == "pending"


def test_crm_sync_log_status_check_constraint_values():
    checks = [
        c for c in CRMSyncLog.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_crm_sync_log_status"
    ]
    assert len(checks) == 1
    text = str(checks[0].sqltext)
    for status in ("success", "failed", "pending"):
        assert status in text


def test_crm_sync_log_error_message_uses_text_type():
    """error_message should be Text (unlimited length), not String."""
    col = CRMSyncLog.__table__.c.error_message
    assert isinstance(col.type, Text)


def test_crm_sync_log_has_composite_index_source_external():
    idx_names = {idx.name for idx in CRMSyncLog.__table__.indexes}
    assert "ix_crm_sync_log_source_external" in idx_names


def test_crm_sync_log_action_is_not_nullable():
    col = CRMSyncLog.__table__.c.action
    assert col.nullable is False


def test_crm_sync_log_has_relationship_back_to_lead():
    rel = CRMSyncLog.__mapper__.relationships["lead"]
    assert rel.back_populates == "sync_logs"


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

def test_models_package_exports_all_models():
    from src.models import Base, Lead, Prediction, ModelRegistry, CRMSyncLog
    # Verify these are the actual classes, not re-exports of something else
    assert Lead.__tablename__ == "leads"
    assert Prediction.__tablename__ == "predictions"
    assert ModelRegistry.__tablename__ == "model_registry"
    assert CRMSyncLog.__tablename__ == "crm_sync_log"


# ---------------------------------------------------------------------------
# Database utilities
# ---------------------------------------------------------------------------

def test_get_session_is_async_generator():
    import inspect
    from src.models.database import get_session
    assert inspect.isasyncgenfunction(get_session)
