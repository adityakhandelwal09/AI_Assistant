import base64
import html
import json
import os
import re
import unicodedata
from bs4 import BeautifulSoup
from google import genai
from tools.gmail_tools import search_emails, get_email_content, get_google_service, get_body_from_parts
from memory.vector_store import add_chunks
from langchain_text_splitters import RecursiveCharacterTextSplitter

service = get_google_service("gmail", "v1")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYNC_STATE_PATH = os.path.join(BASE_DIR, "gmail_sync_state.json")

USEFUL_URL_DOMAINS = {
    "calendar.google.com",
    "docs.google.com",
    "drive.google.com",
    "meet.google.com",
    "teams.microsoft.com",
    "zoom.us",
    "www.zoom.us",
    "forms.gle",
    "docs.google.com",
    "notion.so",
    "www.notion.so",
}

USEFUL_URL_PATH_HINTS = (
    "/meet/",
    "/document/",
    "/spreadsheets/",
    "/presentation/",
    "/file/",
    "/calendar/",
    "/j/",
    "/wc/",
    "/join",
    "/invitation",
    "/event",
)

def strip_signature_and_disclaimers(email_text):
    """
    Removes common email signatures, disclaimers, and footer boilerplate.
    """
    # Common signature delimiters
    signature_markers = [
        r"--\s*\n",  # standard email signature delimiter "-- "
        r"Sent from my iPhone",
        r"Sent from my Android",
        r"Get Outlook for",
        r"This email and any attachments",
        r"CONFIDENTIALITY NOTICE",
        r"This message contains confidential",
        r"For your security and privacy, please do not reply to this email",
        r"To stop receiving account service communications by email",
        r"Fidelity Brokerage Services LLC",
        r"EMAIL REF#",
        r"All rights reserved",
    ]
    
    text = email_text
    for marker in signature_markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]  #cut off everything from the marker onward
    
    return text.strip()

def compact_url(url):
    """Reduce a URL to a shorter, readable form when possible."""
    match = re.match(r"https?://([^/\s<>)\]]+)(/[^\s<>)\]]*)?", url)
    if not match:
        return url

    domain = match.group(1)
    path = (match.group(2) or "").rstrip("/")

    if path and len(path) <= 32:
        return f"{domain}{path}"

    return domain

def is_useful_url(url):
    """Return True for URLs that are likely useful in retrieval."""
    match = re.match(r"https?://([^/\s<>)\]]+)(/[^\s<>)\]]*)?", url)
    if not match:
        return False

    domain = match.group(1).lower()
    path = (match.group(2) or "").lower()

    if domain in USEFUL_URL_DOMAINS:
        return True

    return any(hint in path for hint in USEFUL_URL_PATH_HINTS)

def normalize_url_token(url):
    """Keep a URL only if it passes the usefulness filter."""
    if is_useful_url(url):
        return compact_url(url)
    return ""

def normalize_email_text(email_text):
    """Normalize email text by removing invisible junk, duplicates, and noise."""
    if not email_text:
        return ""

    text = unicodedata.normalize("NFKC", email_text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\u034f\u200b-\u200f\u2060\ufeff]", "", text)
    text = re.sub(r"\n\s*\(R\)\s*\n", " (R) ", text)
    text = re.sub(r"\(R\)(?=[A-Za-z])", "(R) ", text)
    text = re.sub(r"https?://[^\s<>)\]]+", lambda match: normalize_url_token(match.group(0)), text)
    text = re.sub(r"\s{2,}", " ", text)

    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]

    collapsed_lines = []
    previous_line = None
    for line in lines:
        if not line:
            continue

        if line == previous_line:
            continue

        line = re.sub(r"\s{2,}", " ", line).strip()
        if not line:
            continue

        collapsed_lines.append(line)
        previous_line = line

    return "\n".join(collapsed_lines).strip()

def html_to_clean_text(html_content):
    # Converts HTML email content to readable text while preserving useful links.
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove non-content elements entirely.
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    # Keep visible anchor text and only preserve useful link targets.
    for anchor in soup.find_all("a"):
        anchor_text = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "")

        if href and is_useful_url(href):
            if anchor_text and anchor_text.lower() not in {href.lower(), "here", "click here"}:
                replacement = f"{anchor_text} ({compact_url(href)})"
            else:
                replacement = compact_url(href)
        else:
            replacement = anchor_text

        anchor.replace_with(replacement)
    
    text = soup.get_text(separator="\n", strip=True)
    return normalize_email_text(text)

