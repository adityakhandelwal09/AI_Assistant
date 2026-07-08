import base64
import re
from tools.gmail_tools import get_google_service

def get_full_headers(message_id):
    #fetch all headers for a message, not just the basic ones
    service = get_google_service("gmail", "v1")
    msg = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
    headers = msg.get("payload", {}).get("headers", [])
    return {h["name"] for h in headers}


def is_promotional(headers):
    #figure out if an email is a newsletter, promotion, or marketing email based on header signals

    # Signal 1: List-Unsubscribe header - the strongest signal
    if "List-Unsubscribe" in headers or "List-Unsubscribe-Post" in headers:
        return True
    
    # Signal 2: Common bulk-mail headers
    if headers.get("Precedence", "").lower() in ["bulk", "junk", "list"]:
        return True
    
    # Signal 3: Common no-reply patterns in sender
    sender = headers.get("From", "").lower()
    no_reply_patterns = ["noreply", "no-reply", "donotreply", "newsletter", "marketing", "notifications@"]
    if any(pattern in sender for pattern in no_reply_patterns):
        return True
    
    return False

def strip_signature_and_disclaimers(email_text):
    """
    Removes common email signatures, disclaimers, and footer boilerplate.
    """
    # Common signature delimiters
    signature_markers = [
        r"--\s*\n",  # standard email signature delimiter "-- "
        r"Sent from my iPhone",
        r"Sent from my Android",
        r"Get Outlook for",
        r"This email and any attachments",
        r"CONFIDENTIALITY NOTICE",
        r"This message contains confidential",
    ]
    
    text = email_text
    for marker in signature_markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]  # cut off everything from the marker onward
    
    return text.strip()