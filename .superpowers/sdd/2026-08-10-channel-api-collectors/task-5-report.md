# Task 5 Report: SSG.COM and Toss Shopping adapters

## Status

Implemented with test-first RED/GREEN coverage. All response fixtures and credentials are synthetic. No live seller API was called and no `.env` file was read.

## Delivered

- SSG.COM collection through the read-only `POST /api/pd/1/listShppDirection.ssg` endpoint with direct `Authorization`, `perdType=02`, and inclusive windows of at most 180 days.
- One SSG record per `(ordNo, ordItemSeq, shppNo, shppSeq)`, mapped only to the columns already deployed for `dbo.SSG_ORDER_ITEM`.
- Toss Shopping OAuth2 client-credentials acquisition with the documented `toss-shopping-fep:write` scope, in-memory token reuse, and proactive renewal before expiry.
- Toss Shopping order collection through read-only `GET /api/v3/shopping-fep/orders/v2`, inclusive windows of at most 31 days, `limit=50`, and `success.nextCursor` continuation until `null`.
- Business-failure rejection for SSG `resultCode != 00` and Toss `resultType != SUCCESS`, including HTTP 200 failure envelopes.
- Repeated Toss cursor detection that raises instead of returning an apparently successful partial collection.
- Channel-specific recursive masking for every customer, receiver, address, postal-code, customer-note, member-ID, and customs field documented by the selected endpoints before canonical `RawJson` serialization and hashing.
- Exact mappings limited to the deployed SSG and Toss table columns.
- Two synthetic JSON fixtures and nine focused tests.

## Official documentation used

- [SSG.COM Shipping Instructed List Search API](https://eapi.ssgadm.com/info/shpp/listShppDirection.ssg): POST path/version, direct `Authorization`, JSON support, `perdType=02`, 180-day maximum, success/result envelope, four-part row identity, response fields, and documented private fields.
- [Toss Shopping OAuth2 authentication](https://shopping-docs.toss.im/dev/api-2/auth): client-credentials token URL, form fields, fixed scope, bearer token, and `expires_in`.
- [Toss Shopping order API](https://shopping-docs.toss.im/dev/api-2/order): read-only v2 order URL, bearer authentication, 31-day maximum, `limit` maximum 50, `nextCursor` behavior, HTTP-200 success/failure envelopes, order fields, and documented private fields.

## Verification

- Initial RED: `python -m unittest tests.test_ssg tests.test_toss -v` failed with `ModuleNotFoundError` for both new adapter modules.
- Token-lifetime regression RED: a valid 20-second token initially raised `Toss Shopping token lifetime was too short`; the test passed after using a bounded half-life refresh margin for lifetimes shorter than 60 seconds.
- Focused GREEN: all 9 SSG/Toss tests passed.
- Bare-runtime full suite: 40 tests passed and the pre-existing Naver test module could not import because that runtime lacked `bcrypt`.
- Dependency-complete full suite: all 45 tests passed in 0.082 seconds using isolated `requests` and `bcrypt` dependencies.
- `git diff --check`: passed.

## Mapping decisions and concerns

- The current public SSG field table declares `perdStrDts` and `perdEndDts` as `Date` but does not expose a literal format in the rendered field description. The adapter sends ISO calendar dates (`YYYY-MM-DD`), consistent with the API's established request examples. Task 6's credentialed dry run should verify this serialization before database writes.
- SSG's JSON list notation is not explicit about whether `shppDirection` is wrapped per list element. The parser accepts both the documented wrapper shape and direct row objects while rejecting malformed rows.
- Toss access tokens are cached only in memory and are never serialized. The adapter refreshes at least 30 seconds before normal expiry, or halfway through unusually short valid lifetimes.
- No live boundary probe, customer response, token, or seller credential was used in Task 5. Production access and response variants remain for the explicitly planned Task 6 dry run.
