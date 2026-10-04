# 75API IMAGE Response Contract Closure

## Scope

This phase closes the response contract for the 75API GPT-image-2 transport. The documented Feishu example returns a top-level `url`; the adapter now also supports the explicit OpenAI-compatible paths `data[].url` and `data[].b64_json`.

## Previous run closure

`20261004T102258Z` is closed as `CLOSED_PROVIDER_RESPONSE_CONTRACT_MISMATCH`. The request completed in about 40.106 seconds with `timeout_layer = NONE`; the provider returned JSON, but the adapter could not resolve image media. The raw response body was not recoverable and was not reconstructed.

## Zero-call contract

- URL media: supported through explicit allowlisted paths.
- Base64 media: decoded only from explicit media fields; durable evidence stores type, length, SHA-256 and MIME type.
- Signed URLs: only scheme, host, path SHA-256 and query presence are retained.
- HTTP 200 logical errors, missing media and unknown schemas are distinct.
- No recursive arbitrary URL/base64 extraction.

The fixture and extractor tests passed before the fresh canary. No image, video, judge or provider call is made by the fixture tests.

## Fresh canary

The dedicated canary allows one real IMAGE call for Lin Wan MASTER only. Derived views, Lu Shu, HANDBAG, Vision Judge and VIDEO remain disabled.

## Result

- Final status: `75API_IMAGE_RESPONSE_CONTRACT_PROVEN`
- Run: `20261004T105249Z`
- Real IMAGE calls: `1`
- HTTP status: `200`
- Elapsed: `111.969s`
- Response shape: top-level `model`, `url`
- Matched media path: `url`
- Media type: `image/png`
- Media SHA-256: `fb16b58520681d04460467ede564ab44232c629dff128cadaad2eb5e18853c1b`
- Generation execution: `c880b07f4c0c`
- Lin Wan MASTER: `READY`
- Derived calls: `0`; Vision Judge calls: `0`; VIDEO calls: `0`
- Safety: raw base64 `0`; signed URL query `0`; secret leaks `0`; production writes `0`; Book 990400 writes `0`; orphans `0`

## Tests

- Contract and related provider regression suite: `142 passed`.
- `compileall` and `git diff --check`: passed.
- The repository-wide suite completed with `2072 passed, 24 failed`; the failures are in existing migration/model-registry and unrelated production fixture expectations, while the new response-contract suite remained green.
