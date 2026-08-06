"""Ingest coherent iMessage conversation windows into the Chroma vector store.

`get_conversation()` returns messages for one one-to-one conversation, newest
first.  This module restores chronological order, groups messages separated by
short gaps, then chunks and contextualizes those groups before embedding them.
"""

from datetime import datetime, timedelta
import glob
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
import re
import sqlite3
import pytz
from google import genai
from memory.vector_store import add_chunks, embed_text
from tools.imessage_tools import get_conversation, search_messages


DEFAULT_TIME_WINDOW_MINUTES = 360
DEFAULT_TOPIC_SIMILARITY_THRESHOLD = 0.45
MIN_SUBSTANTIVE_WORDS = 4
TOPIC_CONTEXT_MESSAGES = 3
DATE_FORMAT = "%Y-%m-%d %I:%M %p"
IMESSAGE_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
CONTACTS_DB_GLOB = os.path.expanduser(
    "~/Library/Application Support/AddressBook/**/AddressBook-v22.abcddb"
)
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=pytz.utc)
EASTERN_TIMEZONE = pytz.timezone("US/Eastern")


def normalize_message_text(text):
    #normalize plain-text iMessages without applying email/HTML cleanup
    if not text:
        return ""

    text = text.replace("\xa0", " ") #turns non-breaking spaces into normal spaces.
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", text) #removes invisible Unicode characters
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()] #removes extra whitespace, trims each line, removes empty lines, and preserves line breaks
    return "\n".join(line for line in lines if line).strip()


def parse_message_date(date_text):
    #parse the timestamp format returned by get_conversation()
    return datetime.strptime(date_text, DATE_FORMAT)


def is_substantive_message(text, min_words=MIN_SUBSTANTIVE_WORDS):
    # check whether message is long enough for a meaningful topic conversation (filters: ok, sounds good, alright bro, etc.)
    return len(re.findall(r"\S+", text)) >= min_words


def cosine_similarity(first_embedding, second_embedding):
    #for each pair, you MULTIPLY the two numbers together, then SUM all those products.
    dot_product = sum(first * second for first, second in zip(first_embedding, second_embedding))
    #computes the LENGTH of the vector -- square each value, sum, and take square root
    first_magnitude = sum(value * value for value in first_embedding) ** 0.5
    second_magnitude = sum(value * value for value in second_embedding) ** 0.5
    if not first_magnitude or not second_magnitude:
        return 0.0
    return dot_product / (first_magnitude * second_magnitude)


def average_embeddings(embeddings):
    #averages EACH position across all vectors / # of vectors --> result is a single vector that represents the "average meaning" of the last few messages
    return [
        sum(embedding[index] for embedding in embeddings) / len(embeddings)
        for index in range(len(embeddings[0]))
    ]


def get_cached_embedding(text, embedding_cache):
    #embed a message and store in the cache dictionary
    if text not in embedding_cache:
        embedding_cache[text] = embed_text(text)
    return embedding_cache[text]


