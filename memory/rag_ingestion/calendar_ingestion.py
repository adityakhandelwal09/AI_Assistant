from datetime import datetime
import html
import re
import pytz
from bs4 import BeautifulSoup
from config.auth import get_google_service
from tools.calendar_tools import list_calendar_events
from memory.vector_store import add_chunks


EASTERN_TIMEZONE = pytz.timezone("US/Eastern")
service = get_google_service("calendar", "v3")


def normalize_calendar_text(text):
    #normalizes plain or HTML calendar descriptions into readable text
    if not text:
        return ""

    text = BeautifulSoup(html.unescape(text), "html.parser").get_text("\n", strip=True)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def format_event_time(event_time):
    #formats timed and all-day Calendar timestamps for retrieval and display
    if not event_time:
        return "Unknown time"

    if "date" in event_time:
        return f"All day on {event_time['date']}"

    timestamp = event_time.get("dateTime")
    if not timestamp:
        return "Unknown time"

    parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed_time.tzinfo is None:
        parsed_time = EASTERN_TIMEZONE.localize(parsed_time)
    else:
        parsed_time = parsed_time.astimezone(EASTERN_TIMEZONE)
    return parsed_time.strftime("%A, %B %d, %Y at %I:%M %p ET")


def get_event_participants(event):
    #collects readable attendee and organizer identities without duplicating addresses
    participants = []
    organizer = event.get("organizer", {})
    organizer_name = organizer.get("displayName") or organizer.get("email")
    if organizer_name:
        participants.append(f"Organizer: {organizer_name}")

    seen_emails = {organizer.get("email", "").lower()}
    for attendee in event.get("attendees", []):
        email = attendee.get("email", "")
        if email.lower() in seen_emails:
            continue
        seen_emails.add(email.lower())
        participants.append(attendee.get("displayName") or email)

    return participants


def build_display_text(event):
    #builds the entire calendar event into a proper displayable text format
    title = event.get("summary") or "Untitled event"
    lines = []
    if event.get("calendar_name"):
        lines.append(f"Calendar: {event['calendar_name']}")
    lines.extend([
        f"Title: {title}",
        f"Start: {format_event_time(event.get('start'))}",
        f"End: {format_event_time(event.get('end'))}",
    ])

    location = normalize_calendar_text(event.get("location", ""))
    if location:
        lines.append(f"Location: {location}")

    participants = get_event_participants(event)
    if participants:
        lines.append(f"Participants: {', '.join(participants)}")

    description = normalize_calendar_text(event.get("description", ""))
    if description:
        lines.append(f"Description: {description}")

    return "\n".join(lines)


def create_event_chunks(event):
    #creates one chunk per event
    event_id = event.get("id")
    if not event_id:
        return []

    calendar_id = event.get("calendar_id", "primary")
    calendar_name = event.get("calendar_name", calendar_id)
    display_text = build_display_text(event)
    title = event.get("summary") or "Untitled event"
    start_time = format_event_time(event.get("start"))
    end_time = format_event_time(event.get("end"))
    location = normalize_calendar_text(event.get("location", ""))
    participants = get_event_participants(event)

    #uses the whole event for both embedding and display, so title, schedule,
    #location, participants, and description always remain together.
    return [
        {
            "embedding_text": display_text,
            "display_text": display_text,
            "metadata": {
                "thread_id": f"{calendar_id}:{event_id}",
                "message_id": "details",
                "source": "calendar",
                "event_id": event_id,
                "calendar_id": calendar_id,
                "calendar_name": calendar_name,
                "title": title,
                "start": start_time,
                "end": end_time,
                "location": location or "",
                "participants": ", ".join(participants),
                "html_link": event.get("htmlLink", ""),
            },
        }
    ]


def ingest_calendar_events(time_min=None, time_max=None, max_events=None):
    #chunk and embed all calendar events in Chromadb
    events = list_calendar_events(time_min, time_max, max_events)
    chunks = []
    for event in events:
        chunks.extend(create_event_chunks(event))

    if not chunks:
        print("No calendar events found to ingest.")
        return 0

    add_chunks(chunks, "calendar")
    print(f"Ingested {len(chunks)} chunks from {len(events)} calendar events.")
    return len(chunks)
