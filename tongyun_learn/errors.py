import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("tongyun_learn")


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.status_code = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = jsonable_encoder(exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "请求参数不合法",
                    "details": details,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        message = str(exc.detail) if exc.detail else ("Not Found" if exc.status_code == 404 else "HTTP Error")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal",
                    "message": "服务内部错误",
                }
            },
        )