def group_nearby_messages(
    messages,
    time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES,
    topic_similarity_threshold=DEFAULT_TOPIC_SIMILARITY_THRESHOLD
):
    """=======================================================================
    Group one conversation by long pauses and confirmed semantic topic shifts.

    A long pause is always a new conversation window. Within an active window,
    one dissimilar substantive message is held as a possible topic shift. It
    starts a new group only if a later substantive message is similar to that
    candidate and dissimilar to the active topic. Short acknowledgements stay
    with the pending candidate until that decision can be made.
    =========================================================================="""

    normalized_messages = []
    for message in messages:
        text = normalize_message_text(message.get("text", ""))
        if not text:
            continue

        normalized_messages.append({**message, "text": text})

    chronological_messages = sorted(
        normalized_messages,
        #uses the raw Messages timestamp when present so same-minute texts keep
        #their exact chronological order instead of the database's DESC order.
        key=lambda message: message.get(
            "_sort_key",
            (parse_message_date(message["date"]).timestamp(), 0),
        ),
    ) #returns oldest to newest

    groups = []
    current_group = []
    recent_topic_embeddings = []
    pending_messages = []
    pending_topic_embedding = None
    embedding_cache = {}
    previous_date = None

    for message in chronological_messages:
        message_date = parse_message_date(message["date"]) #saves current message date
        #checks to see if there is a 6 hour gap between the last two messages
        has_long_pause = (
            previous_date is not None
            and (message_date - previous_date).total_seconds() > time_window_minutes * 60
        )

        #if there is a long pause, we need to end the current group and start a new one
        if has_long_pause:
            current_group.extend(pending_messages)
            if current_group:
                groups.append(current_group)
            current_group = []
            recent_topic_embeddings = []
            pending_messages = []
            pending_topic_embedding = None

        #first message of a new group just gets added, establishing the topic
        if not current_group:
            current_group.append(message)
            if is_substantive_message(message["text"]):
                recent_topic_embeddings.append(get_cached_embedding(message["text"], embedding_cache))
            previous_date = message_date
            continue

        if pending_messages:
            pending_messages.append(message)
            if is_substantive_message(message["text"]):
                message_embedding = get_cached_embedding(message["text"], embedding_cache)
                active_topic_centroid = average_embeddings(recent_topic_embeddings)
                #checks to see if current message is dissimilar to the active topic and similar to new pending topic message
                confirms_pending_topic = (
                    cosine_similarity(message_embedding, pending_topic_embedding)
                    >= topic_similarity_threshold
                    and cosine_similarity(message_embedding, active_topic_centroid)
                    < topic_similarity_threshold
                )

                #if the current message confirms the new topic, we need to end the current group and start a new one
                if confirms_pending_topic:
                    groups.append(current_group)
                    current_group = pending_messages
                    recent_topic_embeddings = [pending_topic_embedding, message_embedding]
                    pending_messages = []
                    pending_topic_embedding = None
                #if ends up being a single unrelated message, adds all pending messages except last to current group
                else:
                    current_group.extend(pending_messages[:-1])
                    pending_messages = []
                    pending_topic_embedding = None

                    #checks to see if current message is dissimilar to the active topic
                    if cosine_similarity(message_embedding, active_topic_centroid) < topic_similarity_threshold:
                        pending_messages = [message]
                        pending_topic_embedding = message_embedding
                    else:
                        current_group.append(message)
                        recent_topic_embeddings.append(message_embedding)
                        recent_topic_embeddings = recent_topic_embeddings[-TOPIC_CONTEXT_MESSAGES:]
            previous_date = message_date
            continue

        #if no pending candidates -- similar flow as above
        current_group.append(message)
        if is_substantive_message(message["text"]):
            message_embedding = get_cached_embedding(message["text"], embedding_cache)
            if not recent_topic_embeddings:
                #uses the first substantive message as the initial topic baseline.
                recent_topic_embeddings.append(message_embedding)
            else:
                active_topic_centroid = average_embeddings(recent_topic_embeddings)
                if cosine_similarity(message_embedding, active_topic_centroid) < topic_similarity_threshold:
                    current_group.pop()
                    pending_messages = [message]
                    pending_topic_embedding = message_embedding
                else:
                    recent_topic_embeddings.append(message_embedding)
                    recent_topic_embeddings = recent_topic_embeddings[-TOPIC_CONTEXT_MESSAGES:]
        previous_date = message_date

    if current_group:
        current_group.extend(pending_messages)
        groups.append(current_group)

    return groups


def format_message(message):
    #format one message with speaker and reply context for retrieval
    reply_context = ""
    if message.get("reply_to"):
        reply_context = f' (replying to: "{message["reply_to"]}")'
    return f'{message["sender"]}{reply_context}: {message["text"]}'

def build_message_prefix(message):
    #build the prefix for a message, including reply context if applicable.
    reply_context = ""
    if message.get("reply_to"):
        reply_context = f' (replying to: "{message["reply_to"]}")'
    return f'{message["sender"]}{reply_context}: '


def format_message_group(messages):
    #render a time window as readable speaker-attributed conversation text
    return "\n".join(format_message(message) for message in messages)


def word_count(text):
    return len(re.findall(r"\S+", text))


