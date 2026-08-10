SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.ELEVENST_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ELEVENST_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        OrderNo nvarchar(100) NOT NULL,
        OrderProductNo nvarchar(100) NOT NULL,
        ProductId nvarchar(100) NULL,
        OptionId nvarchar(100) NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        OrderAmount decimal(19,4) NULL,
        OrderStatus nvarchar(100) NULL,
        DeliveryStatus nvarchar(100) NULL,
        OrderedAt datetime2(3) NULL,
        PaidAt datetime2(3) NULL,
        DispatchedAt datetime2(3) NULL,
        DeliveryCompanyCode nvarchar(100) NULL,
        TrackingNumber nvarchar(100) NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_ELEVENST_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_ELEVENST_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_ELEVENST_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_ELEVENST_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_ELEVENST_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0)
    );
END;

IF OBJECT_ID(N'dbo.SSG_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SSG_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        OrdNo nvarchar(100) NOT NULL,
        OrdItemSeq nvarchar(100) NOT NULL,
        ShppNo nvarchar(100) NOT NULL,
        ShppSeq nvarchar(100) NOT NULL,
        SiteNo nvarchar(100) NULL,
        ItemId nvarchar(100) NULL,
        UitemId nvarchar(100) NULL,
        SplVenItemId nvarchar(100) NULL,
        USplVenItemId nvarchar(100) NULL,
        ItemName nvarchar(500) NULL,
        UnitItemName nvarchar(500) NULL,
        OrderQuantity int NULL,
        DirectedQuantity int NULL,
        CanceledQuantity int NULL,
        SupplyPrice decimal(19,4) NULL,
        SalesPrice decimal(19,4) NULL,
        RealOrderAmount decimal(19,4) NULL,
        DiscountAmount decimal(19,4) NULL,
        OrderStatusCode nvarchar(100) NULL,
        ShippingStatusCode nvarchar(100) NULL,
        ShippingProgressDetailCode nvarchar(100) NULL,
        OrderReceivedAt datetime2(3) NULL,
        OrderCompletedAt datetime2(3) NULL,
        ScheduledShippingDate date NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_SSG_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_SSG_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_SSG_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_SSG_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_SSG_ORDER_ITEM_Quantities CHECK
        (
            (OrderQuantity IS NULL OR OrderQuantity >= 0)
            AND (DirectedQuantity IS NULL OR DirectedQuantity >= 0)
            AND (CanceledQuantity IS NULL OR CanceledQuantity >= 0)
        )
    );
END;
