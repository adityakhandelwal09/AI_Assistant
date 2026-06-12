from google import genai
from google.genai import types
from datetime import date, timedelta
from tools.schemas import get_events_schema, create_event_schema, delete_event_schema, search_emails_schema, get_email_content_schema, draft_email_schema
from tools.calendar_tools import get_events, create_event, delete_event
from tools.gmail_tools import search_emails, get_email_content, draft_email

def run_agent(prompt):
    client = genai.Client()
    tools = types.Tool(
        function_declarations=[
            get_events_schema, 
            create_event_schema, 
            delete_event_schema, 
            search_emails_schema,
            get_email_content_schema,
            draft_email_schema
        ]
    )
    config = types.GenerateContentConfig(tools=[tools])

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )

    function_dict = {
        "get_events": get_events,
        "create_event": create_event,
        "delete_event": delete_event,
        "search_emails": search_emails,
        "get_email_content": get_email_content,
        "draft_email": draft_email
    }

    if response.candidates[0].content.parts[0].function_call:
        function_call = response.candidates[0].content.parts[0].function_call
        function_name = function_dict[function_call.name]
        function_call_args = dict(function_call.args)
        result = function_name(**function_call_args)
        result

    else:
        print("No function call found")
        print(response.text)