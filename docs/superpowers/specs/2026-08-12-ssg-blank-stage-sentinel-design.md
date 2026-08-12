# SSG Blank Stage Sentinel Design

## Problem

The SSG shipping-direction API returns one order, but the warehouse-out API represents an empty result as `warehouseOuts: [""]`. The shared stage parser treats every list element as an object, raises `ValueError`, and prevents the valid shipping-direction order from reaching database persistence.

## Design

Normalize blank-string elements in SSG follow-up stage lists as empty-result sentinels. Preserve existing handling for `null`, an empty string, one object, and a list of objects. Continue rejecting nonblank strings and other malformed elements so real response-contract changes remain visible.

The four-API collection flow remains unchanged: shipping directions are collected first, then warehouse-out, non-delivery, and delivery-end data are merged when present. A blank follow-up stage contributes no fields but does not discard the base order.

## Verification and operation

Add a regression test that supplies `[""]` for the warehouse-out response and asserts that the shipping-direction record is still returned. Run the focused SSG test, then the complete test suite. Finally run the SSG collector in database-write mode for the verified 180-day window ending 2026-08-12 and confirm the table row count, latest-row count, and collection timestamp.

## Approved field-source correction

The existing `listWarehouseOut` endpoint is a warehouse-out target list, not a completed-release feed, so it is not a valid source for the deployed completion columns. Remove it from the enrichment flow. For each shipping number returned by the shipping-direction feed, query `listNonDelivery` and `listDeliveryEnd` with quick-search parameters `commType: "02"` and `commValue: <ShppNo>`.

Map official SSG fields without changing the table schema:

- `whoutDt` to `WarehouseOutCompletedAt`
- `delicoVenId` to `DeliveryCompanyCode`
- `wblNo` to `TrackingNumber`
- `shppDt` to `DeliveryCompletedAt`
- `lastShppProgStatDtlCd` to `ShippingProgressDetailCode` and `RawDeliveryStatus`

`DeliveryTrackingStatusAt` remains null because the approved APIs do not document a corresponding timestamp. Blank string list elements from either quick-search response are empty sentinels. Nonblank malformed elements and business failures remain errors.

No other channel adapter or table schema is changed.
