import base64
import re
from google import genai
from tools.gmail_tools import search_emails, get_email_content, get_google_service, get_body_from_parts
from memory.vector_store import add_chunks
from langchain_text_splitters import RecursiveCharacterTextSplitter

service = get_google_service("gmail", "v1")

def get_full_headers(message_id):
    #fetch all headers for a message, not just the basic ones
    msg = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
    headers = msg.get("payload", {}).get("headers", [])
    return {h["name"]: h["value"] for h in headers}


def is_promotional(headers):
    #figure out if an email is a newsletter, promotion, or marketing email based on header signals

    # Signal 1: List-Unsubscribe header - the strongest signal
    if "List-Unsubscribe" in headers or "List-Unsubscribe-Post" in headers:
        return True
    
    # Signal 2: Common bulk-mail headers
    if headers.get("Precedence", "").lower() in ["bulk", "junk", "list"]:
        return True
    
    # Signal 3: Common no-reply patterns in sender
    sender = headers.get("From", "").lower()
    no_reply_patterns = ["noreply", "no-reply", "donotreply", "newsletter", "marketing", "notifications@"]
    if any(pattern in sender for pattern in no_reply_patterns):
        return True
    
    return False

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
    ]
    
    text = email_text
    for marker in signature_markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]  # cut off everything from the marker onward
    
    return text.strip()

def get_thread_messages(thread_id):
    #gets all individual messages in a thread as separate turns, each with their own sender, date, and content.
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    
    turns = []
    for message in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
        
        # extract body content (reuse your existing body extraction logic)
        parts = message.get("payload", {}).get("parts", [])
        body = get_body_from_parts(parts) if parts else message.get("payload", {}).get("body", {}).get("data")


        if body:
            content = base64.urlsafe_b64decode(body).decode("utf-8")
            match = re.search(r"On.+?wrote:", content, re.DOTALL)
            if match:
                content = content[:match.start()]
            content = strip_signature_and_disclaimers(content)
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

def chunk_text(text, chunk_size=250, chunk_overlap=40):
    #Splits text into chunks using recursive character splitting. Paragraphs, sentences, and then words are used as separators.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_text(text)

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
    
    all_text = "\n\n".join([f"{t["sender"]}: {t["content"]}" for t in turns])
    thread_summary = generate_email_summary(all_text)
    
    all_chunks = []
    for turn in turns:
        if not turn["content"].strip():
            continue  # skip empty turns
        
        text_chunks = chunk_text(turn["content"])
        
        for chunk in text_chunks:
            text_for_llm = add_context_to_chunk(
                chunk, thread_summary, turn["sender"], turn["date"], turn["subject"]
            )
            
            all_chunks.append({
                "embedding_text": chunk,  # store the clean version for embedding
                "display_text": text_for_llm,
                "metadata": {
                    "thread_id": thread_id,
                    "message_id": turn["message_id"],
                    "sender": turn["sender"],
                    "date": turn["date"],
                    "source": "gmail"
                }
            })
    
    return all_chunks

def ingest_all_emails(max_emails=50):
    """================================================================
    Full Gmail ingestion pipeline: searches recent emails, filters out
    promotional content, splits into threads, chunks with context,
    and embeds everything into the vector store.
    ================================================================="""
        
    emails = search_emails(query="", max_results=max_emails)
    
    processed_thread_ids = set()  #avoid processing the same thread multiple times
    total_chunks_added = 0
    
    for email in emails:
        thread_id = email["thread_id"]
        
        if thread_id in processed_thread_ids:
            continue  # already processed this thread
        
        headers = get_full_headers(email["id"])
        if is_promotional(headers):
            print(f"Skipping promotional email: {email['subject']}")
            continue
        
        try:
            chunk = create_chunk(thread_id)
            add_chunks([chunk], "gmail")
            total_chunks_added += 1
            processed_thread_ids.add(thread_id)
            print(f"Processed thread: {email['subject']} ({len(chunk)} chunks)")
        except Exception as e:
            print(f"Error processing thread {thread_id}: {e}")
            continue
    
    print(f"\nDone! Processed {len(processed_thread_ids)} threads, added {total_chunks_added} chunks total.")