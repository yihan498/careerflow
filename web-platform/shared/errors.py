from __future__ import annotations


class PlatformError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConflictError(PlatformError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 409)


class NotFoundError(PlatformError):
    def __init__(self, message: str):
        super().__init__("not_found", message, 404)

