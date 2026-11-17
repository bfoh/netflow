"""Service-layer errors mapped to HTTP responses by the API."""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, details: object = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class ForbiddenError(ServiceError):
    status_code = 403
