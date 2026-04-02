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


def save_to_notion(title, url, channel, transcript, lang_code):
    if not NOTION_TOKEN:
        return False

    lang    = "Russian" if lang_code and lang_code.startswith("ru") else "English"
    snippet = transcript[:1900]

    page = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Video Title": {"title": [{"text": {"content": title[:200]}}]},
            "Video URL":   {"url": url},
            "Channel":     {"rich_text": [{"text": {"content": channel[:200]}}]},
            "Language":    {"select": {"name": lang}},
            "Transcript":  {"rich_text": [{"text": {"content": snippet}}]},
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
    return r.status_code == 200


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

            if not url:
                return self._respond(400, {"error": "No URL provided."})
            if not transcript:
                return self._respond(400, {"error": "No transcript provided."})

            video_id = extract_video_id(url)
            if not video_id:
                return self._respond(400, {"error": "Invalid YouTube URL."})

            title, channel = get_video_title(video_id)
            notion_saved   = save_to_notion(title, url, channel, transcript, lang)

            self._respond(200, {
                "title":        title,
                "channel":      channel,
                "notion_saved": notion_saved,
            })

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
