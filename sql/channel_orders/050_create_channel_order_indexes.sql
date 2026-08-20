SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @IndexDefinitions table
(
    IndexName sysname NOT NULL PRIMARY KEY,
    TableName sysname NOT NULL,
    IsUnique bit NOT NULL,
    KeyColumns nvarchar(1000) NOT NULL,
    IncludeColumns nvarchar(1000) NULL,
    FilterPredicate nvarchar(1000) NULL
);

INSERT @IndexDefinitions
    (IndexName, TableName, IsUnique, KeyColumns, IncludeColumns, FilterPredicate)
VALUES
    (N'IX_NAVER_SMARTSTORE_ORDER_ITEM_CollectionRunId', N'NAVER_SMARTSTORE_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_NAVER_SMARTSTORE_ORDER_ITEM_Identity_CollectedAt', N'NAVER_SMARTSTORE_ORDER_ITEM', 0, N'ProductOrderId, CollectedAt DESC', N'OrderId, ProductOrderStatus, DeliveryStatus', NULL),
    (N'IX_NAVER_SMARTSTORE_ORDER_ITEM_Identity_PayloadHash', N'NAVER_SMARTSTORE_ORDER_ITEM', 0, N'ProductOrderId, PayloadHash', NULL, NULL),
    (N'UX_NAVER_SMARTSTORE_ORDER_ITEM_Latest', N'NAVER_SMARTSTORE_ORDER_ITEM', 1, N'ProductOrderId', NULL, N'IsLatest = 1'),

    (N'IX_GODOMALL_ORDER_ITEM_CollectionRunId', N'GODOMALL_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_GODOMALL_ORDER_ITEM_Identity_CollectedAt', N'GODOMALL_ORDER_ITEM', 0, N'OrderNo, OrderItemSno, CollectedAt DESC', N'OrderChannelCode, OrderStatus, DeliveryStatus', NULL),
    (N'IX_GODOMALL_ORDER_ITEM_Identity_PayloadHash', N'GODOMALL_ORDER_ITEM', 0, N'OrderNo, OrderItemSno, PayloadHash', NULL, NULL),
    (N'UX_GODOMALL_ORDER_ITEM_Latest', N'GODOMALL_ORDER_ITEM', 1, N'OrderNo, OrderItemSno', NULL, N'IsLatest = 1'),

    (N'IX_COUPANG_ORDER_ITEM_CollectionRunId', N'COUPANG_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_COUPANG_ORDER_ITEM_Identity_CollectedAt', N'COUPANG_ORDER_ITEM', 0, N'ShipmentBoxId, OrderItemId, CollectedAt DESC', N'OrderId, OrderStatus, DeliveryStatus', NULL),
    (N'IX_COUPANG_ORDER_ITEM_Identity_PayloadHash', N'COUPANG_ORDER_ITEM', 0, N'ShipmentBoxId, OrderItemId, PayloadHash', NULL, NULL),
    (N'UX_COUPANG_ORDER_ITEM_Latest', N'COUPANG_ORDER_ITEM', 1, N'ShipmentBoxId, OrderItemId', NULL, N'IsLatest = 1'),

    (N'IX_LOTTEON_ORDER_ITEM_CollectionRunId', N'LOTTEON_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_LOTTEON_ORDER_ITEM_Identity_CollectedAt', N'LOTTEON_ORDER_ITEM', 0, N'OrderNo, OrderItemSeq, CollectedAt DESC', N'OrderStatus, DeliveryStatus', NULL),
    (N'IX_LOTTEON_ORDER_ITEM_Identity_PayloadHash', N'LOTTEON_ORDER_ITEM', 0, N'OrderNo, OrderItemSeq, PayloadHash', NULL, NULL),
    (N'UX_LOTTEON_ORDER_ITEM_Latest', N'LOTTEON_ORDER_ITEM', 1, N'OrderNo, OrderItemSeq', NULL, N'IsLatest = 1'),

    (N'IX_ELEVENST_ORDER_ITEM_CollectionRunId', N'ELEVENST_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_ELEVENST_ORDER_ITEM_Identity_CollectedAt', N'ELEVENST_ORDER_ITEM', 0, N'OrderNo, OrderProductNo, CollectedAt DESC', N'OrderStatus, DeliveryStatus', NULL),
    (N'IX_ELEVENST_ORDER_ITEM_Identity_PayloadHash', N'ELEVENST_ORDER_ITEM', 0, N'OrderNo, OrderProductNo, PayloadHash', NULL, NULL),
    (N'UX_ELEVENST_ORDER_ITEM_Latest', N'ELEVENST_ORDER_ITEM', 1, N'OrderNo, OrderProductNo', NULL, N'IsLatest = 1'),

    (N'IX_SSG_ORDER_ITEM_CollectionRunId', N'SSG_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_SSG_ORDER_ITEM_Identity_CollectedAt', N'SSG_ORDER_ITEM', 0, N'OrdNo, OrdItemSeq, ShppNo, ShppSeq, CollectedAt DESC', N'OrderStatusCode, ShippingStatusCode, ShippingProgressDetailCode', NULL),
    (N'IX_SSG_ORDER_ITEM_Identity_PayloadHash', N'SSG_ORDER_ITEM', 0, N'OrdNo, OrdItemSeq, ShppNo, ShppSeq, PayloadHash', NULL, NULL),
    (N'UX_SSG_ORDER_ITEM_Latest', N'SSG_ORDER_ITEM', 1, N'OrdNo, OrdItemSeq, ShppNo, ShppSeq', NULL, N'IsLatest = 1'),

    (N'IX_CJ_ONSTYLE_ORDER_ITEM_CollectionRunId', N'CJ_ONSTYLE_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_CJ_ONSTYLE_ORDER_ITEM_Identity_CollectedAt', N'CJ_ONSTYLE_ORDER_ITEM', 0, N'OrderNo, OrderItemSequence, OrderDetailSequence, OrderProcessingSequence, CollectedAt DESC', N'DeliveryStatus, TrackingNumber', NULL),
    (N'IX_CJ_ONSTYLE_ORDER_ITEM_Identity_PayloadHash', N'CJ_ONSTYLE_ORDER_ITEM', 0, N'OrderNo, OrderItemSequence, OrderDetailSequence, OrderProcessingSequence, PayloadHash', NULL, NULL),
    (N'UX_CJ_ONSTYLE_ORDER_ITEM_Latest', N'CJ_ONSTYLE_ORDER_ITEM', 1, N'OrderNo, OrderItemSequence, OrderDetailSequence, OrderProcessingSequence', NULL, N'IsLatest = 1'),

    (N'IX_TOSS_SHOPPING_ORDER_ITEM_CollectionRunId', N'TOSS_SHOPPING_ORDER_ITEM', 0, N'CollectionRunId', NULL, NULL),
    (N'IX_TOSS_SHOPPING_ORDER_ITEM_Identity_CollectedAt', N'TOSS_SHOPPING_ORDER_ITEM', 0, N'OrderProductId, CollectedAt DESC', N'OrderId, OrderProductStatus, DeliveryCompanyCode, ShippingTrackingNumber', NULL),
    (N'IX_TOSS_SHOPPING_ORDER_ITEM_Identity_PayloadHash', N'TOSS_SHOPPING_ORDER_ITEM', 0, N'OrderProductId, PayloadHash', NULL, NULL),
    (N'UX_TOSS_SHOPPING_ORDER_ITEM_Latest', N'TOSS_SHOPPING_ORDER_ITEM', 1, N'OrderProductId', NULL, N'IsLatest = 1');

