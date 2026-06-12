get_events_function = {
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

create_event_function = {
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

delete_event_function = {
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

search_emails_function = {
    "name": "search_emails",
    "description": "Searches the user's Gmail inbox using a query string. Use this when the user asks to find or look for emails.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query (e.g. sender, subject, keywords)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

get_email_content_function = {
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

draft_email_function = {
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