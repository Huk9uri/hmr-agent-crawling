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
    (N'GODOMALL_ORDER_ITEM', N'TrackingNumber'),
    (N'COUPANG_ORDER_ITEM', N'ShipmentBoxId'),
    (N'COUPANG_ORDER_ITEM', N'OrderId'),
    (N'COUPANG_ORDER_ITEM', N'OrderItemId'),
    (N'COUPANG_ORDER_ITEM', N'VendorItemId'),
    (N'COUPANG_ORDER_ITEM', N'SellerProductId'),
    (N'COUPANG_ORDER_ITEM', N'SellerProductItemId'),
    (N'COUPANG_ORDER_ITEM', N'ProductName'),
    (N'COUPANG_ORDER_ITEM', N'OptionName'),
    (N'COUPANG_ORDER_ITEM', N'Quantity'),
    (N'COUPANG_ORDER_ITEM', N'CanceledQuantity'),
    (N'COUPANG_ORDER_ITEM', N'SalesPrice'),
    (N'COUPANG_ORDER_ITEM', N'OrderStatus'),
    (N'COUPANG_ORDER_ITEM', N'DeliveryStatus'),
    (N'COUPANG_ORDER_ITEM', N'OrderedAt'),
    (N'COUPANG_ORDER_ITEM', N'PaidAt'),
    (N'COUPANG_ORDER_ITEM', N'EstimatedShippingAt'),
    (N'COUPANG_ORDER_ITEM', N'DispatchedAt'),
    (N'COUPANG_ORDER_ITEM', N'DeliveryCompletedAt'),
    (N'COUPANG_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'COUPANG_ORDER_ITEM', N'TrackingNumber'),
    (N'LOTTEON_ORDER_ITEM', N'OrderNo'),
    (N'LOTTEON_ORDER_ITEM', N'OrderItemSeq'),
    (N'LOTTEON_ORDER_ITEM', N'ProductId'),
    (N'LOTTEON_ORDER_ITEM', N'OptionId'),
    (N'LOTTEON_ORDER_ITEM', N'ProductName'),
    (N'LOTTEON_ORDER_ITEM', N'OptionName'),
    (N'LOTTEON_ORDER_ITEM', N'Quantity'),
    (N'LOTTEON_ORDER_ITEM', N'CanceledQuantity'),
    (N'LOTTEON_ORDER_ITEM', N'SalesAmount'),
    (N'LOTTEON_ORDER_ITEM', N'PaymentAmount'),
    (N'LOTTEON_ORDER_ITEM', N'OrderStatus'),
    (N'LOTTEON_ORDER_ITEM', N'DeliveryStatus'),
    (N'LOTTEON_ORDER_ITEM', N'OrderedAt'),
    (N'LOTTEON_ORDER_ITEM', N'PaidAt'),
    (N'LOTTEON_ORDER_ITEM', N'DispatchedAt'),
    (N'LOTTEON_ORDER_ITEM', N'DeliveryCompletedAt'),
    (N'LOTTEON_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'LOTTEON_ORDER_ITEM', N'TrackingNumber'),
    (N'ELEVENST_ORDER_ITEM', N'OrderNo'),
    (N'ELEVENST_ORDER_ITEM', N'OrderProductNo'),
    (N'ELEVENST_ORDER_ITEM', N'ProductId'),
    (N'ELEVENST_ORDER_ITEM', N'OptionId'),
    (N'ELEVENST_ORDER_ITEM', N'ProductName'),
    (N'ELEVENST_ORDER_ITEM', N'OptionName'),
    (N'ELEVENST_ORDER_ITEM', N'Quantity'),
    (N'ELEVENST_ORDER_ITEM', N'OrderAmount'),
    (N'ELEVENST_ORDER_ITEM', N'OrderStatus'),
    (N'ELEVENST_ORDER_ITEM', N'DeliveryStatus'),
    (N'ELEVENST_ORDER_ITEM', N'OrderedAt'),
    (N'ELEVENST_ORDER_ITEM', N'PaidAt'),
    (N'ELEVENST_ORDER_ITEM', N'DispatchedAt'),
    (N'ELEVENST_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'ELEVENST_ORDER_ITEM', N'TrackingNumber'),
    (N'SSG_ORDER_ITEM', N'OrdNo'),
    (N'SSG_ORDER_ITEM', N'OrdItemSeq'),
    (N'SSG_ORDER_ITEM', N'ShppNo'),
    (N'SSG_ORDER_ITEM', N'ShppSeq'),
    (N'SSG_ORDER_ITEM', N'SiteNo'),
    (N'SSG_ORDER_ITEM', N'ItemId'),
    (N'SSG_ORDER_ITEM', N'UitemId'),
    (N'SSG_ORDER_ITEM', N'SplVenItemId'),
    (N'SSG_ORDER_ITEM', N'USplVenItemId'),
    (N'SSG_ORDER_ITEM', N'ItemName'),
    (N'SSG_ORDER_ITEM', N'UnitItemName'),
    (N'SSG_ORDER_ITEM', N'OrderQuantity'),
    (N'SSG_ORDER_ITEM', N'DirectedQuantity'),
    (N'SSG_ORDER_ITEM', N'CanceledQuantity'),
    (N'SSG_ORDER_ITEM', N'SupplyPrice'),
    (N'SSG_ORDER_ITEM', N'SalesPrice'),
    (N'SSG_ORDER_ITEM', N'RealOrderAmount'),
    (N'SSG_ORDER_ITEM', N'DiscountAmount'),
    (N'SSG_ORDER_ITEM', N'OrderStatusCode'),
    (N'SSG_ORDER_ITEM', N'ShippingStatusCode'),
    (N'SSG_ORDER_ITEM', N'ShippingProgressDetailCode'),
    (N'SSG_ORDER_ITEM', N'OrderReceivedAt'),
    (N'SSG_ORDER_ITEM', N'OrderCompletedAt'),
    (N'SSG_ORDER_ITEM', N'ScheduledShippingDate'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OrderId'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OrderProductId'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ProductId'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'StockId'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ProductName'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OptionName'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'Quantity'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'Price'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OriginPrice'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'TotalDiscountPrice'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'TossShoppingDiscount'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'TossPayDiscount'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'TossPayPoint'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OrderProductStatus'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'OrderedAt'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'CanceledAt'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ConfirmedAt'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ShippingDeadlineAt'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'DeliveryCompanyCode'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ShippingTrackingNumber'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'DeliveryFeeGroupId'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'DeliveryFee'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'DeliveryLocationType'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'NormalDeliveryFee'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'JejuDeliveryFee'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'MountainDeliveryFee'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ProductManagementCode'),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'ProductItemManagementCode');

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
