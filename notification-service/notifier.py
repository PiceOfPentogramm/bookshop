import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_from = os.getenv("SMTP_FROM", self.smtp_user or "")
        self.enabled = bool(self.smtp_user)
        if not self.enabled:
            logger.warning("SMTP_USER not set; email sending disabled")

    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self.enabled:
            logger.info("Email sending skipped (disabled)")
            return False
        try:
            msg = EmailMessage()
            msg["From"] = self.smtp_from or self.smtp_user
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password or "")
                server.send_message(msg)
            logger.info("Email sent to %s", to)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send email to %s: %s", to, exc)
            return False
