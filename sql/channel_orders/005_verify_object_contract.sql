SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedTables table
(
    TableName sysname NOT NULL PRIMARY KEY
);

INSERT @ExpectedTables (TableName)
VALUES
    (N'NAVER_SMARTSTORE_ORDER_ITEM'),
    (N'GODOMALL_ORDER_ITEM'),
    (N'COUPANG_ORDER_ITEM'),
    (N'LOTTEON_ORDER_ITEM'),
    (N'ELEVENST_ORDER_ITEM'),
    (N'SSG_ORDER_ITEM'),
    (N'TOSS_SHOPPING_ORDER_ITEM');

DECLARE @MissingTables nvarchar(max);

SELECT @MissingTables = STRING_AGG(e.TableName, N', ')
FROM @ExpectedTables AS e
WHERE OBJECT_ID(N'dbo.' + e.TableName, N'U') IS NULL;

IF @MissingTables IS NOT NULL
BEGIN
    DECLARE @MissingTableMessage nvarchar(2048) =
        N'Missing channel order tables: ' + @MissingTables;
    THROW 51001, @MissingTableMessage, 1;
END;

DECLARE @ExpectedColumns table
(
    TableName sysname NOT NULL,
    ColumnName sysname NOT NULL,
    CONSTRAINT PK_ExpectedColumns PRIMARY KEY (TableName, ColumnName)
);

INSERT @ExpectedColumns (TableName, ColumnName)
SELECT e.TableName, c.ColumnName
FROM @ExpectedTables AS e
CROSS JOIN
(
    VALUES
        (N'StagingId'),
        (N'CollectionRunId'),
        (N'CollectedAt'),
        (N'RawJson'),
        (N'PayloadHash'),
        (N'IsLatest'),
        (N'CreatedAt')
) AS c (ColumnName);

INSERT @ExpectedColumns (TableName, ColumnName)
VALUES
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'ProductOrderId'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'OrderId'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'ProductId'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'OptionId'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'ProductName'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'OptionName'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'Quantity'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'UnitPrice'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'TotalPaymentAmount'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'ProductOrderStatus'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'ClaimStatus'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryStatus'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'PaymentAt'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'DispatchAt'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryCompletedAt'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'TrackingNumber'),
    (N'GODOMALL_ORDER_ITEM', N'OrderNo'),
    (N'GODOMALL_ORDER_ITEM', N'OrderItemSno'),
    (N'GODOMALL_ORDER_ITEM', N'OrderChannelCode'),
    (N'GODOMALL_ORDER_ITEM', N'ExternalOrderNo'),
    (N'GODOMALL_ORDER_ITEM', N'ProductCode'),
    (N'GODOMALL_ORDER_ITEM', N'OptionCode'),
    (N'GODOMALL_ORDER_ITEM', N'ProductName'),
    (N'GODOMALL_ORDER_ITEM', N'OptionName'),
    (N'GODOMALL_ORDER_ITEM', N'Quantity'),
    (N'GODOMALL_ORDER_ITEM', N'UnitPrice'),
    (N'GODOMALL_ORDER_ITEM', N'PaymentAmount'),
    (N'GODOMALL_ORDER_ITEM', N'DiscountAmount'),
    (N'GODOMALL_ORDER_ITEM', N'DeliveryFee'),
    (N'GODOMALL_ORDER_ITEM', N'OrderStatus'),
    (N'GODOMALL_ORDER_ITEM', N'PaymentStatus'),
    (N'GODOMALL_ORDER_ITEM', N'DeliveryStatus'),
    (N'GODOMALL_ORDER_ITEM', N'OrderedAt'),
    (N'GODOMALL_ORDER_ITEM', N'PaidAt'),
    (N'GODOMALL_ORDER_ITEM', N'DispatchedAt'),
    (N'GODOMALL_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'GODOMALL_ORDER_ITEM', N'TrackingNumber');

DECLARE @MissingColumns nvarchar(max);

SELECT @MissingColumns = STRING_AGG(e.TableName + N'.' + e.ColumnName, N', ')
FROM @ExpectedColumns AS e
WHERE COL_LENGTH(N'dbo.' + e.TableName, e.ColumnName) IS NULL;

IF @MissingColumns IS NOT NULL
BEGIN
    DECLARE @MissingColumnMessage nvarchar(2048) =
        N'Missing channel order columns: ' + @MissingColumns;
    THROW 51002, @MissingColumnMessage, 1;
END;

SELECT
    N'PASS' AS VerificationResult,
    COUNT_BIG(*) AS VerifiedTableCount
FROM @ExpectedTables;