DECLARE
    @IndexName sysname,
    @TableName sysname,
    @IsUnique bit,
    @KeyColumns nvarchar(1000),
    @IncludeColumns nvarchar(1000),
    @FilterPredicate nvarchar(1000),
    @Sql nvarchar(max);

DECLARE IndexCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT IndexName, TableName, IsUnique, KeyColumns, IncludeColumns, FilterPredicate
FROM @IndexDefinitions
ORDER BY TableName, IndexName;

OPEN IndexCursor;
FETCH NEXT FROM IndexCursor
INTO @IndexName, @TableName, @IsUnique, @KeyColumns, @IncludeColumns, @FilterPredicate;

WHILE @@FETCH_STATUS = 0
BEGIN
    IF OBJECT_ID(N'dbo.' + @TableName, N'U') IS NULL
    BEGIN
        CLOSE IndexCursor;
        DEALLOCATE IndexCursor;
        DECLARE @MissingTableMessage nvarchar(2048) =
            N'Cannot create index because table is missing: dbo.' + @TableName;
        THROW 51004, @MissingTableMessage, 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.' + @TableName)
          AND name = @IndexName
    )
    BEGIN
        SET @Sql = N'CREATE '
            + CASE WHEN @IsUnique = 1 THEN N'UNIQUE ' ELSE N'' END
            + N'NONCLUSTERED INDEX ' + QUOTENAME(@IndexName)
            + N' ON dbo.' + QUOTENAME(@TableName)
            + N' (' + @KeyColumns + N')'
            + CASE WHEN @IncludeColumns IS NOT NULL
                THEN N' INCLUDE (' + @IncludeColumns + N')' ELSE N'' END
            + CASE WHEN @FilterPredicate IS NOT NULL
                THEN N' WHERE ' + @FilterPredicate ELSE N'' END
            + N';';

        EXEC sys.sp_executesql @Sql;
    END;

    FETCH NEXT FROM IndexCursor
    INTO @IndexName, @TableName, @IsUnique, @KeyColumns, @IncludeColumns, @FilterPredicate;
END;

CLOSE IndexCursor;
DEALLOCATE IndexCursor;
