import base64
import re
import unicodedata
from bs4 import BeautifulSoup
from google import genai
from tools.gmail_tools import search_emails, get_email_content, get_google_service, get_body_from_parts
from memory.vector_store import add_chunks
from langchain_text_splitters import RecursiveCharacterTextSplitter

service = get_google_service("gmail", "v1")

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
            text = text[:match.start()]  #cut off everything from the marker onward
    
    return text.strip()

def normalize_email_text(email_text):
    text = unicodedata.normalize("NFKC", email_text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\u034f\u200b-\u200f\u2060\ufeff]", "", text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()

def html_to_clean_text(html_content):
    #converts HTML email content to clean, readable plain text
    soup = BeautifulSoup(html_content, "html.parser")
    
    #remove script and style elements entirely - they're never useful content
    for element in soup(["script", "style"]):
        element.decompose()
    
    text = soup.get_text(separator=" ", strip=True)
    url_pattern = r'https?://\S+'
    text = re.sub(url_pattern, '', text)
    
    return text

def looks_like_html(text):
    """Check if text contains HTML markup, regardless of its declared MIME type"""
    html_indicators = re.search(r"<(!DOCTYPE|html|head|body|div|table|tr|td|style|script|meta)\b", text, re.IGNORECASE)
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

def chunk_text(text, chunk_size=250, chunk_overlap=40):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = splitter.split_text(text)
    
    # clean up leading punctuation/whitespace artifacts from overlap
    cleaned_chunks = [chunk.lstrip(". \n") for chunk in chunks]
    
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
    
    all_text = "\n\n".join([f"{t["sender"]}: {t["content"]}" for t in turns])
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
            print(chunk)
            print()
            
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

def ingest_all_emails(max_emails=50):
    """================================================================
    Full Gmail ingestion pipeline: searches recent emails, filters out
    promotional content, splits into threads, chunks with context,
    and embeds everything into the vector store.
    ================================================================="""
    
    emails = search_emails(query="category:primary", max_results=max_emails)
    
    processed_thread_ids = set()  #avoid processing the same thread multiple times
    total_chunks_added = 0
    
    for email in emails:
        thread_id = email["thread_id"]
        
        if thread_id in processed_thread_ids:
            continue  # already processed this thread
        
        try:
            chunk = create_chunk(thread_id)
            add_chunks(chunk, "gmail")
            total_chunks_added += len(chunk)
            processed_thread_ids.add(thread_id)
            print(f"Processed thread: {email['subject']} ({len(chunk)} chunks)")
        except Exception as e:
            print(f"Error processing thread {thread_id}: {e}")
            continue
    
    print(f"\nDone! Processed {len(processed_thread_ids)} threads, added {total_chunks_added} chunks total.")