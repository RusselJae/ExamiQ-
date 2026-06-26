"""AI service exceptions."""


class AIServiceUnavailableError(Exception):
    """Raised when all AI provider attempts fail."""

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)
