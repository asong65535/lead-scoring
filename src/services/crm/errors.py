class CRMError(Exception):
    """Base exception for all CRM operations."""


class CRMAuthError(CRMError):
    """CRM credentials are invalid or expired."""


class CRMRateLimitError(CRMError):
    """CRM rate limit exceeded."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class CRMContactNotFoundError(CRMError):
    """Contact not found in CRM."""

    def __init__(self, external_id: str):
        self.external_id = external_id
        super().__init__(f"Contact not found: {external_id}")


class CRMWritebackError(CRMError):
    """Failed to write data back to CRM."""
