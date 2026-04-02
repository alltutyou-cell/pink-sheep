from http.server import BaseHTTPRequestHandler
import json
import os
import re
import requests
import xml.etree.ElementTree as ET

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID = "5770bdb8e46a4c248d8b227c0fb5fec3"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


def get_video_title(video_id):
    """Free YouTube oEmbed – no auth needed."""
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


# ── caption sources ───────────────────────────────────────────────────────────

def _captions_via_timedtext(video_id):
    """Old YouTube timedtext API — lightweight, avoids modern bot detection."""
    try:
        list_r = requests.get(
            f"https://video.google.com/timedtext?type=list&v={video_id}",
            headers=_BROWSER_HEADERS,
            timeout=8,
        )
        if list_r.status_code != 200 or not list_r.text.strip():
            return None, None

        root = ET.fromstring(list_r.text)
        tracks = root.findall("track")
        if not tracks:
            return None, None

        # Prefer manual captions; fall back to auto-generated (kind="asr")
        track = next((t for t in tracks if not t.get("kind")), tracks[0])
        lang  = track.get("lang_code", "unknown")
        name  = track.get("name", "")
        kind  = track.get("kind", "")

        params = f"v={video_id}&lang={lang}&fmt=json3"
        if name:
            params += f"&name={name}"
        if kind:
            params += f"&kind={kind}"

        cap_r = requests.get(
            f"https://www.youtube.com/api/timedtext?{params}",
            headers=_BROWSER_HEADERS,
            timeout=10,
        )
        if cap_r.status_code != 200:
            return None, None

        events = cap_r.json().get("events", [])
        parts = [
            seg.get("utf8", "").replace("\n", " ")
            for ev in events
            for seg in ev.get("segs", [])
        ]
        text = " ".join(p for p in parts if p.strip())
        return (text, lang) if text else (None, None)
    except Exception:
        return None, None


def _captions_via_page(video_id):
    """Parse the embedded ytInitialPlayerResponse from the YouTube watch page."""
    try:
        r = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=_BROWSER_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return None, None

        idx = r.text.find("ytInitialPlayerResponse =")
        if idx == -1:
            return None, None
        start = r.text.index("{", idx)
        data, _ = json.JSONDecoder().raw_decode(r.text, start)

        tracks = (
            data.get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
        )
        if not tracks:
            return None, None

        track   = next((t for t in tracks if not t.get("kind")), tracks[0])
        lang    = track.get("languageCode", "unknown")
        base_url = track.get("baseUrl", "")
        if not base_url:
            return None, None

        cap_r = requests.get(base_url + "&fmt=json3", headers=_BROWSER_HEADERS, timeout=10)
        if cap_r.status_code != 200:
            return None, None

        events = cap_r.json().get("events", [])
        parts = [
            seg.get("utf8", "").replace("\n", " ")
            for ev in events
            for seg in ev.get("segs", [])
        ]
        text = " ".join(p for p in parts if p.strip())
        return (text, lang) if text else (None, None)
    except Exception:
        return None, None


def get_captions(video_id):
    """Try both caption sources. Returns (text, lang_code) or (None, None)."""
    text, lang = _captions_via_timedtext(video_id)
    if text:
        return text, lang
    return _captions_via_page(video_id)


# ── Notion ────────────────────────────────────────────────────────────────────

def save_to_notion(title, url, channel, transcript, lang_code, duration):
    if not NOTION_TOKEN:
        return False

    lang    = "Russian" if lang_code and lang_code.startswith("ru") else "English"
    mins    = int(duration // 60) if duration else 0
    dur_str = f"{mins} min" if mins else ""
    snippet = transcript[:1900]

    page = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Video Title": {"title": [{"text": {"content": title[:200]}}]},
            "Video URL":   {"url": url},
            "Channel":     {"rich_text": [{"text": {"content": channel[:200]}}]},
            "Language":    {"select": {"name": lang}},
            "Duration":    {"rich_text": [{"text": {"content": dur_str}}]},
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


# ── Vercel handler ────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            url    = body.get("url", "").strip()

            if not url:
                return self._respond(400, {"error": "No URL provided."})

            video_id = extract_video_id(url)
            if not video_id:
                return self._respond(400, {"error": "Invalid YouTube URL."})

            transcript, lang = get_captions(video_id)

            if not transcript:
                return self._respond(422, {
                    "error": (
                        "No captions found for this video. "
                        "YouTube may have blocked caption access from the server, "
                        "or this video has no captions enabled. "
                        "Try a different video, or check that captions are turned on."
                    )
                })

            title, channel = get_video_title(video_id)
            notion_saved   = save_to_notion(title, url, channel, transcript, lang, 0)

            self._respond(200, {
                "transcript":   transcript,
                "title":        title,
                "channel":      channel,
                "method":       "captions",
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
