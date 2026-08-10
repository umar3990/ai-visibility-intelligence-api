"""Consistent JSON error envelope + handlers, registered on the app in
create_app(). Every error response has the same shape:
{"error": {"code": "SOME_CODE", "message": "human readable"}}
"""
from flask import jsonify


class APIError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(APIError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationAPIError(APIError):
    status_code = 422
    code = "VALIDATION_ERROR"


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify({"error": {"code": err.code, "message": err.message}}), err.status_code

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Resource not found"}}), 404

    @app.errorhandler(405)
    def handle_405(err):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": str(err)}}), 405

    @app.errorhandler(429)
    def handle_429(err):
        return jsonify({"error": {"code": "RATE_LIMITED", "message": str(err.description)}}), 429

    @app.errorhandler(500)
    def handle_500(err):
        app.logger.exception("Unhandled exception")
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}}), 500
