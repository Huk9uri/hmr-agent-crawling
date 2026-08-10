# Task 3 Report: Naver SmartStore and Coupang adapters

## Status

Implemented with test-first RED/GREEN coverage. No live API calls were made and no `.env` file was read.

## Delivered

- Naver Commerce OAuth2 SELF token acquisition using `bcrypt(client_id + "_" + timestamp, client_secret)` followed by standard Base64.
- Naver changed-order collection in one-day/24-hour slices, `moreFrom` + `moreSequence` continuation, repeated-pair guard, ID de-duplication, and detail requests in batches of at most 300.
- Coupang CEA HMAC-SHA256 authorization over signed date + method + path + encoded query.
- Coupang collection across `ACCEPT`, `INSTRUCT`, `DEPARTURE`, `DELIVERING`, `FINAL_DELIVERY`, and `NONE_TRACKING`, with inclusive windows capped at 31 days, `maxPerPage=50`, `nextToken` paging, and a repeated-token guard per status.
- Exact mappings limited to deployed `NAVER_SMARTSTORE_ORDER_ITEM` and `COUPANG_ORDER_ITEM` business columns.
- Per-item canonical masked JSON and SHA-256 payload hashes. Coupang's documented PII-bearing `orderer`, `receiver`, and overseas-customs structures are replaced wholesale before serialization.
- Four masked synthetic JSON fixtures and nine focused tests.

## Official documentation used

- Naver Commerce API current 2.84.0 (2026-08-05): authentication, token request, changed product-order status query, and product-order detail query.
- Coupang Developer Center current pages: HMAC signature creation and PO list query (paging by day).

## Verification

- RED: `python -m unittest tests.test_naver tests.test_coupang -v` failed because `channels.naver` and `channels.coupang` did not exist.
- Focused GREEN: 9 tests, all passed.
- Full suite: 23 tests, all passed with `PYTHONPATH=src` in an isolated Python 3.12 environment containing `requests` and `bcrypt`.

## Mapping decisions and concerns

- The current Coupang PO response documents `orderItems.sequenceNo`, but not fields literally named `orderItemId` or `sellerProductItemId`. `OrderItemId` is therefore mapped from `sequenceNo`, the documented per-shipment line identifier; `SellerProductItemId` remains `NULL` rather than inventing a value.
- Coupang exposes one PO `status` in this response, not a separate delivery-status field. It is retained in both normalized/raw order and delivery status columns so the deployed schema remains queryable without fabricating a second status.
- Naver `OptionId` maps from documented `itemNo` (the automatically generated unique option/add-on item number), not seller-entered `optionManageCode`.
- Runtime installation must include `bcrypt` in addition to the existing `requests` dependency.
