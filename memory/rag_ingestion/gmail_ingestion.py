from numpy.ma import count
from tools.gmail_tools import search_emails, get_email_content
import re
from email import message_from_string
from langchain_text_splitters import SemanticChunker
# Replace with your actual embeddings provider (e.g., OpenAIEmbeddings, HuggingFaceEmbeddings)
from langchain_core.embeddings import FakeEmbeddings 



'''
def process_email_pipeline(raw_email_string, email_meta_source):
    """
    Parses, cleans, summarizes, and chunks a raw email string into 
    highly contextualized, RAG-ready vector database payloads.
    """
    msg = message_from_string(raw_email_string)
    
    # 1. PRE-FILTERING: Drop marketing/advertisements immediately
    if "List-Unsubscribe" in msg:
        print(f"Skipping email ID {email_meta_source['id']}: Detected as advertisement/newsletter.")
        return []

    # 2. HEADER ISOLATION: Build clean metadata dictionary
    metadata = {
        "id": email_meta_source["id"],
        "thread_id": email_meta_source["thread_id"],
        "source": "gmail",
        "date": msg.get("Date", email_meta_source.get("date")),
        "sender": msg.get("From", email_meta_source.get("sender")),
        "subject": msg.get("Subject", email_meta_source.get("subject"))
    }

    # 3. EXTRACTION: Pull plain text body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")

    # 4. PARSING & CLEANING: Split threads and remove signatures/disclaimers
    # Regex split on common reply anchors
    thread_delimiters = r"(From:|^On.*wrote:|^---.*Original Message---)"
    raw_turns = re.split(thread_delimiters, body, flags=re.MULTILINE)
    
    cleaned_body_text = ""
    for turn in raw_turns:
        if not turn.strip():
            continue
        # Truncate text before signatures or legal boilerplate footers
        clean_turn = re.split(r"(^Best regards|^Thanks|^Sincerely|--\s*\n|This electronic message contains information)", turn, flags=re.IGNORECASE | re.MULTILINE)[0]
        cleaned_body_text += clean_turn + "\n"

    if not cleaned_body_text.strip():
        return []

    # 5. CONTEXTUAL RETRIEVAL: Mock an LLM call to get a high-level summary of the overall thread
    # Replace this mock string with an actual LLM invocation (e.g., openai.chat.completions)
    thread_summary = f"Discussion regarding {metadata['subject']} between {metadata['sender']}"

    # 6. SEMANTIC CHUNKING: Split the cleaned body based on thematic shifts
    # Using FakeEmbeddings for syntax; swap with OpenAIEmbeddings(model="text-embedding-3-small") in production
    embeddings = FakeEmbeddings(size=1536) 
    text_splitter = SemanticChunker(embeddings, breakpoint_threshold_type="percentile")
    
    # Generate chunks (ideally targets 150-250 tokens per semantic concept)
    semantic_slices = text_splitter.split_text(cleaned_body_text)

    # 7. CONTEXT INJECTION: Combine summary, metadata, and chunk slices
    final_rag_chunks = []
    for slice_text in semantic_slices:
        chunk_text = (
            f"Email Thread Summary: {thread_summary} | "
            f"From: {metadata['sender']} | "
            f"Date: {metadata['date']} | "
            f"Subject: {metadata['subject']} | "
            f"Content: {slice_text.strip()}"
        )
        
        final_rag_chunks.append({
            "text": chunk_text,
            "metadata": metadata
        })

    return final_rag_chunks

# ==========================================
# Example Usage:
# ==========================================
if __name__ == "__main__":
    raw_email_mock = """From: john@company.com
Subject: Q3 Budget Deliverables
Date: Mon, 6 Jul 2026 10:00:00

Hi Team,
We need to finalize the Q3 budget spreadsheet by Friday. Please look over the department costs.

Best regards,
John Doe
-- 
Corporate Signatures Confidentiality Notice..."""

    meta_input = {"id": "msg_12345", "thread_id": "thread_abcde"}
    
    chunks = process_email_pipeline(raw_email_mock, meta_input)
    for index, chunk in enumerate(chunks):
        print(f"\n--- CHUNK {index+1} ---")
        print("TEXT:", chunk["text"])
        print("METADATA:", chunk["metadata"])
'''