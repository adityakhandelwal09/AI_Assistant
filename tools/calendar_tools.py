import pytz
from datetime import datetime, timedelta
from config.auth import get_google_service
service = get_google_service("calendar", "v3")


def list_calendars():
    #fetches every calendar visible to the authenticated Google account.
    calendars = []
    page_token = None
    while True:
        response = service.calendarList().list(
            showHidden=False,
            pageToken=page_token,
        ).execute()
        calendars.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return calendars


def list_calendar_events(time_min=None, time_max=None, max_events=None, calendar_ids=None):
    #fetches events from every selected calendar, if calendar_ids=None, fetches all
    calendars = list_calendars()
    if calendar_ids is not None:
        calendar_ids = set(calendar_ids)
        calendars = [c for c in calendars if c["id"] in calendar_ids]

    events = []
    for calendar in calendars:
        page_token = None
        calendar_id = calendar["id"]
        calendar_name = calendar.get("summary") or calendar_id

        while True:
            request = {
                "calendarId": calendar_id,
                "singleEvents": True,
                "showDeleted": False,
                "orderBy": "startTime",
                "pageToken": page_token,
            }
            if time_min:
                request["timeMin"] = time_min
            if time_max:
                request["timeMax"] = time_max
            if max_events is not None:
                request["maxResults"] = min(max_events - len(events), 2500)

            response = service.events().list(**request).execute()
            for event in response.get("items", []):
                events.append({
                    **event,
                    "calendar_id": calendar_id,
                    "calendar_name": calendar_name,
                })

            if max_events is not None and len(events) >= max_events:
                return events[:max_events]

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return events

def get_events(date_str):
    #convenience wrapper: all events on a single day, formatted for agent/LLM use
    datetime_obj = datetime.fromisoformat(date_str)
    time_min = datetime_obj.replace(hour=0, minute=0, second=0)
    time_max = datetime_obj.replace(hour=23, minute=59, second=59)
    #adds the local timezone because Google Calendar requires RFC 3339 offsets.
    eastern = pytz.timezone("US/Eastern")
    eastern_time_min = eastern.localize(time_min).isoformat()
    eastern_time_max = eastern.localize(time_max).isoformat()
    return list_calendar_events(eastern_time_min, eastern_time_max)


def build_event_body(title, start_datetime, end_datetime, all_day, description=""):
    start_datetime = datetime.fromisoformat(start_datetime)
    end_datetime = datetime.fromisoformat(end_datetime)
    body = {
        "summary": title,
        "description": description,
    }

    if all_day:
        body["start"] = {
            "date": start_datetime.date().isoformat()
        }
        body["end"] = {
            "date": (end_datetime.date() + timedelta(days=1)).isoformat() #all-day events end the day after the last day of the event
        }
    else:
        body["start"] = {
                "dateTime": start_datetime.isoformat(),
                "timeZone": "US/Eastern"
        },
        body["end"] = {
                "dateTime": end_datetime.isoformat(),
                "timeZone": "US/Eastern"
        }
    return body

def create_event(title, start_datetime, end_datetime, all_day, description=""):
    body = build_event_body(title, start_datetime, end_datetime, all_day, description)
    created_event = service.events().insert(calendarId='primary', body=body).execute()
    print(f"Event created: {created_event.get('htmlLink')}, ID: {created_event.get('id')}")
    return {
        "event_id": created_event.get("id"),
        "html_link": created_event.get("htmlLink"),
        "status": "created"
    }

def delete_event(event_id):
    service.events().delete(calendarId='primary', eventId=event_id).execute()
    print(f"Event with ID {event_id} deleted.")
    return {
        "event_id": event_id,
        "status": "deleted"
    }

def edit_event(title, start_datetime, end_datetime, all_day, event_id, description=""):
    body = build_event_body(title, start_datetime, end_datetime, all_day, description)
    updated_event = service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    print(f"Event edited: {updated_event.get('htmlLink')}, ID: {updated_event.get('id')}")
    return {
        "event_id": updated_event.get("id"),
        "html_link": updated_event.get("htmlLink"),
        "status": "updated"
    }

