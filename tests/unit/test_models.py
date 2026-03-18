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
