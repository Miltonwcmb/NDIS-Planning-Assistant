from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from RAGLLM import rag
from threading import Thread
from werkzeug.serving import make_server
from markdown import markdown
import re
from urllib.parse import urlparse

load_dotenv()

def create_app() -> Flask:
    app = Flask(__name__)

    PAGE = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>I love NDIS</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        :root{ --purple:#4A148C; --green:#2e7d32; --card-bg:rgba(255,255,255,0.92); }
        *{box-sizing:border-box;}
        html,body{height:100%;margin:0;}
        body{
          font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
          font-size:16px; color:#111;
          background:
            linear-gradient(rgba(255,255,255,.65),rgba(255,255,255,.65)),
            url("https://cbtprofessionals.com.au/wp-content/uploads/2020/06/NDIS-Service-Page.png")
            no-repeat center center fixed;
          background-size:cover;
          display:flex; flex-direction:column; align-items:center; gap:16px;
        }
        .top-image{
          width:min(1100px,95vw); margin-top:24px; border-radius:14px;
          box-shadow:0 8px 28px rgba(0,0,0,.18);
        }
        h1{
          margin:10px 0 0; font-size:clamp(28px,3.2vw,42px); font-weight:800;
          color:var(--purple); text-align:center;
        }
        .card{
          width:min(900px,92vw); margin:14px auto 36px; background:var(--card-bg);
          border:2px solid var(--purple); border-radius:16px;
          box-shadow:0 10px 30px rgba(0,0,0,.16); padding:20px;
        }
        .chatbox{
          width:100%; max-height:60vh; overflow-y:auto; background:#fff;
          border:1px solid #ddd; border-radius:12px; padding:12px; margin-bottom:10px;
          display:flex; flex-direction:column; gap:8px;
        }
        .msg{ padding:10px; border-radius:12px; border:1px solid #e6e6e6; }
        .msg.user{
          background: linear-gradient(90deg,#ffd6d6 0%,#ffe2b3 20%,#fff6b3 40%,#d4f8d4 60%,#d6e8ff 80%,#f0d6ff 100%);
          color:#111; background-blend-mode: lighten;
        }
        .msg.assistant{
          background:#eef7ff;
          border:1px solid #d5e6ff;
          color:#111;
          white-space:normal;
        }
        .label{display:block; font-weight:700; margin:8px 0; color:var(--purple);}
        textarea{
          width:100%; height:140px; padding:14px; border:2px solid #d4c3e6;
          border-radius:12px; font-size:16px; line-height:1.4; resize:vertical;
        }
        .btn{
          margin-top:12px; padding:12px 18px; border:0; border-radius:12px;
          background:linear-gradient(90deg,var(--purple),var(--green));
          color:#fff; font-weight:700; cursor:pointer;
        }
      </style>
    </head>
    <body>
      <img class="top-image"
           src="https://i0.wp.com/sunshinehomesupport.com/wp-content/uploads/2025/07/NDIS-1.jpg?fit=1024%2C338&ssl=1" />
      <h1>NDIS Planning Assistant</h1>

      <section class="card" role="region" aria-label="NDIS chat">
        <div id="chatBox" class="chatbox" aria-live="polite" aria-label="Conversation transcript"></div>

        <label class="label" for="q">Hey — ASK ME !</label>
        <textarea id="q" placeholder="Enter to send • Shift+Enter for newline"></textarea>
        <button class="btn" id="askBtn" type="button">ASK Away !</button>
      </section>

      <script>
        const btn = document.getElementById('askBtn');
        const qEl  = document.getElementById('q');
        const box  = document.getElementById('chatBox');

        let chatHistory = [];

        function renderChat(){
          box.innerHTML = '';
          chatHistory.forEach(m => {
            const div = document.createElement('div');
            div.className = 'msg ' + m.role;
            if (m.role === 'assistant') {
              div.innerHTML = '<strong>NDIS:</strong> ' + m.content;
            } else {
              div.textContent = 'You: ' + m.content;
            }
            box.appendChild(div);
          });
          box.scrollTop = box.scrollHeight;
        }

        async function ask(){
          const q = (qEl.value || '').trim();
          if(!q) return;

          chatHistory.push({ role: 'user', content: q });
          renderChat();
          qEl.value = '';

          chatHistory.push({ role: 'assistant', content: 'Thinking...' });
          renderChat();

          try{
            const res  = await fetch('/api/plan', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              body: JSON.stringify({ query: q })
            });
            const data = await res.json();
            const content = data?.answer_html || data?.answer || 'Error';
            chatHistory[chatHistory.length - 1] = { role: 'assistant', content };
          }catch(e){
            chatHistory[chatHistory.length - 1] = {
              role: 'assistant',
              content: 'Network or server error: ' + e
            };
          }
          renderChat();
        }

        btn.addEventListener('click', ask);
        qEl.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            ask();
          }
        });
      </script>
    </body>
    </html>
    """

    @app.get("/")
    def home():
        return render_template_string(PAGE)

    def _fix_bullets(text: str) -> str:
        lines = [l.rstrip() for l in text.splitlines()]
        out = []
        i = 0
        while i < len(lines):
            cur = lines[i].strip()
            if cur in {"-", "*", "•"}:
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines):
                    out.append("- " + lines[j].lstrip())
                    i = j + 1
                    continue
                else:
                    i = j
                    continue
            out.append(lines[i])
            i += 1
        text = "\n".join(out)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _collect_refs(r: dict) -> list[dict]:
        if not isinstance(r, dict):
            return []
        for key in ("refs", "sources", "documents", "context", "chunks"):
            val = r.get(key)
            if isinstance(val, list):
                out = []
                for it in val:
                    if isinstance(it, dict):
                        url = it.get("url") or it.get("link") or it.get("source") or it.get("href")
                        title = it.get("title") or it.get("name") or it.get("doc_title") or url
                        page = it.get("page") or it.get("page_number") or it.get("pg")
                        out.append({"url": url, "title": (title or "").strip(), "page": page})
                if out:
                    return out
        return []

    @app.post("/api/plan")
    def plan():
        if not request.is_json:
            return jsonify({"error": "Send JSON: {'query': '...'}"}), 400
        q = (request.get_json(silent=True) or {}).get("query", "").strip()
        if not q:
            return jsonify({"error": "Please provide 'query'"}), 400

        result = rag(q)
        if isinstance(result, dict):
            answer_text = result.get("answer") or result.get("output") or result.get("text") or str(result)
        else:
            answer_text = str(result)

        clean_text = _fix_bullets(answer_text)
        answer_html = markdown(clean_text, extensions=["fenced_code", "tables", "sane_lists"])

        refs = _collect_refs(result) if isinstance(result, dict) else []
        if refs:
            answer_html = _link_citations(answer_html, refs)

        return jsonify({"answer": answer_text, "answer_html": answer_html}), 200

    return app

class Server(Thread):
    def __init__(self, app: Flask, host: str = "0.0.0.0", port: int = 8000):
        super().__init__(daemon=True)
        self._srv = make_server(host, port, app)
        self._ctx = app.app_context()
        self._ctx.push()

    def run(self):
        self._srv.serve_forever()

    def stop(self):
        self._srv.shutdown()

def start_server(host: str = "0.0.0.0", port: int = 8000) -> Server:
    app = create_app()
    server = Server(app, host=host, port=port)
    server.start()
    return server

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=False)
