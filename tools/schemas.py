get_events_schema = {
    "name": "get_events",
    "description": "Retrieves the user's calendar events for a specific date. Use this when the user asks about their schedule, availability, or what's happening on a given day.",
    "parameters": {
        "type": "object",
        "properties": {
            "date_str": {
                "type": "string",
                "description": "The date to check, in YYYY-MM-DD format. Today's date should be calculated based on the current date if the user says things like 'today', 'tomorrow', or a specific day name.",
            },
        },
        "required": ["date_str"],
    },
}

create_event_schema = {
    "name": "create_event",
    "description": "Creates a new event on the user's Google Calendar. Use this when the user asks to add, schedule, or create a calendar event.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the calendar event"
            },
            "description": {
                "type": "string",
                "description": "Optional description or notes for the event"
            },
            "start_datetime": {
                "type": "string",
                "description": "Start date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"
            },
            "end_datetime": {
                "type": "string",
                "description": "End date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)"
            },
            "all_day": {
                "type": "boolean",
                "description": "Whether the event lasts all day"
            }
        },
        "required": ["title", "start_datetime", "end_datetime", "all_day"]
    }
}

delete_event_schema = {
    "name": "delete_event",
    "description": "Deletes a calendar event by its event ID. Use this when the user asks to cancel or remove a calendar event.",
    "parameters": {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The ID of the calendar event to delete"
            }
        },
        "required": ["event_id"]
    }
}

search_emails_schema = {
    "name": "search_emails",
    "description": "Searches the user's Gmail inbox using a query string. For searching by sender name use the 'from:' prefix and do not insert any name titles (Dr. Mrs. Ms, etc). For email addresses use 'from:email@example.com'. Keep queries simple — Gmail searches across all fields by default. When searching emails for multiple people or multiple events, search for each person or event separately",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query (e.g. sender, subject, keywords)"
            },
            "max_results": {
                "type": "integer",
                "description": "Default is 5. Find 5 emails unless the user specifically asks for fewer or more results or there aren't 5 emails associated with the specific query.",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

get_email_content_schema = {
    "name": "get_email_content",
    "description": "Retrieves the full body text of a specific email. Use this after an email has been identified.",
    "parameters": {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID of the email"
            }
        },
        "required": ["message_id"]
    }
}

draft_email_schema = {
    "name": "draft_email",
    "description": "Creates a draft email in Gmail without sending it. Use this when the user asks to write or draft an email.",
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address"
            },
            "subject": {
                "type": "string",
                "description": "Subject line of the email"
            },
            "body": {
                "type": "string",
                "description": "Email body text"
            }
        },
        "required": ["to", "subject", "body"]
    }
}