def looks_like_html(text):
    """Check if text contains HTML markup, regardless of its declared MIME type"""
    html_indicators = re.search(
        r"</?\s*(?:html|head|body|div|table|tr|td|style|script|meta|a|p|br|span|sup|sub|img|ul|ol|li|strong|em|blockquote)\b",
        text,
        re.IGNORECASE,
    )
    return html_indicators is not None

def get_thread_messages(thread_id):
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    
    turns = []
    for message in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        
        parts = message.get("payload", {}).get("parts", [])
        if parts:
            body, body_type = get_body_from_parts(parts)
        else:
            body = message.get("payload", {}).get("body", {}).get("data")
            body_type = message.get("payload", {}).get("mimeType", "")
            body_type = "plain" if "plain" in body_type else "html"

        if body:
            content = base64.urlsafe_b64decode(body).decode("utf-8")
            
            if body_type == "html" or looks_like_html(content):
                content = html_to_clean_text(content)
            
            match = re.search(r"On.+?wrote:", content, re.DOTALL)
            if match:
                content = content[:match.start()]
            content = strip_signature_and_disclaimers(content)
            content = normalize_email_text(content)
        else:
            content = ""
        
        turns.append({
            "sender": headers.get("From", "Unknown"),
            "date": headers.get("Date", ""),
            "subject": headers.get("Subject", ""),
            "content": content,
            "message_id": message.get("id")
        })
    
    return turns

