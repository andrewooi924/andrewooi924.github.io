# Most Wanted API v1

Base URL is configured at deployment. All responses are JSON. Catalog and prices
are public; user writes require `Authorization: Bearer <Supabase access token>`.
The Worker never receives a Supabase service-role key. Errors use `{ "error": "..." }`.
Limits: 60 requests/minute per IP at the Worker, 1 MB request body, 2,000 items/list,
50 lists/account. Cloudflare's edge rate limiter is approximate, not a global quota.

| Method and path | Response |
| --- | --- |
| GET `/health` | Liveness and API version (not downstream readiness) |
| GET `/v1/manifest` | Completed snapshot version, source health, publication time |
| GET `/v1/catalog` | Catalog array compatible with the existing app |
| GET `/v1/variants/{id}` | One variant; accepts canonical UUID or legacy alias |
| GET `/v1/variants/{id}/offers` | Observed retailer offers, including freshness/stock/condition |
| GET `/v1/variants/{id}/price-history` | Up to 365 daily reference prices; empty until observed |
| GET `/v1/me/lists` | Owner's cloud copies, including private notes and costs |
| PUT `/v1/me/lists` | Create or revise a cloud copy |
| PUT `/v1/me/lists/{uuid}/share` | Create/rotate token or revoke sharing |
| DELETE `/v1/me/lists/{uuid}` | Delete cloud copy and revoke its share link |
| GET `/v1/shared/{token}` | Allowlisted fields only; never purchase costs or notes |

Save body:

```json
{"localId":"device-list-id","kind":"collection","title":"My collection","revision":0,
 "items":[{"id":"op01_10151","quantity":1,"pricePaid":1200,"note":"Private note"}]}
```

Use the latest returned `revision` on subsequent saves. A 409 means another save
won the race: fetch the cloud copy and reconcile deliberately. Never automatically
retry a conflict with an incremented revision. Existing legacy IDs remain usable.

Sharing body: `{"token":"<32 lowercase hex characters from 16 random bytes>"}`.
To revoke: `{"token":null}`. Tokens are stored only as SHA-256 hashes. App links
use `#share=<token>` so the hosting server does not receive the token. These are
**unlisted** live cloud copies, not discoverable profiles. A cloud copy changes
when saved; local edits do not synchronize automatically. A new token invalidates
the old one. Revocation blocks future fetches, not already downloaded copies.

Catalog responses include `X-Data-Version` and short cache lifetimes. Personal and
shared responses use `Cache-Control: no-store`. Authentication is validated by
Supabase on every RPC. RLS alone is not used as a field-redaction mechanism.
The database's public RPC interface is also reachable directly; its permissions,
validation and ownership checks do not depend on Worker CORS or rate limiting.

`variantId` is the new permanent identifier; `id` is the app's retained alias.
`mappingStatus=legacy-provisional` means the pre-existing retailer/image mapping
has not been independently reviewed. Official discoveries use distinct IDs until
reviewed. No gameplay engine or executable effects are provided by this API.
Historical matches must pin a separately defined ruleset when an engine is added.

Prices are estimated retail asking prices, not realized sale values. Only fresh
(48-hour), in-stock, JPY, standard-condition observations contribute. One minimum
eligible quote/store is used before taking the median. `legacy-undated` prices
come from the existing repository without a trustworthy observation time and
never create fake historical points. `unavailable` is unknown, not zero.

`GET /v1/price-history` returns a public object keyed by legacy card ID, each value
a list of `[YYYY-MM-DD, JPY price]` observations for up to 90 days. This lets the
collection chart use one request instead of one request per holding. Missing days
and prices remain absent; never treat them as zero.
