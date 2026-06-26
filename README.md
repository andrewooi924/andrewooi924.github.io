# Most Wanted — short link service (Cloudflare Worker + KV)

This turns a long `#w=…` wishlist link into a tiny one like
`https://most-wanted-links.you.workers.dev/s/ab3xz9k`.

How it works: the app sends your list to the Worker, which stores it in KV under a
random 7‑character key and returns that key. The short link only carries the key;
the data lives in KV. Opening the short link bounces to your app, which fetches the
list back by key.

---

## Part 1 — Deploy the Worker (URL shortening)

You need a free [Cloudflare account](https://dash.cloudflare.com/sign-up) and
[Node.js](https://nodejs.org) installed.

1. Open a terminal in the `most-wanted-worker` folder (the one with `wrangler.toml`).

2. Install Wrangler (Cloudflare's CLI) and log in:
   ```
   npm install -g wrangler
   wrangler login
   ```
   `wrangler login` opens a browser to authorize. (No global install? Use `npx wrangler …` for every command.)

3. Create the KV namespace. This prints an `id`:
   ```
   wrangler kv namespace create WISHLISTS
   ```
   (Older Wrangler versions use `wrangler kv:namespace create WISHLISTS`.)
   Copy the printed `id` into `wrangler.toml`, replacing `PASTE_KV_NAMESPACE_ID_HERE`.

4. Edit `wrangler.toml` `[vars]`:
   - `APP_URL` = your deployed app URL, e.g. `https://yourname.github.io/most-wanted/`
   - `ALLOW_ORIGIN` = your app's origin, e.g. `https://yourname.github.io` (or `*` to allow any)
   - leave `REQUIRE_AUTH = "0"` for now.

5. Deploy:
   ```
   wrangler deploy
   ```
   It prints your Worker URL, e.g. `https://most-wanted-links.YOURNAME.workers.dev`.

6. Quick test (replace the URL):
   ```
   curl -X POST https://most-wanted-links.YOURNAME.workers.dev/api/lists \
     -H "Content-Type: application/json" \
     -d '{"name":"Test","items":[["op01_10151","h"],["op01_10152","m"]]}'
   ```
   You should get back `{"id":"……"}`. Visiting `https://…workers.dev/s/THAT_ID`
   should redirect to your app.

## Part 2 — Point the app at the Worker

In the app's `index.html`, near the top of the script, set:

```js
const SHARE_API = 'https://most-wanted-links.YOURNAME.workers.dev';
```

(Leave it `''` to keep the old self-contained links.) Redeploy the app.
Now **Share → Copy public link** creates a short link, and opening one loads the
list from the Worker. If the Worker is ever down, the app automatically falls back
to the long inline link, so sharing never breaks.

### Costs / limits
Cloudflare's free plan covers ~100,000 reads and 1,000 writes per day and 1 GB of
storage — far beyond personal use. Links are permanent by default. To auto-expire,
add `{ expirationTtl: 31536000 }` (1 year) to the `WISHLISTS.put(...)` call in `worker.js`.

---

## Part 3 — Google Sign-In (optional)

Decide *why* you want auth first — it changes how much you build:

- **A) Gate link creation** (stop strangers from filling your KV): small change,
  fully supported by this Worker already. Steps below.
- **B) Cloud-sync your own wishlists across devices / accounts**: a larger feature
  (the app is currently local-first via IndexedDB). This needs per-user storage and
  read/write/delete endpoints. Not included here — ask and I'll build it.

### Setup for A (gate creation)

1. In [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services
   → Credentials → Create credentials → OAuth client ID → Web application**.
2. Under **Authorized JavaScript origins** add your app origin, e.g.
   `https://yourname.github.io` (and `http://localhost:PORT` for local testing).
3. Copy the **Client ID** (looks like `1234-abc.apps.googleusercontent.com`).
4. In `wrangler.toml` set:
   ```
   REQUIRE_AUTH = "1"
   GOOGLE_CLIENT_ID = "1234-abc.apps.googleusercontent.com"
   ```
   then `wrangler deploy` again.
5. In the app, set the same client id and add Google's script + a sign-in button.
   The Worker expects the Google **ID token** in `Authorization: Bearer <token>`,
   and the app already sends `AUTH_TOKEN` if it's set. Minimal client wiring:

   ```html
   <script src="https://accounts.google.com/gsi/client" async></script>
   ```
   ```js
   const GOOGLE_CLIENT_ID = '1234-abc.apps.googleusercontent.com';
   function startGoogleSignIn(){
     google.accounts.id.initialize({
       client_id: GOOGLE_CLIENT_ID,
       callback: (resp) => { AUTH_TOKEN = resp.credential; toast('Signed in ✓'); }
     });
     google.accounts.id.prompt();   // or render a button with google.accounts.id.renderButton
   }
   ```
   Call `startGoogleSignIn()` from a "Sign in" button. After sign-in, **Copy public
   link** will be authorized. (Google's script loads only when the user signs in, so
   the app stays offline-friendly otherwise.)

Note: this Worker verifies tokens via Google's `tokeninfo` endpoint — simple and fine
for personal scale. For high traffic you'd verify the JWT signature locally instead.
