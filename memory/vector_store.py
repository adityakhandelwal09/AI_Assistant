import chromadb
import os
import re
from google import genai
from sentence_transformers import CrossEncoder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
genai_client = genai.Client()

collections = {
    "gmail": chroma_client.get_or_create_collection(name="gmail"),
    "imessage": chroma_client.get_or_create_collection(name="imessage"),
    "drive": chroma_client.get_or_create_collection(name="drive"),
    "calendar": chroma_client.get_or_create_collection(name="calendar"),
}

def multi_query_search(original_query, collection_name, n_results_per_query=10):
    # Step 1: Generate 5 rephrased versions of the query using Gemini
    rephrased_queries = generate_query_variations(original_query)
    print("Rephrased queries:", rephrased_queries)
    print()
    
    # Step 2: Run search() for EACH variation
    all_results = []
    for query in rephrased_queries:
        results = search(query, collection_name, n_results_per_query)
        all_results.extend(results)

    # Step 3: Deduplicate (same chunk might match multiple query variations)
    unique_results = remove_duplicates(all_results)

    return unique_results

def remove_duplicates(results):
    seen_chunk_id = set()
    unique_results = []

    for result in results:
        if result["chunk_id"] not in seen_chunk_id:
            seen_chunk_id.add(result["chunk_id"])
            unique_results.append(result)
    return unique_results

def generate_query_variations(original_query):
    #ses Gemini to generate multiple rephrasings of a query to improve retrieval coverage across different phrasings.

    prompt = f"""
    Generate 4 different ways to phrase this search query. 
    Each should capture the EXACT same underlying question and intent — do not add assumptions or change what is being asked. 
    If the original question is uncertain or asks for a recommendation, keep that same uncertainty.
    Only vary the wording, not the meaning.
    Return ONLY the 4 queries, one per line, no numbering or extra text.

    Original query: {original_query}"""

    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    )
    
    variations = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    variations.append(original_query)  # always include the original too
    
    return variations

def embed_text(text):
    #convert text into a vector embedding using Google's embedding model
    result = genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )
    return result.embeddings[0].values

def add_chunks(chunks, collection_name):
    #adds a list of chunks to the specified collection in the vector store
    collection = collections[collection_name]
    
    for i, chunk in enumerate(chunks):
        embedding = embed_text(chunk["embedding_text"])
        metadata = chunk["metadata"]
        chunk_id = chunk.get("chunk_id") #each ingestion pipeline creates its own meaningful chunk_id
        
        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[chunk.get("display_text", chunk["embedding_text"])],
            metadatas=[metadata]
        )


def search(query, collection_name="messages", n_results=10):
    #searches the vector store for chunks similar to the query
    collection = collections[collection_name]
    
    query_embedding = embed_text(query)
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    matches = []
    for i in range(len(results["documents"][0])):
        matches.append({
            "chunk_id": results.get("ids", [[None]])[0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i]
        })
    
    return matches

def clear_collection(collection_name):
    #delete all data in a collection
    global collections
    chroma_client.delete_collection(collection_name)
    collections[collection_name] = chroma_client.get_or_create_collection(name=collection_name)
