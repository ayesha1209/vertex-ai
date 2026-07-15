"""Microsoft Graph API email sender using client-credentials flow."""

import base64
import logging

import httpx
import msal

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_access_token() -> str:
    settings = get_settings()
    authority = f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        settings.MS_CLIENT_ID,
        authority=authority,
        client_credential=settings.MS_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        desc = result.get("error_description", result.get("error", "unknown"))
        raise RuntimeError(f"Failed to get Microsoft access token: {desc}")
    return result["access_token"]


def send_email(
    *,
    sender: str,
    to: str,
    subject: str,
    body_html: str,
    attachments: list[dict],
) -> None:
    """Send an email via Microsoft Graph.

    attachments: list of {"name": "file.pdf", "bytes": b"..."}
    """
    token = _get_access_token()

    graph_attachments = [
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": att["name"],
            "contentType": "application/pdf",
            "contentBytes": base64.b64encode(att["bytes"]).decode(),
        }
        for att in attachments
    ]

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": to}}],
            "attachments": graph_attachments,
        },
        "saveToSentItems": True,
    }

    url = f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"Graph API returned {resp.status_code}: {resp.text[:300]}"
        )
    logger.info("Email sent from %s to %s — subject: %s", sender, to, subject)
