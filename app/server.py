import logging

from flask import Flask, request, jsonify

from .auth import require_api_key
from .mailer import send_alert, MailSendError, ConfigError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("email-notify")

app = Flask(__name__)


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


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@app.post("/api/send")
@require_api_key
def send():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "invalid or missing JSON body"}), 400

    err = _validate_payload(payload)
    if err:
        return jsonify({"error": err}), 400

    recipients = payload["recipients"]
    subject = payload["subject"]
    message_body = payload["message_body"]

    try:
        send_alert(recipients, subject, message_body)
    except ConfigError as exc:
        logger.error("config error: %s", exc)
        return jsonify({"error": "server_misconfigured", "detail": str(exc)}), 500
    except MailSendError as exc:
        logger.error("smtp failed: %s", exc)
        return jsonify({"error": "smtp_failed", "detail": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("unexpected error")
        return jsonify({"error": "internal", "detail": str(exc)}), 500

    logger.info(
        "sent subject=%r recipients_count=%d path=%s",
        subject, len(recipients), request.path,
    )
    return jsonify({"status": "sent", "recipients": recipients}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
