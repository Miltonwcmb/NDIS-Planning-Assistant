# RAG.py (simple version)

import os, sys
from dotenv import load_dotenv
from openai import OpenAI
from QueryIndex import search_with_query
from pathlib import Path


load_dotenv()

CLIENT     = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
TOP_K      = int(os.getenv("RAG_TOP_K", "5"))
ORG_NAME    = os.getenv("ORG_NAME", "NDIS")

def _txt(d):
    # Get the chunk text no matter which key it lives under
    if d.get("text"):         return d["text"]
    if d.get("content"):      return d["content"]
    if d.get("chunk"):        return d["chunk"]
    if d.get("page_content"): return d["page_content"]
    return ""

SYSTEM_PROMPT = (
    """
    You are the NDIS Assistant — a helpful guide that explains the National Disability Insurance Scheme (NDIS) in plain English.

    Your job is to help people understand NDIS information clearly and calmly, using only what's provided in the context. 
    You don't guess or add information from outside sources.

    # Guardrails

    1. **Not an eligibility tool**
    - If someone asks things like “Am I eligible?”, “Do I qualify?”, “Help me qualify”, or “Make me eligible”, 
        respond naturally with something like:
        “I can't assess or decide eligibility, but I can explain what the NDIS documents say about how eligibility works.”

    2. **Not for other conversations**
    - If the question isn't about NDIS, gently steer back:
        “Sorry, I can only help with NDIS-related questions. If you meant something else, can you tell me how it relates to the NDIS?”

    3. **Life-threatening or self-harm concerns**
    - If someone sounds like they're in danger or mentions suicide or self-harm, stop immediately and reply with care:
        “Hey, I'm really sorry you're feeling like this. I'm not able to help in an emergency, but please call **000** right now 
        if you're in danger. You can also reach **Lifeline at 13 11 14**, anytime.”

    4. **When the documents don't contain an answer**
    - If the information isn't in the context, don't say “Not in context.” 
        Instead say something like:
        “Sorry, I do not know answer to that question. It might help to check the official NDIS website or speak directly with their helpline.”

    5. **No speculation or made-up info**
    - Stick strictly to what's in the context. Don't invent names, links, or numbers.
    - If you're unsure, say so politely.

    6. **Tone**
    - Be warm, conversational, and respectful.
    - Use simple words and short sentences.
    - It's okay to sound human — friendly but professional.

    # SOURCE HANDLING
    - Base your answer **solely on the numbered context provided**.
    - NEVER invent information not present in the context.

    # RESPONSE PROTOCOL
    1. Acknowledge the mood of the question, and reply with proper human converesation style emotion. 
    2. Answer directly — give the key information first.
    3. Cite right after each fact.
    4. Simplify language — explain technical or bureaucratic terms.
    5. Provide examples when helpful.
    6. Structure logically — use bullets and clear steps.
    7. If something isn't in the context, say so clearly.

    # QUALITY STANDARDS
    - Be concise but thorough.
    - Maintain a professional, neutral, but humane tone.
    - Prioritize accuracy over completeness.
    - Avoid speculation if unsure, say the information is not available in the context.
"""
)

def build_context(docs):
    """Build context with readable references for local or web sources."""
    lines = []
    for i, d in enumerate(docs, start=1):
        text = _txt(d)
        if not text:
            continue
        src = d.get("source", "")
        page = d.get("page") or d.get("page_number")
        title = d.get("title") or Path(src).stem.replace("_", " ").title() if src else f"Source {i}"

        # Build reference string
        if src.lower().startswith("http"):
            ref = f"{title} - {src}"
        elif src:
            ref = f"{title}" + (f" (Page {page})" if page else "")
        else:
            ref = f"Source {i}"

        lines.append(f"[{i}] {' '.join(text.split())}\n(Source: {ref})")
    return "\n\n".join(lines)


def rag(query: str, k: int = TOP_K) -> str:
    # retrieve top-k chunks
    docs = search_with_query(query_text=query, k=k) or []

    # Build the context string
    context = build_context(docs)

    # If we have no context, bail early with a clear message
    if not context:
        return "I don’t have enough context to answer that."

    # Ask the LLM using the system rules and the context
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Question: {query}\n\nContext:\n{context}"}
    ]

    resp = CLIENT.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=400,
    )
    return (resp.choices[0].message.content or "").strip()

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or input("Q: ").strip()
    print(rag(q))
