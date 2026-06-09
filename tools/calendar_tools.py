import pytz
from datetime import datetime, timedelta
from config.auth import get_calendar_service
service = get_calendar_service()

def get_events(date_str):
    datetime_obj = datetime.fromisoformat(date_str) #use fromisoformat only when the input is in ISO format (YYYY-MM-DD) otherwise use strptime with the appropriate format string
    time_min = datetime_obj.replace(hour=0, minute=0, second=0)
    time_max = datetime_obj.replace(hour=23, minute=59, second=59)

    eastern = pytz.timezone('US/Eastern')
    eastern_min_time = eastern.localize(time_min).isoformat() #localize the naive datetime object to the Eastern timezone and convert it to ISO format string
    eastern_max_time = eastern.localize(time_max).isoformat()

    events_results = service.events().list(calendarId='primary', timeMin=eastern_min_time, timeMax=eastern_max_time, singleEvents=True, orderBy="startTime").execute()
    events = events_results.get("items", [])
    for event in events:
        start_time = event.get("start").get("dateTime", event.get("start").get("date"))
        start_dt = datetime.fromisoformat(start_time)
        end_time = event.get("end").get("dateTime", event.get("end").get("date"))
        end_dt = datetime.fromisoformat(end_time)
        if "T" in start_time:
            start_time = start_dt.strftime("%A, %B %d at %I:%M %p ET") #day of week, month, day, time in 12-hour format with AM/PM
            end_time = end_dt.strftime("%A, %B %d at %I:%M %p ET")
        event_name = event.get("summary", "No Title")
        event_id = event.get("id")
        event_description = event.get("description", "No Description")
        print(f"Event: {event_name}, Start: {start_time}, End: {end_time}, ID: {event_id}, Description: {event_description}")
    return events

def create_event(title, description, start_datetime, end_datetime, all_day):
    if all_day:
        event = {
            "summary": title,
            "description": description,
            "start": {
                "date": start_datetime.date().isoformat()
            },
            "end": {
                "date": (end_datetime.date() + timedelta(days=1)).isoformat() #all-day events end the day after the last day of the event
            }
        }
    else:
        event = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": "US/Eastern"
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": "US/Eastern"
            }
        }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event created: {created_event.get('htmlLink')}")

    