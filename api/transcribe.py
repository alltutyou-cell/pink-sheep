from http.server import BaseHTTPRequestHandler
import json
import os
import re
import tempfile
import requests

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID   = "5770bdb8e46a4c248d8b227c0fb5fec3"


# ── helpers ──────────────────────────────────────────────────────────────────

def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


def get_video_title(video_id):
    """Free YouTube oEmbed – no auth needed."""
    try:
        r = requests.get(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            timeout=6,
        )
        if r.status_code == 200:
            d = r.json()
            return d.get("title", ""), d.get("author_name", "")
    except Exception:
        pass
    return f"Video {video_id}", ""


def get_captions(video_id):
    """Try YouTube auto-captions. Returns (text, lang_code) or (None, None)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        # prefer manual, fall back to auto-generated
        for transcript in transcripts:
            entries = transcript.fetch()
            text = " ".join(e["text"].replace("\n", " ") for e in entries)
            return text, transcript.language_code
    except Exception:
        pass
    return None, None


def transcribe_with_groq(url):
    """Download audio with yt-dlp, send to Groq Whisper."""
    if not GROQ_API_KEY:
        raise RuntimeError("Groq API key not configured.")

    import yt_dlp

    tmp_dir  = tempfile.mkdtemp()
    out_tmpl = os.path.join(tmp_dir, "audio.%(ext)s")

    ydl_opts = {
        "format": "140/bestaudio[ext=m4a]/18/bestaudio",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        duration = info.get("duration", 0)
        title    = info.get("title", "")
        channel  = info.get("channel", "")

    # find downloaded file
    audio_path = None
    for f in os.listdir(tmp_dir):
        audio_path = os.path.join(tmp_dir, f)
        break
    if not audio_path:
        raise RuntimeError("Audio download failed.")

    with open(audio_path, "rb") as fh:
        audio_bytes = fh.read()
    os.remove(audio_path)

    fname = os.path.basename(audio_path)
    ext   = fname.rsplit(".", 1)[-1] if "." in fname else "m4a"
    mime  = {"m4a": "audio/m4a", "webm": "audio/webm", "mp4": "audio/mp4"}.get(ext, "audio/mpeg")

    resp = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": (fname, audio_bytes, mime)},
        data={"model": "whisper-large-v3", "response_format": "text"},
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq error {resp.status_code}: {resp.text[:300]}")

    return resp.text.strip(), title, channel, duration


def save_to_notion(title, url, channel, transcript, lang_code, duration):
    """Save a row + full transcript body to the Notion database."""
    if not NOTION_TOKEN:
        return False

    lang = "Russian" if lang_code and lang_code.startswith("ru") else "English"
    mins = int(duration // 60) if duration else 0
    dur_str = f"{mins} min" if mins else ""

    # Notion rich_text max 2000 chars per block – save snippet in property
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

    # append full transcript in 2000-char chunks
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

            # ── captions first ────────────────────────────────────────────
            transcript, lang = get_captions(video_id)
            method   = "captions"
            channel  = ""
            duration = 0

            if transcript:
                title, channel = get_video_title(video_id)
            else:
                # ── Groq fallback ─────────────────────────────────────────
                transcript, title, channel, duration = transcribe_with_groq(url)
                lang   = "unknown"
                method = "groq"

            notion_saved = save_to_notion(title, url, channel, transcript, lang, duration)

            self._respond(200, {
                "transcript":   transcript,
                "title":        title,
                "channel":      channel,
                "method":       method,
                "notion_saved": notion_saved,
            })

        except Exception as exc:
            self._respond(500, {"error": str(exc)})

    # ── helpers ───────────────────────────────────────────────────────────────

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
        pass  # silence access log noise