def chunk_text(messages, chunk_size=250, chunk_overlap=30):
    """==================================================================
    Messages are kept whole unless an individual message exceeds chunk_size.

    If an individual message exceeds chunk_size, split only that message
    using RecursiveCharacterTextSplitter.
    ====================================================================="""

    chunks = []
    current_chunk = []
    current_word_count = 0

    for message in messages:
        formatted_message = format_message(message)
        message_word_count = word_count(formatted_message)

        # Handle oversized messages
        if message_word_count > chunk_size:
            # Flush the current chunk first
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_word_count = 0

            # Split only this oversized message
            formatted_prefix = build_message_prefix(message)  # e.g. "Hrishi: " or "Hrishi (replying to Aditya): "
            message_body = normalize_message_text(message["text"])

            prefix_word_count = word_count(formatted_prefix)
            effective_chunk_size = max(1, chunk_size - prefix_word_count)

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=effective_chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=word_count,
                separators=["\n\n", "\n", ". ", " ", ""],
            )

            for piece in splitter.split_text(message_body):
                chunks.append(formatted_prefix + piece)
            continue
        
        # Start a new chunk if this message would exceed the limit
        if current_chunk and current_word_count + message_word_count > chunk_size:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_word_count = 0
        current_chunk.append(formatted_message)
        current_word_count += message_word_count

    # Add the final chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def generate_conversation_summary(conversation_text):
    #generates a brief one-sentence summary of what the iMessage conversation is about

    prompt = f"""
    Summarize this text-message conversation in one short sentence
    (under 15 words). Preserve concrete names, plans, and requests.

    Conversation:
    {conversation_text}

    Summary:
    """

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    )
    return response.text.strip()


def add_context_to_chunk(chunk, conversation_id, start_date, end_date, summary):
    #prepends contextual information to a chunk of text, including the thread summary, sender, date, and subject.
    chunk_text = f"iMessage conversation with {conversation_id} from {start_date} to {end_date}. Conversation summary: {summary}. \n {chunk} "
    return chunk_text


def create_chunks_from_messages(
    messages,
    conversation_id,
    conversation_label,
    time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES,
):
    #create contextualized chunks from messages belonging to one chat
    #splits one chat into time and topic coherent conversation groups.
    message_groups = group_nearby_messages(messages, time_window_minutes)

    all_chunks = []
    for group_index, group in enumerate(message_groups):
        #creates the clean speaker-attributed transcript shown after retrieval.
        display_text = format_message_group(group)
        #summarizes the full group once so every resulting chunk shares context.
        summary = generate_conversation_summary(display_text)
        start_date = group[0]["date"]
        end_date = group[-1]["date"]

        for chunk_index, display_chunk in enumerate(chunk_text(group)):
            #adds generated context only to the text used for embedding.
            embedding_text = add_context_to_chunk(
                display_chunk,
                conversation_label,
                start_date,
                end_date,
                summary,
            )
            all_chunks.append(
                {
                    "chunk_id": f"imessage_{conversation_id}_{group_index}_{chunk_index}",
                    "embedding_text": embedding_text,
                    "display_text": display_chunk,
                    "metadata": {
                        #uses the stable chat ID and local chunk position for Chroma IDs.
                        "thread_id": conversation_id,
                        "message_id": f"{group_index}_{chunk_index}",
                        "sender": "Me and Them",
                        "date": end_date,
                        "source": "imessage",
                        "conversation_id": conversation_id,
                        "conversation_label": conversation_label,
                        "start_date": start_date,
                        "end_date": end_date,
                        "summary": summary,
                    },
                }
            )

    return all_chunks


def create_chunks(phone_number, limit=500, time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES, contact_names=None):
    #create chunks for one existing one-to-one conversation helper
    #keeps the original phone-number-based API working alongside full ingestion.
    contact_names = load_contact_names() if contact_names is None else contact_names
    conversation_label = format_sender_handle(phone_number, contact_names)
    messages = get_conversation(phone_number, limit=limit)
    #replaces the generic one-to-one helper label with the resolved contact name.
    for message in messages:
        if message["sender"] == "Them":
            message["sender"] = conversation_label
    return create_chunks_from_messages(
        messages,
        conversation_id=phone_number,
        conversation_label=conversation_label,
        time_window_minutes=time_window_minutes,
    )


def open_imessage_database():
    #open macOS Messages' database read-only so ingestion cannot modify it
    return sqlite3.connect(f"file:{IMESSAGE_DB_PATH}?mode=ro", uri=True)


def contact_lookup_keys(handle):
    #creates comparable keys for phone number and email formatting variations
    if not handle:
        return []

    handle = handle.strip()
    if "@" in handle:
        return [f"email:{handle.lower()}"]

    digits = re.sub(r"\D", "", handle)
    if not digits:
        return []

    keys = [f"phone:{digits}"]
    if len(digits) >= 10:
        #adds a last-ten-digits key so +1 and non-country-code formats still match.
        keys.append(f"phone:{digits[-10:]}")
    return keys


def contact_display_name(full_name, first_name, last_name, organization):
    #prefers a complete name and falls back to first-last or organization names
    return full_name or " ".join(part for part in (first_name, last_name) if part) or organization


