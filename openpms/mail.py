"""Email notifications. Optional: without a mail server, messages are only
logged, and everything else keeps working.

Settings (environment variables):
  OPENPMS_SMTP_HOST, OPENPMS_SMTP_PORT (587), OPENPMS_SMTP_USER,
  OPENPMS_SMTP_PASSWORD, OPENPMS_SMTP_FROM, OPENPMS_SMTP_STARTTLS (1)
"""
import os
import smtplib
from email.message import EmailMessage

from flask import current_app, has_app_context

# Tests (and anyone curious) can read what would have been sent.
SENT = []


def configured():
    return bool(os.environ.get("OPENPMS_SMTP_HOST"))


def send(repo, to, subject, body):
    org = (repo.get("settings", "organisation_name") or {}).get("setting_value", "Open PMS")
    msg = EmailMessage()
    msg["From"] = os.environ.get("OPENPMS_SMTP_FROM", "openpms@localhost")
    msg["To"] = to
    msg["Subject"] = f"{subject} ({org})"
    msg.set_content(body + "\n\nThis message was sent by Open PMS. You get it because of your role on these measures.")
    SENT.append(msg)
    del SENT[:-200]
    if not configured():
        if has_app_context():
            current_app.logger.info("Email not sent (no mail server set up): %s to %s", subject, to)
        return False
    try:
        with smtplib.SMTP(os.environ["OPENPMS_SMTP_HOST"], int(os.environ.get("OPENPMS_SMTP_PORT", "587")),
                          timeout=15) as smtp:
            if os.environ.get("OPENPMS_SMTP_STARTTLS", "1") == "1":
                smtp.starttls()
            if os.environ.get("OPENPMS_SMTP_USER"):
                smtp.login(os.environ["OPENPMS_SMTP_USER"], os.environ.get("OPENPMS_SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        if has_app_context():
            current_app.logger.warning("Email to %s failed: %s", to, exc)
        return False
