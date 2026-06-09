from google import genai
from dotenv import load_dotenv
import os
from tools.calendar_tools import get_events

get_events("2026-06-08")
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello and introduce yourself in one sentence."
)

print(response.text)