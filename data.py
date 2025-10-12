# Imports
import json, re, unicodedata, shutil, zipfile
from pathlib import Path
import gdown, pandas as pd
from docx import Document
from PyPDF2 import PdfReader
import hashlib
from datetime import datetime, timezone



# Parse text from a Word document
def parse_docx(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        print(f"[skip-docx] Not a valid .docx (zip): {path}")
        return ""
    try:
        raw = "\n".join(p.text.strip() for p in Document(path).paragraphs if p.text.strip())
        return clean_text(raw)
    except Exception as e:
        print(f"[error-docx] {path} -> {e}")
        return ""


# Parse text from a PDF
def parse_pdf(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            header = fh.read(5)
        if header != b"%PDF-":
            print(f"[skip-pdf] Not a real PDF (header): {path}")
            return ""
    except Exception as e:
        print(f"[error-pdf-open] {path} -> {e}")
        return ""
    try:
        raw = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        return clean_text(raw)
    except Exception as e:
        print(f"[error-pdf] {path} -> {e}")
        return ""


# Parse text from Excel (all sheets) - supports .xlsx (zip); .xls is skipped
def parse_excel(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        print(f"[skip-xlsx] Not a valid .xlsx (zip): {path}")
        return ""
    try:
        excel = pd.ExcelFile(path)               # requires openpyxl installed
        parts = []
        for sheet in excel.sheet_names:
            df = excel.parse(sheet)
            if not df.empty:
                parts.append(f"[Sheet: {sheet}]\n" + df.to_csv(index=False))
        raw = "\n".join(parts)
        return clean_text(raw)
    except Exception as e:
        print(f"[error-xlsx] {path} -> {e}")
        return ""


# Clean and normalize text
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)   # normalize unicode
    text = text.replace("\xa0", " ")             # replace non-breaking spaces
    text = re.sub(r"page\s+\d+(\s+of\s+\d+)?", "", text, flags=re.I)  # drop page numbers
    text = re.sub(r"[ \t]+", " ", text)          # collapse multiple spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)       # collapse 3+ newlines into 2
    return text.strip()


# Split text into chunks (~1000 chars with 100 overlap)
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        next_start = end - overlap
        start = next_start if next_start > start else end
    return chunks


# Determine if file is a hidden AppleDouble (Mac) or dotfile 
def is_hidden_or_appledouble(p: Path) -> bool:
    name = p.name
    if name.startswith("._"):   # AppleDouble metadata files 
        return True
    if name.startswith("."):    # dotfiles (and .DS_Store etc.)
        return True
    return False


# Create multiple records from one file (1 per chunk)
def make_record(path: Path) -> list[dict] | None:
    if is_hidden_or_appledouble(path):
        return None

    ext = path.suffix.lower()

    # Only support real .docx, .pdf, .xlsx (skip .xls to avoid extra dependency)
    if ext == ".docx":
        text = parse_docx(path)
    elif ext == ".pdf":
        text = parse_pdf(path)
    elif ext == ".xlsx":
        text = parse_excel(path)
    else:
        return None

    if not text:
        return None


    chunks = chunk_text(text)
    records = []
    for i, chunk in enumerate(chunks, 1):
        sha1 = hashlib.sha1(f'{path.resolve()}::{chunk}'.encode('utf-8')).hexdigest()
        records.append({
            "id": f"{path.stem}_{i}",          # unique id = filename + chunk number
            "source_type": ext,
            "file_name": path.name,
            "file_type": ext,
            "path": str(path),
            "text": chunk,
            "sha1": sha1,
            "meta": {
                "size_bytes": path.stat().st_size,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
        })
    return records


# Download and unzip data from Google Drive
def prepare_data(file_link: str, work_dir: str = "data") -> Path:
    work_path = Path(work_dir)
    if work_path.exists():
        shutil.rmtree(work_path)       # clear old data
    work_path.mkdir(parents=True, exist_ok=True)

    zip_path = Path("subs.zip")
    if zip_path.exists():
        zip_path.unlink()              # remove old zip if exists

    print(">>> Downloading ZIP from Google Drive ...")
    gdown.download(url=file_link, output=str(zip_path), fuzzy=True, quiet=False)

    print(f">>> Extracting into {work_path} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(work_path)

    return work_path


# Loop through files, build JSONL corpus
def build_corpus(data_dir: str | Path, out_path: str = "out/ndis_parsed.jsonl") -> None:
    data_dir = Path(data_dir)
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Gather candidate files then filter out hidden/AppleDouble; allow only .docx/.pdf/.xlsx
    candidates = [p for p in data_dir.rglob("*") if p.is_file()]
    files = [
        p for p in candidates
        if not is_hidden_or_appledouble(p)
        and p.suffix.lower() in (".docx", ".pdf", ".xlsx")
    ]

    # quick header sanity to reduce exceptions later
    docx_ok = sum(1 for p in files if p.suffix.lower() == ".docx" and zipfile.is_zipfile(p))
    xlsx_ok = sum(1 for p in files if p.suffix.lower() == ".xlsx" and zipfile.is_zipfile(p))
    pdf_ok  = 0
    for p in files:
        if p.suffix.lower() == ".pdf":
            try:
                with p.open("rb") as fh:
                    pdf_ok += (fh.read(5) == b"%PDF-")
            except Exception:
                pass

    print(f">>> Found {len(files)} supported files under {data_dir} "
          f"(docx_ok={docx_ok}, pdf_ok={pdf_ok}, xlsx_ok={xlsx_ok})")


    # Write JSONL (one line per chunk)
    written = 0
    skipped = 0
    with out_file.open("w", encoding="utf-8") as f:
        for p in files:
            recs = make_record(p)
            if recs:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1
            else:
                skipped += 1

    print(f"Wrote JSONL corpus to {out_file} (records={written}, files_skipped={skipped})")


# Entry point (runs when is python data.py called)
if __name__ == "__main__":
    FILE_LINK = "https://drive.google.com/file/d/1uD7FHNgO0yHQ_maDvt-pAq3sRd4otaXg/view?usp=share_link"
    data_dir = prepare_data(FILE_LINK)                      
    build_corpus(data_dir, "out/ndis_parsed.jsonl")          
