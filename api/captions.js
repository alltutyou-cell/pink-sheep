// Vercel Edge Function — runs on Cloudflare's edge network
// 1. Fetches the YouTube watch page (from Cloudflare IP, not AWS)
// 2. Extracts signed caption URLs from the embedded player response
// 3. Fetches actual captions using those authenticated URLs
export const config = { runtime: 'edge' };

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

export default async function handler(req) {
  const { searchParams } = new URL(req.url);
  const videoId = searchParams.get('v');
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };

  if (!videoId) {
    return new Response(JSON.stringify({ error: 'Missing video ID' }), { status: 400, headers: cors });
  }

  try {
    // Step 1: Fetch the YouTube watch page from Cloudflare edge
    const pageRes = await fetch(`https://www.youtube.com/watch?v=${videoId}`, {
      headers: {
        'User-Agent': UA,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      },
    });

    if (!pageRes.ok) {
      return new Response(
        JSON.stringify({ error: `YouTube returned HTTP ${pageRes.status}` }),
        { status: 422, headers: cors }
      );
    }

    const html = await pageRes.text();

    // Check for consent/bot pages
    if (html.includes('consent.youtube.com') || html.includes('before you continue')) {
      return new Response(
        JSON.stringify({ error: 'YouTube served a consent page. Captions not accessible from this server.' }),
        { status: 422, headers: cors }
      );
    }

    // Step 2: Extract signed caption base URLs from the page
    // These URLs contain authentication tokens that YouTube requires
    const urlPattern = /"baseUrl"\s*:\s*"(https?:[^"]*timedtext[^"]*)"/g;
    const matches = [...html.matchAll(urlPattern)];

    if (matches.length === 0) {
      // Try to detect why — does the page have captions data at all?
      const hasCaptions = html.includes('captionTracks');
      const hasPlayer = html.includes('ytInitialPlayerResponse');
      return new Response(
        JSON.stringify({
          error: hasCaptions
            ? 'Found caption metadata but no URLs. Please try again.'
            : hasPlayer
              ? 'This video has no captions enabled.'
              : 'Could not parse YouTube page — the page structure may have changed.',
        }),
        { status: 422, headers: cors }
      );
    }

    // Step 3: Fetch each caption track using the signed URL
    for (const match of matches) {
      const captionUrl = match[1]
        .replace(/\\u0026/g, '&')
        .replace(/\\\//g, '/')
        + '&fmt=json3';

      try {
        const capRes = await fetch(captionUrl, {
          headers: { 'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9' },
        });
        if (!capRes.ok) continue;

        const capData = await capRes.json();
        const parts = (capData.events || [])
          .flatMap(ev => (ev.segs || []).map(s => (s.utf8 || '').replace(/\n/g, ' ')))
          .filter(p => p.trim());

        const text = parts.join(' ');
        if (text) {
          const langMatch = captionUrl.match(/[?&]lang=([^&]+)/);
          const lang = langMatch ? decodeURIComponent(langMatch[1]) : 'unknown';
          return new Response(JSON.stringify({ transcript: text, lang }), { headers: cors });
        }
      } catch {
        continue;
      }
    }

    return new Response(
      JSON.stringify({ error: 'Found caption URLs but could not download the text. Please try again.' }),
      { status: 422, headers: cors }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: `Error: ${err.message}` }),
      { status: 500, headers: cors }
    );
  }
}
