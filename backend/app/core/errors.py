"""오류 응답: {"error": {"code": "NOT_FOUND", "message": "..."}} (docs/contracts/api.md).

code 이름은 api.md에 NOT_FOUND 예시만 있다. 나머지(UNAUTHORIZED 등)는 제안이며 확정 전이다.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def unauthorized(message: str = "로그인이 필요합니다") -> ApiError:
    return ApiError(401, "UNAUTHORIZED", message)


def unavailable(message: str = "잠시 후 다시 시도해 주세요") -> ApiError:
    return ApiError(503, "UNAVAILABLE", message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code
        )
