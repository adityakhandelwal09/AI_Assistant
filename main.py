from google import genai
import datetime as datetime
from datetime import date, timedelta
import os
from tools.calendar_tools import get_events, create_event, delete_event, edit_event
from tools.gmail_tools import search_emails, get_email_content, draft_email
from agents.agent import run_agent
from tools.imessage_tools import search_messages, get_conversation
from tools.google_drive_tools import search_drive, get_file_content
from memory.conversation_memory import load_history, history_to_content, add_to_history
from dotenv import load_dotenv

load_dotenv()

# load previous history on startup
history = load_history()
content = history_to_content(history)

if history:
    print(f"Welcome back! Loaded {len(history)} previous messages.")
else:
    print("Starting fresh conversation.")

while True:
    user_input = input("Ask Away: ")
    if user_input.lower() == "quit":
        break
    
    # add user message to history
    history = add_to_history(history, "user", user_input)
    
    response_text, content = run_agent(user_input, content)
    print()
    print(f"ARIA: {response_text}")
    
    # add ARIA's response to history
    history = add_to_history(history, "model", response_text)

'''
for item in content:
  print(item)
  print("------")
'''

#print(search_drive("Janelia"))
#print(get_file_content("15Zh38Do0l_a5T7LIT5xcPzwe8hK9b4ndZxVKEDItHz8"))
#get_events("2026-06-08")
#create_event("Kravitz Appointment", "Wisdom teet consultation", datetime.datetime(2026, 6, 10, 15, 40), datetime.datetime(2026, 6, 10, 16, 20), False)
#create_event("Aditi's Birthday", "", datetime.datetime(2026, 6, 19), datetime.datetime(2026, 6, 19), True)
#delete_event("13qsl87u02874gll5c149087e8") 

#print(search_emails("from:Heath"))
#get_email_content("195c850c48974ddc") 
#print(draft_email("test@example.com", "Test Subject", "Test Body THIS WOULD BE SOOO COOOL IF IT WORKED"))


'''
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello and introduce yourself in one sentence."
)

print(response.text)
'''