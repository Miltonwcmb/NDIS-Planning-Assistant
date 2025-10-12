
import os, json, tempfile
from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()  


def build_embeddings(in_path: str,
                     model: str = None,
                     batch_size: int = None):  
    """
    Building embeddings for a JSONL of records with a `text` field.
    Returning (tmp_dir, out_path) where out_path is a JSONL with vectors attached.
    """
    MODEL = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    BATCH = int(batch_size or os.getenv("EMBED_BATCH", "16"))

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    tmp_dir = tempfile.mkdtemp(prefix="embeddings_")
    out_path = os.path.join(tmp_dir, "embedded.jsonl")

    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        batch_texts, batch_recs = [], []

        def flush_batch():
            if not batch_texts:
                return
            resp = client.embeddings.create(model=MODEL, input=batch_texts)
            for rec, item in zip(batch_recs, resp.data):
                rec["embedding"] = item.embedding          
                rec["embedding_dim"] = len(item.embedding)
                if "content" not in rec and "text" in rec:
                    rec["content"] = rec.pop("text")
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            batch_texts.clear()
            batch_recs.clear()

        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            txt = rec.get("text") or rec.get("content")
            if not txt:
                continue
            batch_texts.append(txt)
            batch_recs.append(rec)
            if len(batch_texts) >= BATCH:
                flush_batch()
        flush_batch()

    print(f"Embeddings temp folder → {tmp_dir}")
    print(f"Embedded JSONL → {out_path}")
    return tmp_dir, out_path

if __name__ == "__main__":
    import sys
    in_path = sys.argv[1] if len(sys.argv) > 1 else "out/ndis_parsed.jsonl"
    build_embeddings(in_path)
