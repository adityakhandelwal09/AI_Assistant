import json
import os
from datetime import datetime
from google.genai import types

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversation_history.json")

def load_history():
    """Load conversation history from JSON file"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    """Save conversation history to JSON file"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def history_to_content(history):
    """Convert plain history dicts back into Gemini types.Content objects"""
    content = []
    for entry in history:
        if entry["role"] == "user":
            content.append(types.Content(
                role="user",
                parts=[types.Part(text=entry["text"])]
            ))
        elif entry["role"] == "model":
            content.append(types.Content(
                role="model",
                parts=[types.Part(text=entry["text"])]
            ))
    return content

def add_to_history(history, role, text):
    """Add a new entry to history"""
    history.append({
        "role": role,
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p")
    })
    save_history(history)
    return history