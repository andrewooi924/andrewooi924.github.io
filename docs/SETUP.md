# Personal-use setup (RM50 ceiling)

The existing app works without cloud configuration. No paid plan is required by
this code, and no live infrastructure is created by installing dependencies.
Personal agent instructions remain outside this repository.

## Local verification

```sh
npm ci
npm run build
npm run typecheck
npm test
# With the local HTTP server running and Chromium installed:
# npx playwright install chromium && node scripts/browser-check.mjs
python3 -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python -m unittest discover -s pipeline/tests -v
npm run test:db  # Docker required; disposable PostgreSQL 17 container
python3 -m http.server 8000 --bind 127.0.0.1
```

Open http://127.0.0.1:8000. Account explains the disconnected state until configured.
`npm run dev:api` runs the API against local R2; it needs a seeded snapshot to serve
catalog data. `npx wrangler deploy --config api/wrangler.jsonc --dry-run` checks the
Worker bundle without deploying. `cloud/bundle.js` is committed for GitHub Pages;
regenerate it with `npm run build` when editing `cloud/client.js`.

## Supabase Free

1. Create a separate Supabase project; do not apply this migration to an unrelated app.
2. Execute `supabase/migrations/202609170001_cloud_lists.sql` in the SQL editor or
   use your usual Supabase CLI migration deployment. It creates an unexposed
   `private` schema and narrowly granted RPC functions in `public`.
3. Keep Email authentication and email confirmation enabled. Set the Auth site
   URL and redirect allowlist to the exact app URL. The account panel sends an
   email sign-in link. After creating your own account, disable public signup
   if this remains a personal-only deployment.
4. Put the project URL and **publishable** key in `app-config.js` and the Worker vars.
   Never put service-role or secret keys in frontend configuration.
5. Enable MFA on administrative accounts. Keep an encrypted database export and
   periodically test restoration; the free plan does not include automatic backups.

The UI explicitly saves the active wishlist or collection. It does not silently
upload local lists on login. Cloud downloads create local copies. Do not use a
shared browser for private collections unless you remove downloaded local copies.
No private cloud records are persisted by the UI automatically; the auth SDK stores
its session locally. Signing out clears the session and in-memory cloud records.

## R2 and API

Create two Standard-storage buckets:

- `most-wanted-data`: **private**, for snapshots, observations, and archives.
- `most-wanted-assets`: private; the Worker exposes only validated content-hashed artwork paths.

Never enable public access on the data bucket. Create bucket-scoped R2 S3 tokens;
use a separate asset-upload token where practical. Enable billing alerts. R2 has
billable operations above its free allowances; alerts are not hard spend caps.

Set `DATA.bucket_name` in `api/wrangler.jsonc`, and set `ALLOWED_ORIGINS` to exact
frontend origins. Remove localhost from production origins. Configure Supabase URL
and publishable key. Then, after authorizing deployment:

```sh
npm run deploy:api
```

Use its workers.dev URL or a custom `api` subdomain in `app-config.js`. Add the final
app domain to Cloudflare, Supabase Auth redirects, and the Worker origin list.
No new domain purchase is needed. DNS changes should follow a review of existing records.

## Seed and images

Credentials belong in ignored environment files or the shell environment; never commit them:
`CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_DATA_BUCKET`,
`R2_ASSETS_BUCKET`, `ASSETS_BASE_URL` (the HTTPS Worker URL followed by `/v1/images`).

```sh
# Build from existing data without making any network requests or changing source JSON.
.venv/bin/python -m pipeline.build
# Optimize a bounded number of images locally; add --upload to write to the assets bucket.
.venv/bin/python -m pipeline.images --limit 100
# Initial upload of all existing images, once the destination and rights are confirmed:
.venv/bin/python -m pipeline.images --limit 6000 --upload
.venv/bin/python -m pipeline.build
# Publishes only when explicitly run with the configured R2 credentials:
.venv/bin/python -m pipeline.publish
```

