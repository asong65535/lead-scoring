"""Unit tests for Event model schema contracts."""

from sqlalchemy import CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import JSONB

from src.models.event import Event
from src.models.lead import Lead


def test_event_lead_id_is_foreign_key_to_leads():
    col = Event.__table__.c.lead_id
    fk = list(col.foreign_keys)
    assert len(fk) == 1
    assert fk[0].target_fullname == "leads.id"


def test_event_lead_id_fk_cascades_delete():
    col = Event.__table__.c.lead_id
    fk = list(col.foreign_keys)
    assert fk[0].ondelete == "CASCADE"


def test_event_lead_id_not_nullable():
    col = Event.__table__.c.lead_id
    assert col.nullable is False


def test_event_type_not_nullable():
    col = Event.__table__.c.event_type
    assert col.nullable is False


def test_event_type_check_constraint():
    checks = [
        c for c in Event.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_events_event_type"
    ]
    assert len(checks) == 1
    text = str(checks[0].sqltext)
    for etype in ("page_view", "email_open", "email_click", "form_submission", "email_unsubscribe"):
        assert etype in text


def test_event_occurred_at_not_nullable():
    col = Event.__table__.c.occurred_at
    assert col.nullable is False


def test_event_properties_uses_jsonb():
    col = Event.__table__.c.properties
    assert isinstance(col.type, JSONB)


def test_event_event_name_is_nullable():
    col = Event.__table__.c.event_name
    assert col.nullable is True


def test_event_has_composite_index_lead_id_occurred_at():
    idx_names = {idx.name for idx in Event.__table__.indexes}
    assert "ix_events_lead_id_occurred_at" in idx_names


def test_event_has_index_on_event_type():
    idx_names = {idx.name for idx in Event.__table__.indexes}
    assert "ix_events_event_type" in idx_names


def test_event_has_relationship_back_to_lead():
    rel = Event.__mapper__.relationships["lead"]
    assert rel.back_populates == "events"


def test_lead_has_relationship_to_events():
    assert "events" in Lead.__mapper__.relationships
    rel = Lead.__mapper__.relationships["events"]
    assert rel.back_populates == "lead"


def test_lead_has_converted_at_column():
    col = Lead.__table__.c.converted_at
    assert col.nullable is True
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is True
