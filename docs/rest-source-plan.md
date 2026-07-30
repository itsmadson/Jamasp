# REST sources: the plan

A REST API is a data source that cannot run SQL. Everything else about جاماسپ —
scan, describe, approve, ask, report — should work unchanged. This is how a REST
source is made to fit the same shape, and where it honestly cannot.

The decisions this is built on: structure comes from an **OpenAPI spec**, all four
auth styles are supported, and a question becomes an **endpoint plus parameters**
chosen by the model and validated against the spec.

## 1. What a REST source is made of

```
config (encrypted, exactly like a DSN)
  base_url    https://api.example.com
  spec_url    https://api.example.com/openapi.json    (or a pasted document)
  auth        one of the four shapes below
```

The spec is fetched at scan time and stored with the snapshot, so a scan is
reproducible and a spec that changes shows up as drift — the same mechanism that
already flags a renamed column.

## 2. Mapping REST onto the existing model

The pipeline's vocabulary is entities, fields and relationships. REST maps cleanly
enough that no new concepts are needed:

| SQL | REST |
| --- | --- |
| table | a `GET` endpoint returning a collection |
| column | a field in that endpoint's response schema |
| row count | `x-total-count`, or a `total` in the envelope, when present |
| foreign key | a `$ref` between schemas, or `{id}` in a path |
| `WHERE` | query parameters the endpoint declares |
| `LIMIT` | the endpoint's own paging parameters |

**Only collection `GET`s become entities.** A `POST /users` is a write and never
appears. A `GET /users/{id}` is not a table — it is a single-row lookup, recorded
as a *lookup* on the `users` entity and used for joins, not listed separately.

Introspection is therefore: fetch spec → walk paths → keep safe collection reads →
resolve each response schema (following `$ref`, `allOf`, and envelope wrappers like
`{data: [...]}`) into a flat field list with types.

## 3. Auth

Four shapes, one interface. All secrets encrypted with the same key as a DSN, and
never returned by any endpoint.

```
bearer   { type: "bearer",  token: "..." }
         { type: "header",  name: "X-API-Key", value: "..." }
basic    { type: "basic",   username: "...", password: "..." }
oauth2   { type: "oauth2",  token_url, client_id, client_secret, scope? }
login    { type: "login",   login_url, payload: {...}, token_path: "data.token",
                            header: "Authorization", prefix: "Bearer",
                            ttl_s: 3600 }
```

`oauth2` and `login` hold a token in memory with its expiry and refresh **before**
it expires, not after a 401 — a retry-on-401 loop doubles every request against an
API that may be rate limited. A refresh failure is reported as a source health
failure, the same way a bad password on a database is.

The OpenAPI `securitySchemes` block tells us which of these the API expects, so the
add-source form asks only for the fields that API actually needs.

## 4. Answering a question

`generate_sql` has a REST sibling, `generate_request`. Given the endpoints the
knowledge export approved and their declared parameters, the model returns:

```json
{
  "endpoint": "GET /users",
  "params": { "status": "active", "city": "تهران", "page_size": 100 },
  "explanation": { "fa": "...", "en": "..." }
}
```

The validator then refuses anything the spec does not support — an unknown path, an
undeclared parameter, a value outside a declared enum, or any method other than
`GET`. This is the same guarantee the SQL validator gives: the model proposes, the
spec decides.

**Paging is ours, not the model's.** The executor follows `next` links or increments
the page parameter until the row limit is reached, so a question never depends on
the model having reasoned correctly about pagination.

## 5. What REST honestly cannot do

Worth stating plainly, because the alternative is a feature that quietly returns
wrong answers:

- **No joins across endpoints.** SQL joins two tables in the engine; REST would
  need N+1 calls. Two-endpoint questions are refused with a message saying so,
  rather than answered from one endpoint and silently missing the other.
- **No aggregation the API does not offer.** "Average order value" is computable
  only if the endpoint exposes it or the whole collection fits in the row limit.
  Otherwise it is refused. An average over the first page is a wrong number that
  looks like a right one.
- **No `GROUP BY`.** Same reason.

A refusal that names the reason is a better product than a plausible wrong number —
the query pipeline already works this way, and this keeps that promise.

## 6. Build order

1. `RestAdapter.test_connection` — fetch spec, authenticate, report what it found.
2. Spec parsing → `StructuralSnapshot`. Pure function over a document, so most of
   the risk is coverable by tests against real specs.
3. Scan and describe: unchanged. This is the payoff of the adapter protocol.
4. `generate_request` + validator + executor with paging.
5. The add-source form: spec URL, then auth fields chosen by what the spec declares.

Steps 1–3 make a REST source browsable and described. Step 4 makes it answerable.
They are worth shipping separately.