The asset uploader resumes from `asset-index.json`, stores content-hashed WebP
files, and does not trust extensions as proof of image type. Official source URLs
can be processed with `--official artifacts/ingestion/bandai.json --limit 50 --upload`.
Use `--refresh` to recheck previously mapped source images for changes.
Dry-run mappings never enter published catalogs. Image mirroring is an opt-in workflow step; daily metadata scraping does not silently
redownload the full library. Review image usage rights and robots policies first.

No R2 public access or bucket CORS is required; the Worker controls image reads.
Avoid on-demand paid image transforms.

## Daily ingestion

`pipeline/sources.json` controls enabled sources, URLs, request budget, and pacing.
The HTTP client checks robots.txt, restricts HTTPS hosts/redirects, rejects private
network destinations, bounds response sizes, and does not circumvent challenges.

- Official list: discovers release options dynamically, with distinct printing IDs.
- Yuyutei: discovers set links; existing exact listing IDs can refresh existing prices.
- Cardrush: currently the configured homepage sample, **not full-store coverage**.
  Add verified category URLs after checking parser fixtures and the request budget.
- Dorasuta: disabled after an initial HTTP 403; structured-data parser is provisional.
  Do not advertise this source as supported until permitted access and fixtures pass.

```sh
.venv/bin/python -m pipeline.run
.venv/bin/python -m pipeline.publish --restore
.venv/bin/python -m pipeline.build --ingestion artifacts/ingestion --previous artifacts/api/previous.json
.venv/bin/python -m pipeline.publish
```

Review `artifacts/ingestion/report.json` and `artifacts/api/unmatched.json`. Add
explicit entries to `pipeline/mappings.json` with `source`, `source_id`, `legacy_id`,
`condition` (`standard` only when verified), `reviewed_by`, and `evidence`.
Matching also checks card code. Never map alternate artwork by price or filename order.
New official records are published unpriced, separately from uncertain legacy matches.
Failed sources preserve their last observations, which expire from valuation after
48 hours. A >30% count drop quarantines the source. No eligible price means unknown.

The scheduled workflow is **disabled by default**. Test with workflow_dispatch
(publish=false) first. Configure GitHub Actions for this repository:

- Repository secrets: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
- Repository variables: `CLOUDFLARE_ACCOUNT_ID`, `R2_DATA_BUCKET`.
- Repository variable `MW_REFRESH_ENABLED=true` only when the dry run and budget fit.
- Optional `MW_MIRROR_IMAGES=true`: upload at most 50 new official images per run.
  The publishing token must be scoped to both app buckets. Configure variables
  `R2_ASSETS_BUCKET`, `ASSETS_BASE_URL`. Leave disabled until asset
  hosting is configured. Run the bounded manual uploader for the initial backlog.

Schedule: 20:17 UTC (04:17 Malaysia), bounded to 40 minutes/run and 180 HTTP requests.
Jobs serialize, and publish the pointer only after uploading the entire snapshot.
Pinning actions prevents tag changes silently changing dependency code. No secrets
are used in pull-request checks. Keep paid Actions overages disabled.

Up to 365 daily points per card live in R2, not the 500 MB Supabase database.
Full compressed daily states are archived separately. Older snapshots are pruned
at publish time after seven days; configure `archives/` retention (e.g. 365 days)
in R2. Never expire `published.json` or blindly expire the current snapshot.
Track R2 operations: all-variant snapshots can exceed the free write allowance as
the catalog grows. Reduce publication frequency or deduplicate objects before
paying for a larger workload. The RM50 ceiling is a budget target, not an API guarantee.

## Current boundaries

This is an incremental migration, not a finished simulator or social platform.
Cloud saves are explicit; automatic offline merge and public profiles are not implemented.
Retailer/official reconciliation requires review. The collection chart reprices today's
holdings over up to 90 observed days, with gaps for incomplete pricing. It is not a
transaction ledger: it does not reconstruct sold cards, prior quantities, or cash flows.
A complete daily account-performance ledger remains future work. Existing user data and old share links remain supported.
