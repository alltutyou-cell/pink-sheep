"""
Receives a pre-fetched transcript from the frontend and saves it to Notion.
YouTube caption fetching is handled by api/captions.js (Vercel Edge Function).
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID = "5770bdb8e46a4c248d8b227c0fb5fec3"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


def get_video_title(video_id):
    try:
        r = requests.get(
            f"https://www.youtube.com/oembed"
            f"?url=https://www.youtube.com/watch?v={video_id}&format=json",
            timeout=6,
        )
        if r.status_code == 200:
            d = r.json()
            return d.get("title", ""), d.get("author_name", "")
    except Exception:
        pass
    return f"Video {video_id}", ""


def translate_title(title):
    """Translate video title to English using Groq LLM."""
    if not GROQ_API_KEY or not title:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": "Translate the following video title to English. Return ONLY the translated title, nothing else."},
                    {"role": "user", "content": title},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return ""


def save_to_notion(title, url, channel, transcript, lang_code, duration=0):
    if not NOTION_TOKEN:
        return False, "NOTION_TOKEN not set"

    lang    = "Russian" if lang_code and lang_code.startswith("ru") else "English"
    mins    = int(duration // 60) if duration else 0
    dur_str = f"{mins} min" if mins else ""
    snippet = transcript[:1900]

    # Translate title to English
    eng_title = translate_title(title) if lang != "English" else title

    page = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Video Title":   {"title": [{"text": {"content": title[:200]}}]},
            "English Title": {"rich_text": [{"text": {"content": eng_title[:200]}}]},
            "Video URL":     {"url": url},
            "Channel":       {"rich_text": [{"text": {"content": channel[:200]}}]},
            "Language":      {"select": {"name": lang}},
            "Duration":      {"rich_text": [{"text": {"content": dur_str}}]},
            "Transcript":    {"rich_text": [{"text": {"content": snippet}}]},
        },
        "children": [
            {
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Full Transcript"}}]},
            }
        ],
    }

    for i in range(0, len(transcript), 2000):
        page["children"].append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": transcript[i:i+2000]}}]},
        })

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization":  f"Bearer {NOTION_TOKEN}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        },
        json=page,
        timeout=15,
    )
    if r.status_code == 200:
        return True, ""
    return False, f"Notion {r.status_code}: {r.text[:300]}"


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length     = int(self.headers.get("Content-Length", 0))
            body       = json.loads(self.rfile.read(length))
            url        = body.get("url", "").strip()
            transcript = body.get("transcript", "").strip()
            lang       = body.get("lang", "unknown")
            title      = body.get("title", "").strip()
            channel    = body.get("channel", "").strip()
            duration   = body.get("duration", 0)

            if not url:
                return self._respond(400, {"error": "No URL provided."})
            if not transcript:
                return self._respond(400, {"error": "No transcript provided."})

            video_id = extract_video_id(url)
            if not video_id:
                return self._respond(400, {"error": "Invalid YouTube URL."})

            # Use title/channel from Apify if provided; fall back to oEmbed
            if not title:
                title, channel = get_video_title(video_id)
            notion_saved, notion_err = save_to_notion(title, url, channel, transcript, lang, duration)

            resp = {
                "title":        title,
                "channel":      channel,
                "notion_saved": notion_saved,
            }
            if notion_err:
                resp["notion_error"] = notion_err
            self._respond(200, resp)

        except Exception as exc:
            self._respond(500, {"error": str(exc)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass
