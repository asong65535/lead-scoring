from src.models.base import Base, TimestampMixin


def test_base_has_metadata():
    assert hasattr(Base, "metadata")


def test_timestamp_mixin_has_expected_columns():
    assert hasattr(TimestampMixin, "id")
    assert hasattr(TimestampMixin, "created_at")
    assert hasattr(TimestampMixin, "updated_at")
