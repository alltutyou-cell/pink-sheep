from http.server import BaseHTTPRequestHandler
import json
import os
import re
import tempfile
import time
import requests

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
ASSEMBLYAI_KEY    = os.environ.get("ASSEMBLYAI_KEY", "")
NOTION_TOKEN      = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID      = "5770bdb8e46a4c248d8b227c0fb5fec3"


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
    """Try YouTube captions (manual + auto-generated). Returns (text, lang_code) or (None, None)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()          # v1.x requires instance

        # 1. try to get any available transcript
        t_list = api.list(video_id)
        for t in t_list:
            try:
                fetched = api.fetch(video_id, languages=[t.language_code])
                text = " ".join(s.text.replace("\n", " ") for s in fetched)
                return text, t.language_code
            except Exception:
                continue

    except Exception:
        pass
    return None, None


def get_direct_audio_url(url):
    """Use pytubefix to extract a direct CDN audio URL (no download needed)."""
    from pytubefix import YouTube
    yt = YouTube(url)
    stream = (
        yt.streams.filter(only_audio=True, file_extension="mp4").order_by("abr").last()
        or yt.streams.filter(only_audio=True).first()
    )
    if not stream:
        raise RuntimeError("No audio stream found for this video.")
    return stream.url


def transcribe_with_assemblyai(url):
    """Get direct audio CDN URL via pytubefix, then transcribe with AssemblyAI."""
    if not ASSEMBLYAI_KEY:
        raise RuntimeError(
            "This video has no YouTube captions. "
            "Add ASSEMBLYAI_KEY in Vercel env vars to enable AI transcription."
        )

    # Get the direct CDN audio URL — AssemblyAI will download from there
    audio_url = get_direct_audio_url(url)

    headers = {"authorization": ASSEMBLYAI_KEY, "content-type": "application/json"}

    # 1. submit
    submit = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json={"audio_url": audio_url, "language_detection": True, "speech_models": ["universal-2"]},
        timeout=15,
    )
    if submit.status_code != 200:
        raise RuntimeError(f"AssemblyAI submit error: {submit.text[:200]}")

    transcript_id = submit.json()["id"]

    # 2. poll until done (max ~270 s to stay under Vercel's 300 s limit)
    for _ in range(90):
        time.sleep(3)
        poll = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
            headers=headers,
            timeout=10,
        ).json()

        status = poll.get("status")
        if status == "completed":
            text     = poll.get("text", "")
            lang     = poll.get("language_code", "unknown")
            duration = poll.get("audio_duration", 0)
            return text, "", duration, lang   # title & channel via oEmbed below

        if status == "error":
            raise RuntimeError(f"AssemblyAI error: {poll.get('error', 'unknown')}")

    raise RuntimeError("AssemblyAI transcription timed out.")


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
                # ── AssemblyAI fallback (handles YouTube download server-side) ──
                transcript, _, duration, lang = transcribe_with_assemblyai(url)
                title, channel = get_video_title(video_id)
                method = "assemblyai"

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
