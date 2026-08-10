SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.TOSS_SHOPPING_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TOSS_SHOPPING_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        OrderId bigint NOT NULL,
        OrderProductId bigint NOT NULL,
        ProductId bigint NULL,
        StockId bigint NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        Price bigint NULL,
        OriginPrice bigint NULL,
        TotalDiscountPrice bigint NULL,
        TossShoppingDiscount bigint NULL,
        TossPayDiscount bigint NULL,
        TossPayPoint bigint NULL,
        OrderProductStatus nvarchar(100) NULL,
        OrderedAt datetime2(3) NULL,
        CanceledAt datetime2(3) NULL,
        ConfirmedAt datetime2(3) NULL,
        ShippingDeadlineAt datetime2(3) NULL,
        DeliveryCompanyCode nvarchar(100) NULL,
        ShippingTrackingNumber nvarchar(100) NULL,
        DeliveryFeeGroupId bigint NULL,
        DeliveryFee bigint NULL,
        DeliveryLocationType nvarchar(100) NULL,
        NormalDeliveryFee bigint NULL,
        JejuDeliveryFee bigint NULL,
        MountainDeliveryFee bigint NULL,
        ProductManagementCode nvarchar(100) NULL,
        ProductItemManagementCode nvarchar(100) NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_TOSS_SHOPPING_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_TOSS_SHOPPING_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_TOSS_SHOPPING_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_TOSS_SHOPPING_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_TOSS_SHOPPING_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0)
    );
END;
