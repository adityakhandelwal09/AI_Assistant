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

#def get_email_content(message_id):
 #   msg = service.users().messages().get(userId="me", id=message["id"], format="metadata").execute()




