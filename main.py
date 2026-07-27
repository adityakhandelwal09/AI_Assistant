from email import message_from_string
from google import genai
import datetime as datetime
from datetime import date, timedelta
import os
from config.auth import get_google_service
from memory.rag_ingestion.gmail_ingestion import get_thread_messages
from tools.calendar_tools import get_events, create_event, delete_event, edit_event
from tools.gmail_tools import search_emails, get_email_content, draft_email
from agents.agent import run_agent
from tools.imessage_tools import search_messages, get_conversation
from tools.google_drive_tools import search_drive, get_file_content
from memory.conversation_memory import load_history, history_to_content, add_to_history
from memory.vector_store import add_chunks, search, generate_query_variations, multi_query_search, clear_collection
from memory.rag_ingestion.gmail_ingestion import ingest_all_primary_emails, create_chunk
from dotenv import load_dotenv 
load_dotenv()



queries = [
    "nova transcript for dual enrollment",
    "did i get any free AI credits?"
]

for q in queries:
    print(f"QUERY: {q}")
    print("=" * 50)
    results = multi_query_search(q, "gmail")
    for r in results[:5]:
        print(r["text"][:200])
        print("---")
    print("\n")


'''
clear_collection("gmail")
ingest_all_primary_emails(max_threads=300)
'''












'''
def check_labels_for_recent_emails(count=50):
    service = get_google_service("gmail", "v1")
    
    emails = search_emails(query="", max_results=count)
    
    for email in emails:
        msg = service.users().messages().get(
            userId="me", 
            id=email["id"], 
            format="minimal"
        ).execute()
        
        label_ids = msg.get("labelIds", [])
        
        print(f"Subject: {email['subject']}")
        print(f"Thread ID: {email['thread_id']}")
        print(f"Labels: {label_ids}")
        print("---")

check_labels_for_recent_emails(50)
'''

#print(headers[0])

#thread_id = "19f90c25e84d3998"
#create_chunk(thread_id)
'''
text = "for the NEW TJHSST Hall of Honor! Dear TJHSST Community, A huge thank you to everyone who has already stepped up and submitted a nomination for the inaugural Thomas Jefferson High School for Science and Technology (TJHSST) Hall of Honor class of 2026! Our alumni have consistently changed the world, making profound impacts across all facets of life. Whether their incredible accomplishments are in science, technology, engineering, programming, medicine, education, government, entertainment, athletics, or something else, we want to celebrate them. Who makes the ideal candidate? We aren't just looking for the richest or most famous graduates. The ideal Hall of Honor inductee is: · An individual who has lived a true life of honor. · An inspiring role model whom current TJ students can look up to and see as a reflection of their own future potential. How You Can Make an Impact: Help us cement the legacy of our greatest alumni by telling their stories! If you know someone deserving of a place in TJHSST’s Hall of Honor, please fill out our [nomination Google Form](). · Deadline: We are accepting submissions through Wednesday, July 29. · What to Include: Please provide as much supporting information as possible to help your nominee stand out. If you have any questions about the nomination process, please don't hesitate to reach out to our TJ Director of Communications, Mike Roth, at mbroth@fcps.edu"
client_id = genai.Client()
response = client_id.models.count_tokens(
        model="gemini-2.5-flash",
        contents=text
    )
print(response.total_tokens)
'''
'''
email = search_emails(query="ONE WEEK LEFT to Nominate for the NEW TJHSST Hall of Honor!", max_results=1)
print(email)
print()
thread_id = email[0].get("thread_id")
create_chunk(thread_id)
'''

'''
clear_collection("gmail")
ingest_all_emails(max_emails=20)

results = multi_query_search("what school wished aditya happy birthday", "gmail", n_results_per_query=3)
for r in results:
    print(r["text"])
    print("---")
'''

'''
emails = search_emails(query="", max_results=4)
for email in emails:
    print(email["subject"], "-", email["date"], "-", email["thread_id"])
'''

'''
emails = search_emails(query="", max_results=1)
turns = get_thread_messages(emails[0]["thread_id"])

for turn in turns:
    print(turn["sender"], "-", turn["date"])
    print(turn["content"])
    print("---")
print()
'''

'''

def get_full_headers(message_id):
    """Fetch all headers for a message, not just the basic ones"""
    service = get_google_service("gmail", "v1")
    msg = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
    headers = msg.get("payload", {}).get("headers", [])
    return {h["name"] for h in headers}


def is_promotional(headers):
    """
    Determines if an email is a newsletter, promotion, or marketing email
    based on header signals.
    """
    # Signal 1: List-Unsubscribe header - the strongest signal
    if "List-Unsubscribe" in headers:
        return True
    
emails = search_emails(query="", max_results=10)

for email in emails:
    headers = get_full_headers(email["id"])
    promotional = is_promotional(headers)
    print(f"{email['subject']} — Promotional: {promotional}")

'''


'''
clear_collection("messages")

tricky_chunks = [
    {"text": "Aditya used to love spicy Indian curries but after getting food poisoning last year, he can't stand spicy food anymore", "metadata": {"id": "1", "source": "test"}},
    {"text": "Aditya's favorite restaurant growing up was a spicy Thai place downtown that he visited every weekend", "metadata": {"id": "2", "source": "test"}},
    {"text": "When people ask Aditya about spicy food, he always says his tolerance used to be really high back in middle school", "metadata": {"id": "3", "source": "test"}},
    {"text": "Aditya specifically requested mild seasoning when ordering butter chicken last week, saying his stomach can't handle heat anymore", "metadata": {"id": "4", "source": "test"}},
    {"text": "Aarav loves extremely spicy food and once did a ghost pepper challenge with his friends", "metadata": {"id": "5", "source": "test"}},
    {"text": "Aditya's mom makes a mild version of biryani because the whole family prefers less heat in their meals now", "metadata": {"id": "6", "source": "test"}},
]
print()
add_chunks(tricky_chunks, "messages")
print("PLAIN SEARCH (no multi-query, no rerank):")
results = multi_query_search("Should I order Aditya something spicy?", "messages", n_results_per_query=6)
for r in results:
    print(r["text"], "-", r["distance"])

#print(generate_query_variations("Should I order Aditya something spicy?"))
'''
'''
print("=" * 60)
print("TRICKY QUERY: Should I order Aditya something spicy?")
print("=" * 60)
results = multi_query_search("Should I order Aditya something spicy?", "messages", n_results_per_query=6)
for r in results:
    print(r)
    print()
'''

'''
print("=" * 60)
print("TRICKY QUERY: Should I order Aditya something spicy?")
print("=" * 60)
results = search("Should I order Aditya something spicy?", "messages", n_results=6)
for r in results:
    print(r)
    print()
'''
'''
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
