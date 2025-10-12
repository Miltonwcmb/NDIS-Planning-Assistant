import os 
from typing import List, Dict, Any 

from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from dotenv import load_dotenv
load_dotenv()


ENDPOINT = os.getenv('AZURE_SEARCH_SERVICE_ENDPOINT')
INDEX_NAME = os.getenv('AZURE_SEARCH_INDEX')
ADMIN_KEY = os.getenv('AZURE_SEARCH_ADMIN_KEY')

EMBED_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

search_client = SearchClient(
    endpoint=ENDPOINT,
    index_name=INDEX_NAME,
    credential=AzureKeyCredential(ADMIN_KEY)
)

def search_with_query(query_text: str, k: int = 5) -> List[Dict[str, Any]]:
    """Embeds the query text using OpenAI, sends the vector to Azure, and returns top-k matches."""
    if not query_text or not query_text.strip():
        return []

    # Embed query text using OpenAI
    resp = client.embeddings.create(model=EMBED_MODEL, input=query_text)
    query_vector = resp.data[0].embedding  # list of 1536 floats

    # Build vector search request
    vq = VectorizedQuery(
        vector=query_vector,
        fields="embedding", # compare the query with the saved documents vector
        k_nearest_neighbors=k,
    )

    # Send the vector search request to Azure Search
    # This compares the query embedding with all stored embeddings in the index
    # and returns the top-K most semantically similar chunks (with their metadata)
    results = search_client.search(
        search_text=None,           # vector-only (Free tier)
        vector_queries=[vq],
        select=["content", "source", "id"],
    )
    
    matches = []
    print("\nTop results:\n------------------------------")

    for rank, r in enumerate(results, 1):
        content = (r.get("content") or "").strip().replace("\n", " ")[:300]
        print(f"#{rank} |  Score: {r['@search.score']:.4f}")
        print(f"   ID: {r['id']}")
        print(f"   Source: {r.get('source', 'N/A')}")
        print(f"   Snippet: {content}\n")
        matches.append(r)

    if not matches:
        print(" No relevant results found.")

    return matches

    # Format and return results
    return [{
        "content": r.get("content", ""),
        "source":  r.get("source"),
        "id":      r.get("id"),
        "score":   r.get("@search.score"),
    } for r in results][:k]


if __name__ == "__main__":
    import sys
    query_embedded_path = sys.argv[1] if len(sys.argv) > 1 else "What is NDIS"
    search_with_query(query_embedded_path)

