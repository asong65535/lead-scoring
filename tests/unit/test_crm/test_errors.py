from src.services.crm.errors import (
    CRMError,
    CRMAuthError,
    CRMRateLimitError,
    CRMContactNotFoundError,
    CRMWritebackError,
)


def test_all_errors_inherit_from_crm_error():
    assert issubclass(CRMAuthError, CRMError)
    assert issubclass(CRMRateLimitError, CRMError)
    assert issubclass(CRMContactNotFoundError, CRMError)
    assert issubclass(CRMWritebackError, CRMError)


def test_rate_limit_error_carries_retry_after():
    err = CRMRateLimitError(retry_after=30)
    assert err.retry_after == 30
    assert "30" in str(err)


def test_contact_not_found_error_carries_external_id():
    err = CRMContactNotFoundError(external_id="abc-123")
    assert err.external_id == "abc-123"


def test_writeback_error_carries_message():
    err = CRMWritebackError("push failed")
    assert str(err) == "push failed"
