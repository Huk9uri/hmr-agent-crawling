SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.COUPANG_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.COUPANG_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        ShipmentBoxId nvarchar(100) NOT NULL,
        OrderId nvarchar(100) NULL,
        OrderItemId nvarchar(100) NOT NULL,
        VendorItemId nvarchar(100) NULL,
        SellerProductId nvarchar(100) NULL,
        SellerProductItemId nvarchar(100) NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        CanceledQuantity int NULL,
        SalesPrice decimal(19,4) NULL,
        OrderStatus nvarchar(100) NULL,
        DeliveryStatus nvarchar(100) NULL,
        OrderedAt datetime2(3) NULL,
        PaidAt datetime2(3) NULL,
        EstimatedShippingAt datetime2(3) NULL,
        DispatchedAt datetime2(3) NULL,
        DeliveryCompletedAt datetime2(3) NULL,
        DeliveryCompanyCode nvarchar(100) NULL,
        TrackingNumber nvarchar(100) NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_COUPANG_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_COUPANG_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_COUPANG_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_COUPANG_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_COUPANG_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0),
        CONSTRAINT CK_COUPANG_ORDER_ITEM_CanceledQuantity CHECK (CanceledQuantity IS NULL OR CanceledQuantity >= 0)
    );
END;

IF OBJECT_ID(N'dbo.LOTTEON_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LOTTEON_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        OrderNo nvarchar(100) NOT NULL,
        OrderItemSeq nvarchar(100) NOT NULL,
        ProductId nvarchar(100) NULL,
        OptionId nvarchar(100) NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        CanceledQuantity int NULL,
        SalesAmount decimal(19,4) NULL,
        PaymentAmount decimal(19,4) NULL,
        OrderStatus nvarchar(100) NULL,
        DeliveryStatus nvarchar(100) NULL,
        OrderedAt datetime2(3) NULL,
        PaidAt datetime2(3) NULL,
        DispatchedAt datetime2(3) NULL,
        DeliveryCompletedAt datetime2(3) NULL,
        DeliveryCompanyCode nvarchar(100) NULL,
        TrackingNumber nvarchar(100) NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_LOTTEON_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_LOTTEON_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_LOTTEON_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_LOTTEON_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_LOTTEON_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0),
        CONSTRAINT CK_LOTTEON_ORDER_ITEM_CanceledQuantity CHECK (CanceledQuantity IS NULL OR CanceledQuantity >= 0)
    );
END;
