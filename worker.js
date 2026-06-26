/* Most Wanted — wishlist short-link service (Cloudflare Worker + KV)
 *
 * Routes:
 *   POST /api/lists          { name, items:[[id,pri],...] }  -> { id }
 *   GET  /api/lists/:id       -> stored JSON { n, i, by? }   (used by the app)
 *   GET  /s/:id               -> 302 redirect to the app at #s=:id (the human short link)
 *   OPTIONS *                 -> CORS preflight
 *
 * KV binding (wrangler.toml): WISHLISTS
 * Vars: APP_URL, ALLOW_ORIGIN, REQUIRE_AUTH ('0'|'1'), GOOGLE_CLIENT_ID (only if REQUIRE_AUTH=1)
 */

const ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789'; // no 0/o/1/l look-alikes
function shortId(n = 7) {
  const a = new Uint8Array(n); crypto.getRandomValues(a);
  let s = ''; for (const b of a) s += ALPHABET[b % ALPHABET.length];
  return s;
}
function cors(env) {
  return {
    'Access-Control-Allow-Origin': env.ALLOW_ORIGIN || '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}
function json(data, env, status = 200) {
  return new Response(JSON.stringify(data), {
    status, headers: { 'Content-Type': 'application/json', ...cors(env) },
  });
}

// Lightweight Google ID-token check via Google's tokeninfo endpoint.
async function verifyGoogle(idToken, env) {
  if (!idToken) return null;
  const r = await fetch('https://oauth2.googleapis.com/tokeninfo?id_token=' + encodeURIComponent(idToken));
  if (!r.ok) return null;
  const p = await r.json();
  if (env.GOOGLE_CLIENT_ID && p.aud !== env.GOOGLE_CLIENT_ID) return null;
  if (p.iss !== 'accounts.google.com' && p.iss !== 'https://accounts.google.com') return null;
  if (p.exp && Number(p.exp) * 1000 < Date.now()) return null;
  return { sub: p.sub, email: p.email, name: p.name };
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname;

    if (req.method === 'OPTIONS') return new Response(null, { headers: cors(env) });

    // Create a short link
    if (req.method === 'POST' && path === '/api/lists') {
      let user = null;
      if (env.REQUIRE_AUTH === '1') {
        const auth = req.headers.get('Authorization') || '';
        user = await verifyGoogle(auth.startsWith('Bearer ') ? auth.slice(7) : '', env);
        if (!user) return json({ error: 'sign-in required' }, env, 401);
      }
      let body;
      try { body = await req.json(); } catch { return json({ error: 'bad json' }, env, 400); }
      if (!body || !Array.isArray(body.items)) return json({ error: 'bad payload' }, env, 400);

      const record = JSON.stringify({
        n: String(body.name || 'Wishlist').slice(0, 80),
        i: body.items.slice(0, 2000),
        by: user ? (user.name || user.email) : undefined,
        t: Date.now(),
      });
      if (record.length > 200000) return json({ error: 'too large' }, env, 413);

      let id;
      for (let attempt = 0; attempt < 5; attempt++) {
        id = shortId();
        if (!(await env.WISHLISTS.get('w:' + id))) break;
      }
      // No TTL = permanent. To auto-expire after a year add: { expirationTtl: 31536000 }
      await env.WISHLISTS.put('w:' + id, record);
      return json({ id }, env);
    }

    // Read a list (the app fetches this)
    if (req.method === 'GET' && path.startsWith('/api/lists/')) {
      const id = path.slice('/api/lists/'.length);
      const data = await env.WISHLISTS.get('w:' + id);
      if (!data) return json({ error: 'not found' }, env, 404);
      return new Response(data, {
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=300', ...cors(env) },
      });
    }

    // Human short link -> bounce to the app with #s=:id
    if (req.method === 'GET' && path.startsWith('/s/')) {
      const id = path.slice(3);
      const app = env.APP_URL || 'https://example.github.io/most-wanted/';
      return Response.redirect(app + '#s=' + encodeURIComponent(id), 302);
    }

    return new Response('Most Wanted link service', { headers: cors(env) });
  },
};
