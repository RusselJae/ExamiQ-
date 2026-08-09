"""AI service exceptions."""


class AIServiceUnavailableError(Exception):
    """Raised when all AI provider attempts fail."""

    def __init__(self, message: str, detail: str | None = None, retryable: bool = False):
        self.message = message
        self.detail = detail
        self.retryable = retryable
        super().__init__(message)
