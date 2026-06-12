from google import genai
import datetime as datetime
from datetime import date, timedelta
from dotenv import load_dotenv
import os
from tools.calendar_tools import get_events, create_event, delete_event
from tools.gmail_tools import search_emails, get_email_content, draft_email
from google import genai
from google.genai import types

#get_events("2026-06-08")
#create_event("Kravitz Appointment", "Wisdom teet consultation", datetime.datetime(2026, 6, 10, 15, 40), datetime.datetime(2026, 6, 10, 16, 20), False)
#create_event("Aditi's Birthday", "", datetime.datetime(2026, 6, 19), datetime.datetime(2026, 6, 19), True)
#delete_event("13qsl87u02874gll5c149087e8") 

#print(search_emails("subject:possible research opportunity"))
#get_email_content("195c850c48974ddc") 
#print(draft_email("test@example.com", "Test Subject", "Test Body THIS WOULD BE SOOO COOOL IF IT WORKED"))

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

client = genai.Client()
tools = types.Tool(function_declarations=[get_events_function])
config = types.GenerateContentConfig(tools=[tools])

# Send request with function declarations
prompt = f'''Today's date is {date.today()}
            What's on my calendar for today? 
            '''

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=config,
)

if response.candidates[0].content.parts[0].function_call:
    function_call = response.candidates[0].content.parts[0].function_call
    function_call_args = dict(function_call.args)
    if function_call.name == "get_events":
        get_events(**function_call_args)

else:
    print("No function call found")
    print(response.text)



'''
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello and introduce yourself in one sentence."
)

print(response.text)
'''