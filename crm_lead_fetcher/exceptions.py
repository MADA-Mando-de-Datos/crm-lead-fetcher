class LeadSourceError(Exception):
    """Base exception for all lead mining source errors."""


class LeadSourceConnectionError(LeadSourceError):
    """Network connection, timeout or unreachable host error."""


class LeadSourceAuthError(LeadSourceError):
    """Authentication failure, missing token or invalid API key."""


class LeadSourceQuotaError(LeadSourceError):
    """API quota or rate limit exceeded."""


class LeadSourceDataError(LeadSourceError):
    """Unexpected payload format or invalid API response."""
