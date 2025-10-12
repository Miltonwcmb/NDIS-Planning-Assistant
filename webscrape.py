# webscrape_ndis.py
import os, json, time, hashlib, re
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlparse
import requests
from dotenv import load_dotenv

load_dotenv()

# Config 
START_URL            = os.getenv("SCRAPE_URL", "https://www.ndis.gov.au")
OUT_PATH             = os.getenv("WEB_PARSED_JSONL_PATH", "out/web_parsed.jsonl")
CRAWLER_MAX_PAGES    = int(os.getenv("CRAWLER_MAX_PAGES", "5"))   # pages, not chunks
CRAWLER_DELAY_SEC    = float(os.getenv("CRAWLER_DELAY_SEC", "0.3"))

# Hard caps to stay within Azure Free quotas
MAX_BYTES            = int(os.getenv("MAX_BYTES", "2000000"))      # ~2 MB per page
MAX_TEXT_CHARS       = int(os.getenv("MAX_TEXT_CHARS", "20000"))   # trim very long pages

# Skip downloading these file types (These files have been donwloaded/chunked in data.py)
SKIP_EXT = {
    ".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".zip",
    ".jpg",".jpeg",".png",".gif",".svg",".webp",".mp4",".webm",
    ".json",".xml",".rss",".ics",".apk",".csv",".txt"
}

def is_html_url(link: str, start_url: str) -> bool:
    """Same-host, non-binary, no fragments."""
    try:
        u = urlparse(link)
        s = urlparse(start_url)
        # same host (or relative)
        if u.netloc and u.netloc != s.netloc:
            return False
        # skip known non-html extensions
        path = (u.path or "").lower()
        if any(path.endswith(ext) for ext in SKIP_EXT):
            return False
        # avoid in-page anchors
        if u.fragment:
            return False
        return True
    except:
        return False

# Cleaning & Chunking 
def clean_text(html: str) -> str:
    """Remove boilerplate and keep readable text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{2,}", "\n\n", text)

def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200):
    """Split into chunks with small overlap."""
    chunks, start = [], 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start < 0:
            break
    return chunks

# Fetching 
def scrape_page(url: str) -> tuple[str, BeautifulSoup | None]:
    """
    Fetch a page safely and return (clean_text, soup) for link extraction.
    Returns ("", None) for non-HTML or failures.
    """
    try:
        # quick HEAD to validate content-type & size (when provided)
        h = requests.head(url, timeout=10, allow_redirects=True)
        ctype = h.headers.get("Content-Type", "")
        if "text/html" not in ctype:
            return "", None
        clen = h.headers.get("Content-Length")
        if clen and int(clen) > MAX_BYTES:
            return "", None

        r = requests.get(url, timeout=10)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return "", None

        soup = BeautifulSoup(r.text, "html.parser")
        text = clean_text(r.text)[:MAX_TEXT_CHARS]
        return text, soup
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
        return "", None

#  Crawl driver (counts PAGES, not chunks) 
def crawl_website(start_url: str, max_pages: int = 10, out_path: str = "out/web_parsed.jsonl"):
    """
    Crawl same-domain HTML pages and write cleaned, chunked JSONL.
    - Counts pages (not chunks) against max_pages.
    - Skips binaries and large pages.
    """
    os.makedirs(Path(out_path).parent, exist_ok=True)
    visited, to_visit = set(), [start_url]
    pages_written = 0
    chunks_written = 0
    seen_chunks = set()  # dedupe identical chunk bodies across pages

    with open(out_path, "w", encoding="utf-8") as f:
        while to_visit and pages_written < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            print(f"Scraping: {url}")
            text, soup = scrape_page(url)
            if not text or soup is None:
                # nothing useful; do not count this as a page
                time.sleep(CRAWLER_DELAY_SEC)
                continue

            # Fewer, larger chunks reduce Azure vector/doc counts
            for i, chunk in enumerate(chunk_text(text, max_chars=2500, overlap=100), 1):
                # stable hash on content to avoid dup writes
                h = hashlib.sha1(chunk.encode("utf-8")).hexdigest()
                if h in seen_chunks:
                    continue
                seen_chunks.add(h)

                # make ID unique per-path + chunk index
                path_part = urlsplit(url).path or "/"
                rec = {
                    "id": f"{urlsplit(url).netloc}{path_part}#{i}",
                    "source_type": "web",
                    "file_name": path_part if path_part != "/" else "index.html",
                    "file_type": "html",
                    "path": url,
                    "text": chunk,
                    "sha1": h,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                chunks_written += 1

            pages_written += 1  # ← count pages once per fetched URL

            # enqueue new same-domain HTML links (reuse the soup we already parsed)
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                if is_html_url(link, start_url) and link not in visited:
                    to_visit.append(link)

            time.sleep(CRAWLER_DELAY_SEC)

    print(f"Saved {pages_written} pages ({chunks_written} chunks) to {out_path}")
    return out_path

#  CLI 
if __name__ == "__main__":
    crawl_website(
        start_url=START_URL,
        max_pages=CRAWLER_MAX_PAGES,
        out_path=OUT_PATH,
    )
