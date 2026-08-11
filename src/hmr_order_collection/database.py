"""Safe SQL Server history persistence for masked channel order records."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from hmr_order_collection.config import AppConfig, ConfigurationError
from hmr_order_collection.models import ChannelRecord


@dataclass(frozen=True)
class TableDefinition:
    """Static, deployed SQL identifiers for one channel history table."""

    table: str
    identity_columns: tuple[str, ...]
    columns: tuple[str, ...]


@dataclass(frozen=True)
class WriteSummary:
    """Counts of rows committed by one channel write transaction."""

    inserted: int = 0
    changed: int = 0
    skipped: int = 0


TABLES: dict[str, TableDefinition] = {
    "naver": TableDefinition(
        "NAVER_SMARTSTORE_ORDER_ITEM",
        ("ProductOrderId",),
        ("ProductOrderId", "OrderId", "ProductId", "OptionId", "ProductName", "OptionName", "Quantity", "UnitPrice", "TotalPaymentAmount", "ProductOrderStatus", "ClaimStatus", "DeliveryStatus", "OrderDate", "PaymentAt", "PaymentMeans", "PayLocationType", "OrderDiscountAmount", "GeneralPaymentAmount", "OptionManageCode", "DeliveryFeeAmount", "SectionDeliveryFee", "ShippingDueDate", "PlaceOrderDate", "PlaceOrderStatus", "ExpectedDeliveryMethod", "DeliveryAttributeType", "DeliveryMethod", "DispatchAt", "DeliveryCompletedAt", "DeliveryCompanyCode", "TrackingNumber", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "godomall": TableDefinition(
        "GODOMALL_ORDER_ITEM",
        ("OrderNo", "OrderItemSno"),
        ("OrderNo", "OrderItemSno", "OrderChannelCode", "ExternalOrderNo", "OrderTypeCode", "SettlementMethodCode", "ProductCode", "OptionCode", "ProductName", "OptionName", "Quantity", "UnitPrice", "OptionPrice", "AdditionalGoodsPrice", "GoodsDiscountAmount", "CouponGoodsDiscountAmount", "PaymentAmount", "TotalGoodsPrice", "OrderDiscountAmount", "MemberDiscountAmount", "CouponOrderDiscountAmount", "UsedMileageAmount", "UsedDepositAmount", "DiscountAmount", "DeliveryFee", "OrderStatus", "PaymentStatus", "DeliveryStatus", "OrderedAt", "PaidAt", "DispatchedAt", "DeliveryCompanyCode", "TrackingNumber", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "coupang": TableDefinition(
        "COUPANG_ORDER_ITEM",
        ("ShipmentBoxId", "OrderItemId"),
        ("ShipmentBoxId", "OrderId", "OrderItemId", "VendorItemId", "SellerProductId", "SellerProductItemId", "ProductId", "VendorItemPackageId", "VendorItemPackageName", "VendorItemName", "ProductName", "OptionName", "Quantity", "CanceledQuantity", "HeldCancellationQuantity", "SalesPrice", "SalesPriceCurrencyCode", "OrderStatus", "DeliveryStatus", "OrderedAt", "PaidAt", "EstimatedShippingAt", "DispatchedAt", "DeliveryCompletedAt", "DeliveryCompanyCode", "TrackingNumber", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "lotteon": TableDefinition(
        "LOTTEON_ORDER_ITEM",
        ("OrderNo", "OrderItemSeq"),
        ("OrderNo", "OrderItemSeq", "ProductId", "OptionId", "ProductName", "OptionName", "Quantity", "CanceledQuantity", "SalesAmount", "PaymentAmount", "OrderStatus", "DeliveryStatus", "OrderedAt", "PaidAt", "DispatchedAt", "DeliveryCompletedAt", "DeliveryCompanyCode", "TrackingNumber", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "elevenst": TableDefinition(
        "ELEVENST_ORDER_ITEM",
        ("OrderNo", "OrderProductNo"),
        ("OrderNo", "OrderProductNo", "ProductId", "OptionId", "ProductName", "OptionName", "Quantity", "OrderAmount", "OrderStatus", "DeliveryStatus", "OrderedAt", "PaidAt", "DispatchedAt", "DeliveryCompanyCode", "TrackingNumber", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "ssg": TableDefinition(
        "SSG_ORDER_ITEM",
        ("OrdNo", "OrdItemSeq", "ShppNo", "ShppSeq"),
        ("OrdNo", "OrdItemSeq", "ShppNo", "ShppSeq", "SiteNo", "ItemId", "UitemId", "SplVenItemId", "USplVenItemId", "ItemName", "UnitItemName", "OrderQuantity", "DirectedQuantity", "CanceledQuantity", "SupplyPrice", "SalesPrice", "RealOrderAmount", "DiscountAmount", "OrderStatusCode", "ShippingStatusCode", "ShippingProgressDetailCode", "OrderReceivedAt", "OrderCompletedAt", "ScheduledShippingDate", "RawOrderStatus", "RawDeliveryStatus"),
    ),
    "toss": TableDefinition(
        "TOSS_SHOPPING_ORDER_ITEM",
        ("OrderProductId",),
        ("OrderId", "OrderProductId", "ProductId", "StockId", "ProductName", "OptionName", "Quantity", "Price", "OriginPrice", "TotalDiscountPrice", "TossShoppingDiscount", "TossPayDiscount", "TossPayPoint", "OrderProductStatus", "OrderedAt", "CanceledAt", "ConfirmedAt", "ShippingDeadlineAt", "DeliveryCompanyCode", "ShippingTrackingNumber", "DeliveryFeeGroupId", "DeliveryFee", "DeliveryLocationType", "NormalDeliveryFee", "JejuDeliveryFee", "MountainDeliveryFee", "ProductManagementCode", "ProductItemManagementCode", "RawOrderStatus", "RawDeliveryStatus"),
    ),
}

_SESSION_OPTIONS = (
    "SET ANSI_NULLS ON",
    "SET ANSI_PADDING ON",
    "SET ANSI_WARNINGS ON",
    "SET ARITHABORT ON",
    "SET CONCAT_NULL_YIELDS_NULL ON",
    "SET QUOTED_IDENTIFIER ON",
    "SET NUMERIC_ROUNDABORT OFF",
    "SET XACT_ABORT ON",
)


def connect_from_config(
    config: AppConfig,
    *,
    connector: Callable[..., Any] | None = None,
) -> Any:
    """Open SQL Server using only strict config values, never command arguments."""
    if connector is None:
        import pymssql

        connector = pymssql.connect

    raw_port = config.get("DB_PORT", "1433")
    try:
        port = int(raw_port) if raw_port is not None else 1433
    except (TypeError, ValueError) as error:
        raise ConfigurationError("DB_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("DB_PORT must be between 1 and 65535")

    return connector(
        server=config.require("DB_SERVER"),
        database=config.require("DB_NAME"),
        user=config.require("DB_USER"),
        password=config.require("DB_PASSWORD"),
        port=port,
        login_timeout=10,
        timeout=60,
    )


class DatabaseWriter:
    """Append changed channel records while preserving one locked latest row."""

    def __init__(self, connection: Any, *, now: Callable[[], datetime] | None = None) -> None:
        self._connection = connection
        self._now = now or (lambda: datetime.now(timezone.utc))

    def write(self, channel: str, records: Iterable[ChannelRecord], run_id: UUID) -> WriteSummary:
        definition = self._definition_for(channel)
        validated_records = tuple(records)
        for record in validated_records:
            self._validate_record(definition, record)
        if not validated_records:
            return WriteSummary()

        cursor = self._connection.cursor()
        inserted = changed = skipped = 0
        try:
            for statement in _SESSION_OPTIONS:
                cursor.execute(statement)
            collected_at = self._utc_now()
            for record in validated_records:
                latest_hash = self._locked_latest_hash(cursor, definition, record.identity)
                if latest_hash == record.payload_hash:
                    skipped += 1
                    continue
                if latest_hash is not None:
                    self._clear_latest(cursor, definition, record.identity)
                    changed += 1
                self._insert(cursor, definition, record, run_id, collected_at)
                inserted += 1
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()
        return WriteSummary(inserted=inserted, changed=changed, skipped=skipped)

    @staticmethod
    def _definition_for(channel: str) -> TableDefinition:
        try:
            return TABLES[channel]
        except KeyError as error:
            raise ValueError(f"Unsupported channel: {channel}") from error

    @staticmethod
    def _validate_record(definition: TableDefinition, record: ChannelRecord) -> None:
        if len(record.identity) != len(definition.identity_columns):
            raise ValueError(f"{definition.table} identity must contain {len(definition.identity_columns)} values")
        unknown_columns = set(record.columns).difference(definition.columns)
        if unknown_columns:
            raise ValueError(f"Unsupported columns for {definition.table}: {sorted(unknown_columns)!r}")
        for column, identity_value in zip(definition.identity_columns, record.identity, strict=True):
            supplied_value = record.columns.get(column, identity_value)
            if supplied_value != identity_value:
                raise ValueError(f"{column} must match the record identity")
        if len(record.payload_hash) != 32:
            raise ValueError("payload_hash must be exactly 32 bytes")

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("now() must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _locked_latest_hash(cursor: Any, definition: TableDefinition, identity: Sequence[Any]) -> bytes | None:
        where = " AND ".join(f"[{column}] = %s" for column in definition.identity_columns)
        cursor.execute(
            f"SELECT PayloadHash FROM dbo.[{definition.table}] WITH (UPDLOCK, HOLDLOCK) "
            f"WHERE {where} AND IsLatest = 1",
            tuple(identity),
        )
        row = cursor.fetchone()
        return None if row is None else row[0]

    @staticmethod
    def _clear_latest(cursor: Any, definition: TableDefinition, identity: Sequence[Any]) -> None:
        where = " AND ".join(f"[{column}] = %s" for column in definition.identity_columns)
        cursor.execute(f"UPDATE dbo.[{definition.table}] SET IsLatest = 0 WHERE {where} AND IsLatest = 1", tuple(identity))

    @staticmethod
    def _insert(cursor: Any, definition: TableDefinition, record: ChannelRecord, run_id: UUID, collected_at: datetime) -> None:
        insert_columns = ("CollectionRunId", "CollectedAt", *definition.columns, "RawJson", "PayloadHash", "IsLatest")
        values = (
            run_id,
            collected_at,
            *(record.columns.get(column, record.identity[definition.identity_columns.index(column)]) if column in definition.identity_columns else record.columns.get(column) for column in definition.columns),
            record.raw_json,
            record.payload_hash,
            True,
        )
        quoted_columns = ", ".join(f"[{column}]" for column in insert_columns)
        placeholders = ", ".join("%s" for _ in insert_columns)
        cursor.execute(f"INSERT INTO dbo.[{definition.table}] ({quoted_columns}) VALUES ({placeholders})", values)
