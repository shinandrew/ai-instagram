import logging
import resend
from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str, unsubscribe_url: str = "") -> None:
    if not settings.resend_api_key or not settings.email_from:
        return
    try:
        resend.api_key = settings.resend_api_key
        footer = ""
        if unsubscribe_url:
            footer = f'<p style="margin-top:24px;font-size:12px;color:#999;">Don\'t want these emails? <a href="{unsubscribe_url}" style="color:#999;">Unsubscribe</a></p>'
        resend.Emails.send({
            "from": settings.email_from,
            "to": to,
            "subject": subject,
            "html": html + footer,
        })
    except Exception as e:
        logger.warning("Email send failed: %s", e)
