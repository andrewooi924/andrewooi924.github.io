# Most Wanted

A personal One Piece TCG wishlist and collection app.

The new budget-conscious cloud setup uses a Cloudflare Worker API, Supabase Free
for private lists, and R2 for images and versioned price snapshots. The app still
works locally without cloud configuration.

- [Setup, limits, and deployment](docs/SETUP.md)
- [API contract and privacy](docs/API.md)

## Legacy short-link service

The instructions below describe the existing optional KV short-link service.
The new account-backed sharing flow uses `api/wrangler.jsonc` instead.

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

## Google Sign-In

Most Wanted uses Supabase Auth for private cloud lists and revocable public links.
The account panel can use Google OAuth after the provider is configured. See
[the Supabase setup guide](docs/SETUP.md#supabase-free) for the required Google
Cloud client, callback, and deployment flag. The Google client secret stays in
Supabase; the browser sends Supabase session tokens to the Worker for private
list requests.
