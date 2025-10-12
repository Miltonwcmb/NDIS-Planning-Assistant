import os, json, re
from pathlib import Path
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchField, SearchFieldDataType,
    VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile
)
from azure.search.documents import SearchClient

# Load env 
load_dotenv()

IN_PATH   = os.getenv("PARSED_JSONL_PATH", "out/ndis_parsed.jsonl")
WEB_PATH  = os.getenv("WEB_PARSED_JSONL_PATH", "out/web_parsed.jsonl")
EMB_PATH  = os.getenv("EMBEDDED_JSONL_PATH", "out/ndis_parsed_embedded.jsonl")

ENDPOINT  = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
ADMIN_KEY = os.environ["AZURE_SEARCH_ADMIN_KEY"]
INDEX     = os.getenv("AZURE_SEARCH_INDEX", "at2-index")

# Helpers 
def sanitize_id(raw: str) -> str:
    """Azure doc keys: only letters, digits, _, -, = . Replace others with _ ."""
    if not raw:
        return "missing_id"
    safe = re.sub(r"[^A-Za-z0-9_\-=]", "_", raw)
    return safe[:512]

def combine_jsonl(out_path: str, paths: list[str]) -> str:
    """Combine JSONL inputs; de-dup by sha1/id."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    seen, wrote = set(), 0
    with open(out_path, "w", encoding="utf-8") as out:
        for p in paths:
            if not p or not Path(p).exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    key = rec.get("sha1") or rec.get("id")
                    if key in seen:
                        continue
                    seen.add(key)
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    wrote += 1
    print(f"[combine] wrote {wrote} → {out_path}")
    return out_path

def load_embedded(jsonl_path: str):
    """Map embedded JSONL to minimal index schema."""
    docs = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            emb = rec.get("embedding") or rec.get("vector") or rec.get("content_vector")
            if not emb:
                continue
            raw_id = str(rec.get("id", ""))
            docs.append({
                "id": sanitize_id(raw_id),
                "content": (rec.get("content") or rec.get("text") or rec.get("page_content") or "")[:32766],
                "source": str(rec.get("source") or rec.get("file_name") or "local"),
                "embedding": emb
            })
    print(f"[load] {len(docs)} embedded docs ready")
    return docs

def upload_all(search_client: SearchClient, docs, batch_size: int = 500):
    """Upload to Azure in batches."""
    total = len(docs)
    for i in range(0, total, batch_size):
        search_client.upload_documents(docs[i:i+batch_size])
    print(f"[upload] uploaded {total} docs")

def reset_index():
    """DELETE existing index (frees storage), ignore if missing."""
    ic = SearchIndexClient(endpoint=ENDPOINT, credential=AzureKeyCredential(ADMIN_KEY))
    try:
        ic.delete_index(INDEX)
        print(f"[index] deleted: {INDEX}")
    except ResourceNotFoundError:
        pass

def ensure_index():
    """Create minimal vector index (1536 dims for text-embedding-3-*)."""
    ic = SearchIndexClient(endpoint=ENDPOINT, credential=AzureKeyCredential(ADMIN_KEY))

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=1536,
            vector_search_profile_name="hnsw-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
    )

    index = SearchIndex(name=INDEX, fields=fields, vector_search=vector_search)
    ic.create_or_update_index(index)
    print(f"[index] ready: {INDEX}")

#  Main 
def build_index():
    # Choose input: combine if web exists
    input_file = IN_PATH
    if Path(WEB_PATH).exists():
        input_file = combine_jsonl("out/combined.jsonl", [IN_PATH, WEB_PATH])

    # Build embeddings ONCE (fresh each run keeps things in sync)
    from embeddings import build_embeddings
    _, embedded_path = build_embeddings(input_file)
    print(f"[embed] {embedded_path}")

    # Reset + recreate index (fixes storage quota issues)
    reset_index()
    ensure_index()

    # Upload
    docs = load_embedded(embedded_path)
    sc = SearchClient(endpoint=ENDPOINT, index_name=INDEX, credential=AzureKeyCredential(ADMIN_KEY))
    upload_all(sc, docs)

    # Count
    try:
        print(f"[count] {sc.get_document_count()} docs in index")
    except Exception:
        pass

if __name__ == "__main__":
    build_index()
