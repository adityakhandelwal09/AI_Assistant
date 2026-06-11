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

#helper function to recursively search through the parts of an email payload to find the text/plain body content
def get_body_from_parts(parts):
    for part in parts:
        if part.get("mimeType") == "text/plain":
            return part.get("body", {}).get("data")
        elif "multipart" in part.get("mimeType"):
            subparts = part.get("parts", [])
            body = get_body_from_parts(subparts)
            if body:
                return body
    return None

#given a message ID, retrieves the full email content (including body) and decodes it from base64
def get_email_content(message_id):
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    parts = msg.get("payload", {}).get("parts", [])
    email_body = get_body_from_parts(parts)
    print(base64.urlsafe_b64decode(email_body).decode('utf-8'))
    return base64.urlsafe_b64decode(email_body).decode('utf-8')
