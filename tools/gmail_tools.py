import base64
from config.auth import get_google_service

service = get_google_service("gmail", "v1")

def search_emails(query, max_results=5):
    gmail_results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = gmail_results.get("messages", [])
    email_list = []
    for message in messages:
        msg = service.users().messages().get(userId="me", id=message["id"], format="metadata").execute()
        headers = msg.get("payload", {}).get("headers", [])
        for header in headers:
            if header["name"] == "Subject":
                subject = header["value"]
            elif header["name"] == "From":
                sender = header["value"]
            elif header["name"] == "Date":
                date = header["value"]
            elif header["name"] == "To":
                recipient = header["value"]

        email_dict = {"id": message["id"],
                      "thread_id": msg.get("threadId"),
                      "subject": subject,
                      "snippet": msg.get("snippet"),
                      "sender": sender,
                      "recipient": recipient,
                      "date": date}
        email_list.append(email_dict)
        
    return email_list

def get_body_from_parts(parts):
    """======================================================================
    Recursively searches email parts for content. Prefers text/plain,
    falls back to text/html (converted to clean text) if no plain text exists.
    ======================================================================"""
    html_fallback = None
    
    for part in parts:
        mime_type = part.get("mimeType", "")        
        
        if mime_type == "text/plain":
            return part.get("body", {}).get("data"), "plain"
        
        elif mime_type == "text/html" and html_fallback is None:
            html_fallback = part.get("body", {}).get("data")
        
        elif "multipart" in mime_type:
            result, result_type = get_body_from_parts(part.get("parts", []))
            if result_type == "plain":
                return result, "plain"
            elif result and html_fallback is None:
                html_fallback = result
    
    return html_fallback, "html"

#given a message ID, retrieves the full email content (including body) and decodes it from base64
def get_email_content(message_id):
    content = ""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    parts = msg.get("payload", {}).get("parts", [])
    email_body, body_type = get_body_from_parts(parts)
    content = base64.urlsafe_b64decode(email_body).decode("utf-8")
    if body_type == "html":
        content = html_to_clean_text(content)

    if email_body is None:
        email_body = msg.get("payload", {}).get("body", {}).get("data")
        content = base64.urlsafe_b64decode(email_body).decode("utf-8")
    return content

def draft_email(to, subject, body):
    message = f"To: {to}\nSubject: {subject}\n\n{body}"
    encoded_message = base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8")
    draft = {
        "message": {
            "raw": encoded_message

        }
    }
    draft_response = service.users().drafts().create(userId="me", body=draft).execute()

    return {
        "draft_id": draft_response.get("id"),
        "message_id": draft_response.get("message", {}).get("id"),
        "status": "Draft created successfully"
    }

