import os
from typing import TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from .mailer import send_alert, MailSendError

mcp = FastMCP(
    "email-notify",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)

_default_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_allowed_env = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
if _allowed_env == "*":
    # 全放开：关闭 DNS rebinding 防护，仅靠 Bearer Token 鉴权 + 网络隔离兜底
    # 适合 Docker 部署 / 反代后端 / 内网场景
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
else:
    _extra_hosts = [h.strip() for h in _allowed_env.split(",") if h.strip()]
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*_default_hosts, *_extra_hosts],
    )


class SendEmailResult(TypedDict):
    status: str
    recipients: list[str]


@mcp.tool()
def send_email(recipients: list[str], subject: str, message_body: str) -> SendEmailResult:
    """Send an HTML email to one or more recipients.

    Args:
        recipients: List of recipient email addresses (non-empty).
        subject: Email subject line (non-empty).
        message_body: HTML body content of the email (non-empty).

    Returns:
        A dict with the delivery status and the recipients it was sent to.
    """
    if not isinstance(recipients, list) or not recipients:
        raise ToolError("'recipients' must be a non-empty array")
    if not all(isinstance(r, str) and "@" in r for r in recipients):
        raise ToolError("'recipients' must be an array of valid email strings")
    if not isinstance(subject, str) or not subject.strip():
        raise ToolError("'subject' must be a non-empty string")
    if not isinstance(message_body, str) or not message_body.strip():
        raise ToolError("'message_body' must be a non-empty string")

    try:
        send_alert(recipients, subject, message_body)
    except MailSendError as exc:
        raise ToolError(f"smtp failed: {exc}") from exc

    return {"status": "sent", "recipients": recipients}
