# SSG Blank Stage Sentinel Design

## Problem

The SSG shipping-direction API returns one order, but the warehouse-out API represents an empty result as `warehouseOuts: [""]`. The shared stage parser treats every list element as an object, raises `ValueError`, and prevents the valid shipping-direction order from reaching database persistence.

## Design

Normalize blank-string elements in SSG follow-up stage lists as empty-result sentinels. Preserve existing handling for `null`, an empty string, one object, and a list of objects. Continue rejecting nonblank strings and other malformed elements so real response-contract changes remain visible.

The four-API collection flow remains unchanged: shipping directions are collected first, then warehouse-out, non-delivery, and delivery-end data are merged when present. A blank follow-up stage contributes no fields but does not discard the base order.

## Verification and operation

Add a regression test that supplies `[""]` for the warehouse-out response and asserts that the shipping-direction record is still returned. Run the focused SSG test, then the complete test suite. Finally run the SSG collector in database-write mode for the verified 180-day window ending 2026-08-12 and confirm the table row count, latest-row count, and collection timestamp.

No other channel adapter, table schema, or API request is changed.
