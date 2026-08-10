SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;

:r .\sql\channel_orders\005_verify_object_contract.sql
:r .\sql\channel_orders\060_verify_history_constraints.sql

SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedRawJsonConstraints table
(
    TableName sysname NOT NULL PRIMARY KEY,
    ConstraintName sysname NOT NULL
);

INSERT @ExpectedRawJsonConstraints (TableName, ConstraintName)
VALUES
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'CK_NAVER_SMARTSTORE_ORDER_ITEM_RawJson'),
    (N'GODOMALL_ORDER_ITEM', N'CK_GODOMALL_ORDER_ITEM_RawJson'),
    (N'COUPANG_ORDER_ITEM', N'CK_COUPANG_ORDER_ITEM_RawJson'),
    (N'LOTTEON_ORDER_ITEM', N'CK_LOTTEON_ORDER_ITEM_RawJson'),
    (N'ELEVENST_ORDER_ITEM', N'CK_ELEVENST_ORDER_ITEM_RawJson'),
    (N'SSG_ORDER_ITEM', N'CK_SSG_ORDER_ITEM_RawJson'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'CK_TOSS_SHOPPING_ORDER_ITEM_RawJson');

DECLARE @InvalidRawJsonConstraints nvarchar(max);

SELECT @InvalidRawJsonConstraints = STRING_AGG(e.TableName + N'.' + e.ConstraintName, N', ')
FROM @ExpectedRawJsonConstraints AS e
LEFT JOIN sys.check_constraints AS c
    ON c.parent_object_id = OBJECT_ID(N'dbo.' + e.TableName)
   AND c.name = e.ConstraintName
   AND c.is_disabled = 0
   AND c.is_not_trusted = 0
WHERE c.object_id IS NULL;

IF @InvalidRawJsonConstraints IS NOT NULL
BEGIN
    DECLARE @InvalidConstraintMessage nvarchar(2048) =
        N'Missing, disabled, or untrusted RawJson constraints: ' + @InvalidRawJsonConstraints;
    THROW 51004, @InvalidConstraintMessage, 1;
END;

DECLARE @VerificationJson nvarchar(max) =
    N'{"verificationSample":"HMR_SCHEMA_TEST","name":"***","phone":"***","address":"***"}';
DECLARE @VerificationHash binary(32) = HASHBYTES('SHA2_256', @VerificationJson);

BEGIN TRANSACTION;

INSERT dbo.NAVER_SMARTSTORE_ORDER_ITEM
(
    CollectionRunId, CollectedAt, ProductOrderId,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-NAVER-PRODUCT-ORDER',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.GODOMALL_ORDER_ITEM
(
    CollectionRunId, CollectedAt, OrderNo, OrderItemSno,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-GODO-ORDER', N'1',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.COUPANG_ORDER_ITEM
(
    CollectionRunId, CollectedAt, ShipmentBoxId, OrderItemId,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-COUPANG-SHIPMENT', N'TEST-COUPANG-ITEM',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.LOTTEON_ORDER_ITEM
(
    CollectionRunId, CollectedAt, OrderNo, OrderItemSeq,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-LOTTE-ORDER', N'1',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.ELEVENST_ORDER_ITEM
(
    CollectionRunId, CollectedAt, OrderNo, OrderProductNo,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-11ST-ORDER', N'TEST-11ST-PRODUCT',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.SSG_ORDER_ITEM
(
    CollectionRunId, CollectedAt, OrdNo, OrdItemSeq, ShppNo, ShppSeq,
    RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), N'TEST-SSG-ORDER', N'1', N'TEST-SSG-SHIPPING', N'1',
    @VerificationJson, @VerificationHash, 1
);

INSERT dbo.TOSS_SHOPPING_ORDER_ITEM
(
    CollectionRunId, CollectedAt, OrderId, OrderProductId,
    ProductName, OptionName, Quantity, Price, OrderProductStatus,
    RawOrderStatus, RawDeliveryStatus, RawJson, PayloadHash, IsLatest
)
VALUES
(
    NEWID(), SYSUTCDATETIME(), -10001, -20001,
    N'검증용 가상 상품', N'검증용 옵션', 1, 10000, N'DELIVERED',
    N'DELIVERED', N'DELIVERED', @VerificationJson, @VerificationHash, 1
);

DECLARE @InsertedRows int;
DECLARE @DistinctCollectionRuns int;

SELECT
    @InsertedRows = COUNT(*),
    @DistinctCollectionRuns = COUNT(DISTINCT CollectionRunId)
FROM
(
    SELECT CollectionRunId FROM dbo.NAVER_SMARTSTORE_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.GODOMALL_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.COUPANG_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.LOTTEON_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.ELEVENST_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.SSG_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT CollectionRunId FROM dbo.TOSS_SHOPPING_ORDER_ITEM WHERE RawJson = @VerificationJson
) AS VerificationRows;

IF @InsertedRows <> 7 OR @DistinctCollectionRuns <> 7
    THROW 51005, N'Channel order sample insertion verification failed.', 1;

ROLLBACK TRANSACTION;

DECLARE @RowsAfterRollback int;

SELECT @RowsAfterRollback = COUNT(*)
FROM
(
    SELECT StagingId FROM dbo.NAVER_SMARTSTORE_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.GODOMALL_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.COUPANG_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.LOTTEON_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.ELEVENST_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.SSG_ORDER_ITEM WHERE RawJson = @VerificationJson
    UNION ALL
    SELECT StagingId FROM dbo.TOSS_SHOPPING_ORDER_ITEM WHERE RawJson = @VerificationJson
) AS RolledBackRows;

IF @RowsAfterRollback <> 0
    THROW 51006, N'Channel order sample rows remained after rollback.', 1;

SELECT
    N'PASS' AS VerificationResult,
    @InsertedRows AS TestedTableCount,
    @RowsAfterRollback AS RowsRemainingAfterRollback;
