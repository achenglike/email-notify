import os
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class ConfigError(RuntimeError):
    """SMTP 配置缺失。"""


class MailSendError(RuntimeError):
    """SMTP 发送失败，detail 携带原始异常信息。"""


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required env var: {name}")
    return value


def _build_config() -> dict:
    return {
        "smtp_server": _require_env("SMTP_SERVER"),
        "smtp_port": _require_env("SMTP_PORT"),
        "sender_mail": _require_env("SENDER_MAIL"),
        "sender_pw": _require_env("SENDER_PW"),
    }


def send_alert(recipients, subject, message_body):
    if not recipients:
        raise ValueError("recipients must be a non-empty list")

    cfg = _build_config()

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = cfg["sender_mail"]
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(message_body, "html"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=30) as server:
            server.starttls(context=context)
            server.login(cfg["sender_mail"], cfg["sender_pw"])
            server.sendmail(cfg["sender_mail"], recipients, message.as_string())
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise MailSendError(str(exc)) from exc