def load_contact_names():
    #one dictionary that maps normalized phone numbers/emails to contact names
    contact_names = {}
    contact_databases = sorted(set(glob.glob(CONTACTS_DB_GLOB, recursive=True)))

    for database_path in contact_databases:
        try:
            #opens each Contacts database read-only because it is system-owned data
            with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
                #reads saved phone numbers with their owning contact names
                phone_rows = connection.execute(
                    """
                    SELECT p.ZFULLNUMBER, r.ZNAME, r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION
                    FROM ZABCDPHONENUMBER AS p
                    JOIN ZABCDRECORD AS r ON r.Z_PK = p.ZOWNER
                    """
                ).fetchall()
                #reads saved email addresses with their owning contact names
                email_rows = connection.execute(
                    """
                    SELECT e.ZADDRESS, r.ZNAME, r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION
                    FROM ZABCDEMAILADDRESS AS e
                    JOIN ZABCDRECORD AS r ON r.Z_PK = e.ZOWNER
                    """
                ).fetchall()
        except sqlite3.DatabaseError:
            #skips a Contacts source that cannot be read without stopping ingestion
            continue

        for handle, full_name, first_name, last_name, organization in phone_rows + email_rows:
            name = contact_display_name(full_name, first_name, last_name, organization)
            if not name:
                continue
            for key in contact_lookup_keys(handle):
                #keeps the first match when several Contacts sources contain the same handle
                contact_names.setdefault(key, name)

    return contact_names


def format_sender_handle(handle, contact_names):
    #combines a resolved name with the stable phone or email handle
    for key in contact_lookup_keys(handle):
        name = contact_names.get(key)
        if name:
            return f"{name} ({handle})"
    return handle or "Unknown sender"


def list_imessage_chats(contact_names=None):
    #return every chat with a stable ID, display label, and participants
    contact_names = contact_names or {}
    with open_imessage_database() as connection:
        #joins chats to handles so both one-to-one and group-chat participants are available
        rows = connection.execute(
            """
            SELECT
                c.ROWID AS chat_id,
                c.guid AS chat_guid,
                c.chat_identifier,
                c.display_name,
                h.id AS participant
            FROM chat AS c
            LEFT JOIN chat_handle_join AS chj ON chj.chat_id = c.ROWID
            LEFT JOIN handle AS h ON h.ROWID = chj.handle_id
            WHERE EXISTS (
                SELECT 1
                FROM chat_message_join AS cmj
                JOIN message AS m ON m.ROWID = cmj.message_id
                WHERE cmj.chat_id = c.ROWID
                  AND m.text IS NOT NULL
                  AND TRIM(m.text) <> ''
            )
            ORDER BY c.ROWID, h.id
            """
        ).fetchall()

    #combines the one-row-per-participant query result into one dictionary per chat
    chats_by_id = {}
    for chat_id, chat_guid, chat_identifier, display_name, participant in rows:
        chat = chats_by_id.setdefault(
            chat_id,
            {
                "chat_id": chat_id,
                "conversation_id": chat_guid,
                "chat_identifier": chat_identifier,
                "display_name": display_name,
                "participants": [],
            },
        )
        if participant:
            #adds each participant handle to its parent chat
            chat["participants"].append(participant)

    chats = []
    for chat in chats_by_id.values():
        #resolves participant handles so unnamed chats still have readable labels
        participant_labels = [
            format_sender_handle(participant, contact_names)
            for participant in chat["participants"]
        ]
        #prefers a group title, then resolved participant labels, for a readable context header
        chat["conversation_label"] = (
            chat["display_name"]
            or ", ".join(participant_labels)
            or chat["chat_identifier"]
            or f"Chat {chat['chat_id']}"
        )
        chats.append(chat)
    return chats


def format_imessage_date(apple_timestamp):
    #convert Messages' nanosecond timestamp to the existing display format
    message_date = APPLE_EPOCH + timedelta(seconds=apple_timestamp / 1e9)
    return message_date.astimezone(EASTERN_TIMEZONE).strftime(DATE_FORMAT)


