from google import genai
from google.genai import types
from datetime import date, timedelta
from tools.schemas import get_events_schema, create_event_schema, delete_event_schema, search_emails_schema, get_email_content_schema, draft_email_schema
from tools.calendar_tools import get_events, create_event, delete_event
from tools.gmail_tools import search_emails, get_email_content, draft_email

def run_agent(prompt, content):
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
    config = types.GenerateContentConfig(
        tools=[tools],
        system_instruction=f"Today's date is {date.today()}. You are a personal assistant with access to the user's calendar and email"
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
        "search_emails": search_emails,
        "get_email_content": get_email_content,
        "draft_email": draft_email
    }

    if not response.candidates[0].content.parts[0].function_call:
        content.append(response.candidates[0].content)
        return response.text, content
    
    while response.candidates[0].content.parts[0].function_call:
        function_calls = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_calls.append(part.function_call)

        results = []
        for function_call in function_calls:
            function_name = function_dict[function_call.name]
            function_call_args = dict(function_call.args)
            results = function_name(**function_call_args)

        #create a function response part
        function_response_part = types.Part.from_function_response(
            name=function_call.name,
            response={"result": results},
        )

        # Append function call and result of the function execution to contents
        content.append(response.candidates[0].content) # Append the content from the model's response.
        content.append(types.Content(role="user", parts=[function_response_part])) # Append the function response

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=config,
            contents=content,
        )
    return response.text, content