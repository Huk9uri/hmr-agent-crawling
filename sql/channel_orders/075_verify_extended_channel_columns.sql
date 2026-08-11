SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @Expected table
(
    TableName sysname NOT NULL,
    ColumnName sysname NOT NULL,
    DataType nvarchar(128) NOT NULL,
    PRIMARY KEY (TableName, ColumnName)
);

INSERT @Expected (TableName, ColumnName, DataType)
VALUES
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'OrderDate', N'datetime2'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'PaymentMeans', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'PayLocationType', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'OrderDiscountAmount', N'decimal'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'GeneralPaymentAmount', N'decimal'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'OptionManageCode', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryFeeAmount', N'decimal'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'SectionDeliveryFee', N'decimal'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'ShippingDueDate', N'datetime2'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'PlaceOrderDate', N'datetime2'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'PlaceOrderStatus', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'ExpectedDeliveryMethod', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryAttributeType', N'nvarchar'),
(N'NAVER_SMARTSTORE_ORDER_ITEM', N'DeliveryMethod', N'nvarchar');

DECLARE @Problems nvarchar(max);

SELECT @Problems = STRING_AGG(
    expected.TableName + N'.' + expected.ColumnName + N' expected ' + expected.DataType,
    N', '
)
FROM @Expected expected
LEFT JOIN INFORMATION_SCHEMA.COLUMNS actual
  ON actual.TABLE_SCHEMA = N'dbo'
 AND actual.TABLE_NAME = expected.TableName
 AND actual.COLUMN_NAME = expected.ColumnName
WHERE actual.COLUMN_NAME IS NULL
   OR actual.DATA_TYPE <> expected.DataType;

IF @Problems IS NOT NULL
BEGIN
    DECLARE @Message nvarchar(2048) = N'Extended channel column contract failed: ' + @Problems;
    THROW 51012, @Message, 1;
END;