def chunk_text(text, chunk_size=250, chunk_overlap=30):
    """Split normalized email text into fixed-size overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=lambda value: len(re.findall(r"\S+", value)),
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = splitter.split_text(normalize_email_text(text))
    
    # clean up leading punctuation/whitespace artifacts from overlap
    cleaned_chunks = []
    for chunk in chunks:
        cleaned_chunk = normalize_email_text(chunk).lstrip(". \n")
        if cleaned_chunk:
            cleaned_chunks.append(cleaned_chunk)
    
    return cleaned_chunks

def generate_email_summary(all_turns_text):
    #generates a brief one-sentence summary of what the email is about

    prompt = f"""
    Summarize what this email conversation is about in ONE short sentence (under 15 words).

    Conversation:
    {all_turns_text}

    Summary:
    """

    genai_client = genai.Client()
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    )
    
    return response.text.strip()

def add_context_to_chunk(chunk, thread_summary, sender, date, subject):
    #prepends contextual information to a chunk of text, including the thread summary, sender, date, and subject.
    chunk_text = f"Email from {sender} on {date}. Subject is {subject} and email summary is {thread_summary}. {chunk}"
    return chunk_text

def create_chunk(thread_id):
    """
    Fetches a thread, splits into turns, chunks each turn, and prepends
    contextual headers to each chunk. Returns chunks ready for embedding.
    """
    turns = get_thread_messages(thread_id)
    
    all_text = "\n\n".join([f"{t['sender']}: {t['content']}" for t in turns])
    thread_summary = generate_email_summary(all_text)
    
    all_chunks = []
    seen_chunk_texts = set()
    for turn in turns:
        if not turn["content"].strip():
            continue 
        
        text_chunks = chunk_text(turn["content"])
        
        for chunk in text_chunks:
            if chunk in seen_chunk_texts:
                continue
            seen_chunk_texts.add(chunk)

            text_for_llm = add_context_to_chunk(
                chunk, thread_summary, turn["sender"], turn["date"], turn["subject"]
            )
            
            all_chunks.append({
                "embedding_text": text_for_llm,  # include subject/context so retrieval can match on it
                "metadata": {
                    "thread_id": thread_id,
                    "message_id": turn["message_id"],
                    "subject": turn["subject"],
                    "sender": turn["sender"],
                    "date": turn["date"],
                    "source": "gmail"
                }
            })
    
    return all_chunks

def load_sync_state():
    #Load the most recent Gmail sync checkpoint from disk.
    if not os.path.exists(SYNC_STATE_PATH):
        return {}

    try:
        with open(SYNC_STATE_PATH, "r", encoding="utf-8") as sync_file:
            return json.load(sync_file)
    except (OSError, json.JSONDecodeError):
        return {}

def save_sync_state(state):
    #Save the Gmail sync checkpoint to disk.
    with open(SYNC_STATE_PATH, "w", encoding="utf-8") as sync_file:
        json.dump(state, sync_file, indent=2)

def get_current_history_id():
    #Fetch the current Gmail historyId so only retrieve new emails after that point
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("historyId")

def collect_primary_thread_ids(max_threads=None, page_size=500):
    #Collect unique thread IDs from the primary inbox with pagination.
    thread_ids = []
    seen_thread_ids = set()
    page_token = None

    while True:
        response = service.users().messages().list(
            userId="me",
            q="category:primary",
            maxResults=page_size,
            pageToken=page_token,
        ).execute()

        for message in response.get("messages", []):
            thread_id = message.get("threadId")
            if not thread_id or thread_id in seen_thread_ids:
                continue

            seen_thread_ids.add(thread_id)
            thread_ids.append(thread_id)

            if max_threads is not None and len(thread_ids) >= max_threads:
                return thread_ids

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return thread_ids

def ingest_thread_id(thread_ids):
    #Ingest a list of Gmail thread IDs into the vector store.
    processed_thread_ids = set()
    total_chunks_added = 0

    for thread_id in thread_ids:
        if thread_id in processed_thread_ids:
            continue

        try:
            chunks = create_chunk(thread_id)
            if not chunks:
                continue

            add_chunks(chunks, "gmail")
            total_chunks_added += len(chunks)
            processed_thread_ids.add(thread_id)
            print(f"Processed thread: {thread_id} ({len(chunks)} chunks)")
        except Exception as e:
            print(f"Error processing thread {thread_id}: {e}")
            continue

    print(f"\nDone! Processed {len(processed_thread_ids)} threads, added {total_chunks_added} chunks total.")
    return total_chunks_added

def collect_new_primary_thread_ids(start_history_id):
    #Collect primary inbox thread IDs that changed since the last sync checkpoint.
    thread_ids = []
    seen_thread_ids = set()
    page_token = None
    latest_history_id = start_history_id

    while True:
        response = service.users().history().list(
            userId="me",
            startHistoryId=start_history_id,
            historyTypes=["messageAdded"],
            pageToken=page_token,
        ).execute()

        latest_history_id = response.get("historyId", latest_history_id)

        for history in response.get("history", []):
            for message_added in history.get("messagesAdded", []):
                message = message_added.get("message", {})

                thread_id = message.get("threadId")
                if not thread_id or thread_id in seen_thread_ids:
                    continue

                seen_thread_ids.add(thread_id)
                thread_ids.append(thread_id)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return thread_ids, latest_history_id

def ingest_all_primary_emails(max_threads=None):
    #Ingests the entire primary inbox into the vector store, paging through every thread.
    thread_ids = collect_primary_thread_ids(max_threads=max_threads)
    total_chunks_added = ingest_thread_id(thread_ids)

    current_history_id = get_current_history_id()
    if current_history_id:
        save_sync_state({"history_id": current_history_id})

    return total_chunks_added

def ingest_new_primary_emails():
    #Incrementally ingest new primary inbox mail since the last saved checkpoint.
    state = load_sync_state()
    start_history_id = state.get("history_id")

    if not start_history_id:
        print("No Gmail sync checkpoint found. Running a full primary inbox backfill.")
        return ingest_all_primary_emails()

    try:
        thread_ids, latest_history_id = collect_new_primary_thread_ids(start_history_id)
    except Exception as e:
        print(f"Incremental sync failed ({e}); running a full primary inbox backfill instead.")
        return ingest_all_primary_emails()

    if not thread_ids:
        current_history_id = get_current_history_id()
        if current_history_id:
            save_sync_state({"history_id": current_history_id})
        print("No new primary inbox emails found.")
        return 0

    total_chunks_added = ingest_thread_id(thread_ids)
    checkpoint_history_id = latest_history_id or get_current_history_id()
    if checkpoint_history_id:
        save_sync_state({"history_id": checkpoint_history_id})

    return total_chunks_added
