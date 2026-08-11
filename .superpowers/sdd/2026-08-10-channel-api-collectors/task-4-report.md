# Task 4 Report: Godomall, LotteON, and 11st adapters

## Status

Implemented with test-first RED/GREEN coverage. All fixtures are synthetic and masked. No live seller API calls were made and no `.env` file was read.

## Delivered

- NHN Commerce Godomall5 collection through the read-only `Order_Search.php` endpoint with `partner_key` and user `key` form authentication, `orderChannelFl` retention, `lastOrder` continuation, repeated-cursor protection, and repeated-item de-duplication.
- LotteON collection through the read-only `SellerDeliveryOrdersSearch` and `SellerDeliveryProgressStateSearch` endpoints, joined on `odNo` + `odSeq`, with the latest delivery progress retained for each item.
- 11st read-only XML collection for completed, packing, shipping, and delivered order states, namespace-independent parsing, cross-state de-duplication, and exactly one record per `orderProductNo`.
- Mappings limited to the columns already deployed for each channel.
- Canonical masked `RawJson` and SHA-256 payload hashes, including channel-specific masking for abbreviated PII fields not safely recognized by the shared masker.
- Successful empty-result handling and bounded continuation guards.
- Seven masked synthetic XML/JSON fixtures and nine focused tests.

## Official documentation used

- [NHN Commerce Godomall5 Open API specification download](https://devcenter.nhn-commerce.com/godomall5/openapi/specDownload): `Order_Search.php`, POST form authentication, `dateType`, `startDate`, `endDate`, `size`, `lastOrder`, `orderChannelFl`, `apiOrderNo`, `orderGoodsData`, and item `sno`.
- [LotteON Open API service portal](https://api.lotteon.com/apiService/): `SellerDeliveryOrdersSearch` and `SellerDeliveryProgressStateSearch`, bearer/header requirements, `srchStrtDt`/`srchEndDt`, one-day maximum, result lists, and `odNo` + `odSeq` join identity.
- [11st Open API](https://api.11st.co.kr/): the public Seller Office guide redirects to authenticated Seller Office. The documented ordservices URL shape and `openapikey` requirement were corroborated without credentials by the API's XML authentication response; no seller data was requested.

## Verification

- RED: `python -m unittest tests.test_godomall tests.test_lotteon tests.test_elevenst -v` failed because the three channel modules did not exist.
- Focused GREEN: all 9 tests passed.
- Regression RED/GREEN: three added privacy/loop assertions initially failed, then passed after adapter-specific masking and Godomall identity de-duplication were implemented.
- Full suite: all 33 tests passed with `PYTHONPATH=src` in an isolated environment containing the repository's `requests` and `bcrypt` runtime dependencies.

## Mapping decisions and concerns

- The relevant Godomall `Order_Search.php` specification pages document date inputs but do not state a maximum date span. No unsupported cap was invented; a production boundary probe should establish an operational window before scheduling large historical runs.
- LotteON documents a one-day maximum for both selected endpoints, so the adapter rejects wider windows before HTTP. No additional vendor identifier is required for the top-level seller; documented `lrtrNo` is optional and applies to subordinate-trader filtering.
- 11st's detailed seller guide is behind authenticated Seller Office. The read-only ordservices path/header contract was verified from the public endpoint's authentication response, but an exact maximum date span could not be confirmed from current public documentation. The adapter therefore does not guess a limit; a credentialed production dry run should validate state coverage, date boundaries, and response field variants before scheduling.
- 11st duplicates can appear in multiple state feeds. The adapter keeps the first occurrence for an `(orderNo, orderProductNo)` identity during a fetch, following the endpoint order `complete`, `packing`, `shipping`, then `delivered`.

## Fix round 1/5: authoritative state selection and paging failure safety

Addressed both Important review findings.

- 11st now buffers records across all four state feeds and applies the explicit lifecycle precedence `complete < packing < shipping < delivered`. A duplicate from a more advanced feed replaces the earlier payload before any record is emitted.
- Godomall now raises a collection error when `lastOrder` is true but the response cannot provide a new continuation cursor. Missing and repeated cursors can no longer turn a partial fetch into apparent success, while a normal multi-page response still completes.
- Added four synthetic fixtures covering a duplicate 11st item in the complete/delivered feeds, a valid final Godomall page, and a missing-cursor Godomall page.

### RED evidence

Command:

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_godomall tests.test_elevenst -v
```

Result before production changes: 9 tests ran with 3 expected failures. The duplicate 11st item retained `PAYMENT_COMPLETE` instead of `DELIVERY_COMPLETE`, and neither the repeated nor missing Godomall continuation raised an error.

### GREEN evidence

Focused command:

```powershell
$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_godomall tests.test_lotteon tests.test_elevenst -v
```

Result: all 12 focused tests passed in 0.029 seconds.

Full-suite command:

```powershell
$env:UV_CACHE_DIR='C:\Users\user1\Documents\HMR_Agent_Crawling\.tmp_task4_fix1_uv_cache'; $env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; uv run --python 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' --with bcrypt --with requests python -m unittest discover -s tests -v
```

Result: all 36 tests passed in 0.063 seconds.

The original first-occurrence note above is superseded by this fix: cross-state duplicates now retain the payload from the most advanced state feed.
