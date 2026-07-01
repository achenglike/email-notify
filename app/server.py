import contextlib
import logging

import anyio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import is_authorized
from .mailer import ConfigError, MailSendError, send_alert
from .mcp_tools import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("email-notify")

mcp_streamable = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


def _is_non_empty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_payload(payload):
    if not isinstance(payload, dict):
        return "request body must be a JSON object"

    recipients = payload.get("recipients")
    if not isinstance(recipients, list) or len(recipients) == 0:
        return "'recipients' must be a non-empty array"
    if not all(isinstance(r, str) and "@" in r for r in recipients):
        return "'recipients' must be an array of valid email strings"

    if not _is_non_empty_str(payload.get("subject")):
        return "'subject' must be a non-empty string"

    if not _is_non_empty_str(payload.get("message_body")):
        return "'message_body' must be a non-empty string"

    return None


async def healthz(request: Request):
    return JSONResponse({"status": "ok"})


async def api_send(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid or missing JSON body"}, status_code=400)

    err = _validate_payload(payload)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    recipients = payload["recipients"]
    subject = payload["subject"]
    message_body = payload["message_body"]

    try:
        await anyio.to_thread.run_sync(
            send_alert, recipients, subject, message_body
        )
    except ConfigError as exc:
        logger.error("config error: %s", exc)
        return JSONResponse(
            {"error": "server_misconfigured", "detail": str(exc)}, status_code=500
        )
    except MailSendError as exc:
        logger.error("smtp failed: %s", exc)
        return JSONResponse(
            {"error": "smtp_failed", "detail": str(exc)}, status_code=502
        )
    except Exception as exc:
        logger.exception("unexpected error")
        return JSONResponse({"error": "internal", "detail": str(exc)}, status_code=500)

    logger.info(
        "sent subject=%r recipients_count=%d path=%s",
        subject, len(recipients), request.url.path,
    )
    return JSONResponse({"status": "sent", "recipients": recipients})


async def _unauthorized(scope, receive, send):
    response = JSONResponse({"error": "unauthorized"}, status_code=401)
    await response(scope, receive, send)


class BearerAuthMiddleware:
    """Validate Bearer token for /api/send and /mcp; exempt /healthz.

    Stateless: wraps the ASGI app, no session storage.
    """

    PUBLIC_PATHS = {"/healthz"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        if path in self.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        auth_header = ""
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name == b"authorization":
                auth_header = raw_value.decode("latin-1")
                break

        if not is_authorized(auth_header):
            return await _unauthorized(scope, receive, send)

        return await self.app(scope, receive, send)


inner = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/api/send", api_send, methods=["POST"]),
        Mount("/mcp", app=mcp_streamable),
    ],
    lifespan=lifespan,
)
app = BearerAuthMiddleware(inner)
