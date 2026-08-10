SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.NAVER_SMARTSTORE_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.NAVER_SMARTSTORE_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        ProductOrderId nvarchar(100) NOT NULL,
        OrderId nvarchar(100) NULL,
        ProductId nvarchar(100) NULL,
        OptionId nvarchar(100) NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        UnitPrice decimal(19,4) NULL,
        TotalPaymentAmount decimal(19,4) NULL,
        ProductOrderStatus nvarchar(100) NULL,
        ClaimStatus nvarchar(100) NULL,
        DeliveryStatus nvarchar(100) NULL,
        PaymentAt datetime2(3) NULL,
        DispatchAt datetime2(3) NULL,
        DeliveryCompletedAt datetime2(3) NULL,
        DeliveryCompanyCode nvarchar(100) NULL,
        TrackingNumber nvarchar(100) NULL,
        RawOrderStatus nvarchar(100) NULL,
        RawDeliveryStatus nvarchar(100) NULL,
        RawJson nvarchar(max) NOT NULL,
        PayloadHash binary(32) NOT NULL,
        IsLatest bit NOT NULL CONSTRAINT DF_NAVER_SMARTSTORE_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_NAVER_SMARTSTORE_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_NAVER_SMARTSTORE_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_NAVER_SMARTSTORE_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_NAVER_SMARTSTORE_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0)
    );
END;

IF OBJECT_ID(N'dbo.GODOMALL_ORDER_ITEM', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.GODOMALL_ORDER_ITEM
    (
        StagingId bigint IDENTITY(1,1) NOT NULL,
        CollectionRunId uniqueidentifier NOT NULL,
        CollectedAt datetime2(3) NOT NULL,
        SourceCreatedAt datetime2(3) NULL,
        SourceModifiedAt datetime2(3) NULL,
        OrderNo nvarchar(100) NOT NULL,
        OrderItemSno nvarchar(100) NOT NULL,
        OrderChannelCode nvarchar(100) NULL,
        ExternalOrderNo nvarchar(100) NULL,
        ProductCode nvarchar(100) NULL,
        OptionCode nvarchar(100) NULL,
        ProductName nvarchar(500) NULL,
        OptionName nvarchar(500) NULL,
        Quantity int NULL,
        UnitPrice decimal(19,4) NULL,
        PaymentAmount decimal(19,4) NULL,
        DiscountAmount decimal(19,4) NULL,
        DeliveryFee decimal(19,4) NULL,
        OrderStatus nvarchar(100) NULL,
        PaymentStatus nvarchar(100) NULL,
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
        IsLatest bit NOT NULL CONSTRAINT DF_GODOMALL_ORDER_ITEM_IsLatest DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL CONSTRAINT DF_GODOMALL_ORDER_ITEM_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_GODOMALL_ORDER_ITEM PRIMARY KEY CLUSTERED (StagingId),
        CONSTRAINT CK_GODOMALL_ORDER_ITEM_RawJson CHECK (ISJSON(RawJson) = 1),
        CONSTRAINT CK_GODOMALL_ORDER_ITEM_Quantity CHECK (Quantity IS NULL OR Quantity >= 0)
    );
END;
