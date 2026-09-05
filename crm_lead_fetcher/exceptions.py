class LeadSourceError(Exception):
    """Base exception for all lead mining source errors."""
    pass


class LeadSourceConnectionError(LeadSourceError):
    """Network connection, timeout or unreachable host error."""
    pass


class LeadSourceAuthError(LeadSourceError):
    """Authentication failure, missing token or invalid API key."""
    pass


class LeadSourceQuotaError(LeadSourceError):
    """API quota or rate limit exceeded."""
    pass


class LeadSourceDataError(LeadSourceError):
    """Unexpected payload format or invalid API response."""
    pass
