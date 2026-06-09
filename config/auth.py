import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If you change scopes, delete token.json and re-auth
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    """
    Handles Google OAuth and returns a Google Calendar API service object.
    """
    creds = None

    # Paths relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(base_dir, "credentials.json")
    token_path = os.path.join(base_dir, "token.json")

    # Load existing token if it exists
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If no valid credentials, do login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next time
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    # Build Calendar API service
    service = build("calendar", "v3", credentials=creds)
    return service


if __name__ == "__main__":
    service = get_calendar_service()
    print("Calendar service created:", service)