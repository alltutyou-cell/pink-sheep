// Vercel Edge Function — calls Apify's YouTube Transcript actor
// Apify uses residential proxies, so YouTube never blocks it
export const config = { runtime: 'edge' };

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: corsHeaders() });
  }

  const { searchParams } = new URL(req.url);
  const videoId = searchParams.get('v');
  const hdrs = corsHeaders();

  if (!videoId) {
    return new Response(JSON.stringify({ error: 'Missing video ID' }), { status: 400, headers: hdrs });
  }

  const APIFY_TOKEN = process.env.APIFY_TOKEN;
  if (!APIFY_TOKEN) {
    return new Response(
      JSON.stringify({ error: 'APIFY_TOKEN not set in Vercel environment variables.' }),
      { status: 500, headers: hdrs }
    );
  }

  try {
    const res = await fetch(
      `https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/run-sync-get-dataset-items?token=${APIFY_TOKEN}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          youtube_url: `https://www.youtube.com/watch?v=${videoId}`,
          include_transcript_text: true,
        }),
      }
    );

    if (!res.ok) {
      const text = await res.text();
      return new Response(
        JSON.stringify({ error: `Apify returned ${res.status}: ${text.slice(0, 200)}` }),
        { status: 422, headers: hdrs }
      );
    }

    const items = await res.json();

    if (!items.length || items[0].status !== 'success' || !items[0].transcript_text) {
      const msg = items[0]?.message || 'No transcript available';
      return new Response(JSON.stringify({ error: msg }), { status: 422, headers: hdrs });
    }

    const item = items[0];
    return new Response(JSON.stringify({
      transcript: item.transcript_text,
      lang: item.language || 'unknown',
      title: item.title || '',
      channel: item.channel_name || '',
      duration: item.duration_seconds || 0,
    }), { headers: hdrs });

  } catch (err) {
    return new Response(JSON.stringify({ error: `Error: ${err.message}` }), { status: 500, headers: hdrs });
  }
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };
}
