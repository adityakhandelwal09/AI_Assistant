from google import genai
from google.genai import types
from datetime import date, timedelta
from tools.schemas import get_events_schema, create_event_schema, delete_event_schema, edit_event_schema, search_emails_schema, get_email_content_schema, draft_email_schema, search_messages_schema, get_conversation_schema, search_drive_schema, get_file_content_schema
from tools.calendar_tools import get_events, create_event, delete_event, edit_event
from tools.gmail_tools import search_emails, get_email_content, draft_email
from tools.imessage_tools import search_messages, get_conversation
from tools.google_drive_tools import search_drive, get_file_content

def run_agent(prompt, content):
    client = genai.Client()
    tools = types.Tool(
        function_declarations=[
            get_events_schema, 
            create_event_schema, 
            delete_event_schema,
            edit_event_schema,
            search_emails_schema,
            get_email_content_schema,
            draft_email_schema,
            search_messages_schema,
            get_conversation_schema, 
            search_drive_schema, 
            get_file_content_schema
        ]
    )
    config = types.GenerateContentConfig(
        tools=[tools],
        system_instruction=f"Today's date is {date.today()}. You are a personal assistant with access to the user's calendar, email, messages, an google drive"
    )

    #append to content from the start so model has a recurring memory
    content.append(
        types.Content(
            role="user", parts=[types.Part(text=prompt)]
        )
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=content,
        config=config,
    )

    function_dict = {
        "get_events": get_events,
        "create_event": create_event,
        "delete_event": delete_event,
        "edit_event": edit_event,
        "search_emails": search_emails,
        "get_email_content": get_email_content,
        "draft_email": draft_email,
        "search_messages": search_messages,
        "get_conversation": get_conversation,
        "search_drive": search_drive,
        "get_file_content": get_file_content,
    }

    while True:
        parts = response.candidates[0].content.parts
        function_calls = [part.function_call for part in parts if part.function_call]

        if not function_calls:
            content.append(response.candidates[0].content)
            return response.text, content

        function_response_parts = []
        for function_call in function_calls:
            try:
                if function_call.name not in function_dict:
                    raise KeyError(f"Unknown tool: {function_call.name}")
                function_name = function_dict[function_call.name]
                function_call_args = dict(function_call.args)
                result = function_name(**function_call_args)
            except Exception as e:
                result = {"error": str(e), "tool": function_call.name}

            function_response_parts.append(
                types.Part.from_function_response(
                    name=function_call.name,
                    response={"result": result},
                )
            )

        content.append(response.candidates[0].content)
        content.append(types.Content(role="user", parts=function_response_parts))

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=config,
            contents=content,
        )