"""Ingest coherent iMessage conversation windows into the Chroma vector store.

`get_conversation()` returns messages for one one-to-one conversation, newest
first.  This module restores chronological order, groups messages separated by
short gaps, then chunks and contextualizes those groups before embedding them.
"""

from datetime import datetime
from langchain_text_splitters import RecursiveCharacterTextSplitter
import re

from google import genai
from memory.vector_store import add_chunks, embed_text
from tools.imessage_tools import get_conversation, search_messages


DEFAULT_TIME_WINDOW_MINUTES = 360
DEFAULT_TOPIC_SIMILARITY_THRESHOLD = 0.45
MIN_SUBSTANTIVE_WORDS = 4
TOPIC_CONTEXT_MESSAGES = 3
DATE_FORMAT = "%Y-%m-%d %I:%M %p"


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
        key=lambda message: parse_message_date(message["date"]),
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
    chunk_text = f"iMessage conversation with {conversation_id} from {start_date} to {end_date}. Conversation summary: {summary}. {chunk} "
    return chunk_text


def create_chunks(phone_number, limit=500, time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES):
    #Create contextualized embedding chunks for one iMessage conversation.

    messages = get_conversation(phone_number, limit=limit)
    message_groups = group_nearby_messages(messages, time_window_minutes)

    all_chunks = []
    for group_index, group in enumerate(message_groups):
        display_text = format_message_group(group)
        summary = generate_conversation_summary(display_text)
        start_date = group[0]["date"]
        end_date = group[-1]["date"]

        for chunk_index, display_chunk in enumerate(chunk_text(group)):
            embedding_text = add_context_to_chunk(
                display_chunk,
                phone_number,
                start_date,
                end_date,
                summary,
            )
            all_chunks.append(
                {
                    "embedding_text": embedding_text,
                    "display_text": display_chunk,
                    "metadata": {
                        "thread_id": phone_number,
                        "message_id": f"{group_index}_{chunk_index}",
                        "sender": "Me and Them",
                        "date": end_date,
                        "source": "imessage",
                        "conversation_id": phone_number,
                        "start_date": start_date,
                        "end_date": end_date,
                        "summary": summary,
                    },
                }
            )

    return all_chunks


def ingest_conversations(phone_numbers, limit_per_conversation=500, time_window_minutes=DEFAULT_TIME_WINDOW_MINUTES):
    #create and add chunks for each supplied one-to-one iMessage conversation.
    total_chunks_added = 0
    for phone_number in dict.fromkeys(phone_numbers):
        try:
            chunks = create_chunks(
                phone_number,
                limit=limit_per_conversation,
                time_window_minutes=time_window_minutes,
            )
            if not chunks:
                continue

            add_chunks(chunks, "imessage")
            total_chunks_added += len(chunks)
            print(f"Processed iMessage conversation {phone_number} ({len(chunks)} chunks)")
        except Exception as error:
            print(f"Error processing iMessage conversation {phone_number}: {error}")

    print(f"\nDone! Added {total_chunks_added} iMessage chunks.")
    return total_chunks_added


def find_messages(query, limit=10):
    """Expose the existing keyword search helper for iMessage discovery.

    Its results do not include a conversation ID, so they are intentionally not
    mixed into ingestion chunks; use ``ingest_conversations`` with known phone
    numbers to preserve conversation boundaries.
    """
    return search_messages(query, limit=limit)
