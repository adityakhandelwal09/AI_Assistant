from memory.vector_store import clear_collection
from memory.rag_ingestion.gmail_ingestion import ingest_all_primary_emails
from memory.rag_ingestion.imessage_ingestion import ingest_all_imessages
from memory.rag_ingestion.calendar_ingestion import ingest_calendar_events
from memory.rag_ingestion.drive_ingestion import ingest_drive_files


#deletes only the local ChromaDB test vectors, not your real Gmail, texts, Calendar, or Drive files.
for collection_name in ["gmail", "imessage", "calendar", "drive"]:
    print(f"\nClearing {collection_name} collection...")
    clear_collection(collection_name)


print("\nStarting Gmail backfill...")
gmail_chunks = ingest_all_primary_emails()

print("\nStarting iMessage backfill...")
imessage_chunks = ingest_all_imessages()

print("\nStarting Calendar backfill...")
calendar_chunks = ingest_calendar_events()

print("\nStarting Drive backfill...")
drive_chunks = ingest_drive_files(include_shared=False)


print("\nBackfill complete!")
print(f"Gmail chunks: {gmail_chunks}")
print(f"iMessage chunks: {imessage_chunks}")
print(f"Calendar chunks: {calendar_chunks}")
print(f"Drive chunks: {drive_chunks}")