def get_chat_messages(chat_id, limit=None, contact_names=None):
    #fetch text messages for one chat, newest first, including group chats
    contact_names = contact_names or {}
    #joins each incoming message to its handle so group-chat speakers stay distinct
    query = """
        SELECT m.text, m.date, m.ROWID, m.is_from_me, m.thread_originator_guid, m.guid, h.id
        FROM message AS m
        JOIN chat_message_join AS cmj ON cmj.message_id = m.ROWID
        LEFT JOIN handle AS h ON h.ROWID = m.handle_id
        WHERE cmj.chat_id = ?
          AND m.text IS NOT NULL
          AND TRIM(m.text) <> ''
        ORDER BY m.date DESC, m.ROWID DESC
    """
    parameters = [chat_id]
    if limit is not None:
        #adds a limit only for test runs or intentionally partial ingestion
        query += " LIMIT ?"
        parameters.append(limit)

    with open_imessage_database() as connection:
        rows = connection.execute(query, parameters).fetchall()

    #builds a lookup so reply GUIDs can be rendered as readable reply snippets
    guid_to_text = {guid: text for text, _, _, _, _, guid, _ in rows if guid and text}
    messages = []
    for text, apple_timestamp, message_row_id, is_from_me, reply_guid, _, sender_handle in rows:
        #normalizes each database row into the message shape used by chunking
        message = {
            "text": text,
            "date": format_imessage_date(apple_timestamp),
            "sender": "Me" if is_from_me else format_sender_handle(sender_handle, contact_names),
            #keeps a precise, internal-only ordering key for same-minute messages.
            "_sort_key": (apple_timestamp, message_row_id),
        }
        if reply_guid and reply_guid in guid_to_text:
            #keeps reply context short so it does not dominate the embedded message
            message["reply_to"] = f"{guid_to_text[reply_guid][:50]}..."
        messages.append(message)
    return messages


def ingest_conversations(phone_numbers, limit_per_conversation=500, time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES):
    #create and add chunks for each supplied one-to-one iMessage conversation
    total_chunks_added = 0
    next_progress_report = 40
    #loads Contacts once so every requested conversation reuses the same mapping.
    contact_names = load_contact_names()
    for phone_number in dict.fromkeys(phone_numbers):
        try:
            chunks = create_chunks(
                phone_number,
                limit=limit_per_conversation,
                time_window_minutes=time_window_minutes,
                contact_names=contact_names,
            )
            if not chunks:
                continue

            add_chunks(chunks, "imessage")
            total_chunks_added += len(chunks)
            if total_chunks_added >= next_progress_report:
                print(f"iMessage progress: {total_chunks_added} chunks ingested.")
                next_progress_report = total_chunks_added + 40
        except Exception as error:
            print(f"Error processing iMessage conversation {phone_number}: {error}")

    print(f"\nDone! Added {total_chunks_added} iMessage chunks.")
    return total_chunks_added


def ingest_all_imessages(max_chats=None, max_messages_per_chat=None, time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES,):
    """Backfill every text-bearing iMessage/SMS chat into the vector store.

    Set either limit while testing; leave both as ``None`` for a full archive
    ingestion. Group chats are included.
    """
    #loads Contacts once so every chat and message reuses the same name mapping.
    contact_names = load_contact_names()
    #enumerates every chat before optionally limiting the run for testing.
    chats = list_imessage_chats(contact_names)
    if max_chats is not None:
        chats = chats[:max_chats]

    total_chunks_added = 0
    processed_chats = 0
    next_progress_report = 40
    for chat in chats:
        try:
            #retrieves the complete text history for this one chat by default.
            messages = get_chat_messages(
                chat["chat_id"],
                limit=max_messages_per_chat,
                contact_names=contact_names,
            )
            if not messages:
                continue

            #runs the same grouping and chunking path used for individual chats.
            chunks = create_chunks_from_messages(
                messages,
                conversation_id=chat["conversation_id"],
                conversation_label=chat["conversation_label"],
                time_window_minutes=time_window_minutes,
            )
            if not chunks:
                continue

            #embeds contextual text and stores clean display text in Chroma.
            add_chunks(chunks, "imessage")
            processed_chats += 1
            total_chunks_added += len(chunks)
            if total_chunks_added >= next_progress_report:
                print(f"iMessage progress: {total_chunks_added} chunks ingested.")
                next_progress_report = total_chunks_added + 40
        except Exception as error:
            #continues with the remaining chats if one chat cannot be read or embedded.
            print(f"Error processing {chat['conversation_label']}: {error}")

    print(f"\nDone! Processed {processed_chats} chats and added {total_chunks_added} iMessage chunks.")
    return total_chunks_added


def find_messages(query, limit=10):
    """Expose the existing keyword search helper for iMessage discovery.

    Its results do not include a conversation ID, so they are intentionally not
    mixed into ingestion chunks; use ``ingest_conversations`` with known phone
    numbers to preserve conversation boundaries.
    """
    return search_messages(query, limit=limit)
