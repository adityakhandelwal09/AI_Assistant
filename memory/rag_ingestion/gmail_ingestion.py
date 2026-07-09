import base64
import re
from tools.gmail_tools import search_emails, get_email_content, get_google_service, get_body_from_parts

service = get_google_service("gmail", "v1")

def get_full_headers(message_id):
    #fetch all headers for a message, not just the basic ones
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

def get_thread_messages(thread_id):
    #gets all individual messages in a thread as separate turns, each with their own sender, date, and content.
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    
    turns = []
    for message in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        
        # extract body content (reuse your existing body extraction logic)
        parts = message.get("payload", {}).get("parts", [])
        body = get_body_from_parts(parts) if parts else message.get("payload", {}).get("body", {}).get("data")


        if body:
            content = base64.urlsafe_b64decode(body).decode("utf-8")
            match = re.search(r"On.+?wrote:", content, re.DOTALL)
            if match:
                content = content[:match.start()]
            content = strip_signature_and_disclaimers(content)
        else:
            content = ""
        
        turns.append({
            "sender": headers.get("From", "Unknown"),
            "date": headers.get("Date", ""),
            "subject": headers.get("Subject", ""),
            "content": content,
            "message_id": message.get("id")
        })
    
    return turns
