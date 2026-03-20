"""Custom exceptions for API error handling.

Each exception maps to an HTTP status code. Exception handlers in main.py
convert these to JSON responses.
"""

from uuid import UUID


class LeadNotFoundError(Exception):
    """Raised when a lead ID does not exist in the database."""

    def __init__(self, lead_id: UUID):
        self.lead_id = lead_id
        super().__init__(f"Lead not found: {lead_id}")


class ModelNotLoadedError(Exception):
    """Raised when scoring is attempted but no model is loaded."""

    def __init__(self):
        super().__init__("Model not available")


class FeatureComputationError(Exception):
    """Raised when feature computation fails for a lead."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)
