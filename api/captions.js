// Vercel Edge Function — runs on Cloudflare's edge, not AWS
// YouTube does not block Cloudflare IPs (too many legitimate sites use them)
export const config = { runtime: 'edge' };

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';
const LANGS = ['ru', 'en', 'uk', 'de', 'fr', 'es', 'it', 'pt', 'zh', 'ja', 'ko'];

async function fetchTimedtext(videoId, lang, kind) {
  const qs = new URLSearchParams({ v: videoId, lang, fmt: 'json3' });
  if (kind) qs.set('kind', kind);
  try {
    const r = await fetch(`https://www.youtube.com/api/timedtext?${qs}`, {
      headers: { 'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9' },
    });
    if (!r.ok) return null;
    const data = await r.json();
    const parts = (data.events || [])
      .flatMap(ev => (ev.segs || []).map(s => (s.utf8 || '').replace(/\n/g, ' ')))
      .filter(p => p.trim());
    return parts.length ? parts.join(' ') : null;
  } catch {
    return null;
  }
}

export default async function handler(req) {
  const { searchParams } = new URL(req.url);
  const videoId = searchParams.get('v');
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };

  if (!videoId) {
    return new Response(JSON.stringify({ error: 'Missing video ID' }), { status: 400, headers: cors });
  }

  // ASR (auto-generated) first, then manual — for each language
  for (const kind of ['asr', '']) {
    for (const lang of LANGS) {
      const text = await fetchTimedtext(videoId, lang, kind);
      if (text) {
        return new Response(JSON.stringify({ transcript: text, lang }), { headers: cors });
      }
    }
  }

  return new Response(
    JSON.stringify({ error: 'No captions found. This video may not have captions, or they may be disabled.' }),
    { status: 422, headers: cors }
  );
}
