SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedIndexes table
(
    TableName sysname NOT NULL,
    IndexName sysname NOT NULL,
    MustBeUnique bit NOT NULL,
    MustBeFiltered bit NOT NULL,
    PRIMARY KEY (TableName, IndexName)
);

INSERT @ExpectedIndexes (TableName, IndexName, MustBeUnique, MustBeFiltered)
VALUES
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'IX_NAVER_SMARTSTORE_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'IX_NAVER_SMARTSTORE_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'IX_NAVER_SMARTSTORE_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'NAVER_SMARTSTORE_ORDER_ITEM', N'UX_NAVER_SMARTSTORE_ORDER_ITEM_Latest', 1, 1),
    (N'GODOMALL_ORDER_ITEM', N'IX_GODOMALL_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'GODOMALL_ORDER_ITEM', N'IX_GODOMALL_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'GODOMALL_ORDER_ITEM', N'IX_GODOMALL_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'GODOMALL_ORDER_ITEM', N'UX_GODOMALL_ORDER_ITEM_Latest', 1, 1),
    (N'COUPANG_ORDER_ITEM', N'IX_COUPANG_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'COUPANG_ORDER_ITEM', N'IX_COUPANG_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'COUPANG_ORDER_ITEM', N'IX_COUPANG_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'COUPANG_ORDER_ITEM', N'UX_COUPANG_ORDER_ITEM_Latest', 1, 1),
    (N'LOTTEON_ORDER_ITEM', N'IX_LOTTEON_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'LOTTEON_ORDER_ITEM', N'IX_LOTTEON_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'LOTTEON_ORDER_ITEM', N'IX_LOTTEON_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'LOTTEON_ORDER_ITEM', N'UX_LOTTEON_ORDER_ITEM_Latest', 1, 1),
    (N'ELEVENST_ORDER_ITEM', N'IX_ELEVENST_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'ELEVENST_ORDER_ITEM', N'IX_ELEVENST_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'ELEVENST_ORDER_ITEM', N'IX_ELEVENST_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'ELEVENST_ORDER_ITEM', N'UX_ELEVENST_ORDER_ITEM_Latest', 1, 1),
    (N'SSG_ORDER_ITEM', N'IX_SSG_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'SSG_ORDER_ITEM', N'IX_SSG_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'SSG_ORDER_ITEM', N'IX_SSG_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'SSG_ORDER_ITEM', N'UX_SSG_ORDER_ITEM_Latest', 1, 1),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'IX_TOSS_SHOPPING_ORDER_ITEM_CollectionRunId', 0, 0),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'IX_TOSS_SHOPPING_ORDER_ITEM_Identity_CollectedAt', 0, 0),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'IX_TOSS_SHOPPING_ORDER_ITEM_Identity_PayloadHash', 0, 0),
    (N'TOSS_SHOPPING_ORDER_ITEM', N'UX_TOSS_SHOPPING_ORDER_ITEM_Latest', 1, 1);

DECLARE @MissingIndexes nvarchar(max);

SELECT @MissingIndexes = STRING_AGG(e.TableName + N'.' + e.IndexName, N', ')
FROM @ExpectedIndexes AS e
LEFT JOIN sys.indexes AS i
    ON i.object_id = OBJECT_ID(N'dbo.' + e.TableName)
   AND i.name = e.IndexName
   AND i.is_unique = e.MustBeUnique
   AND CASE WHEN i.filter_definition IS NULL THEN 0 ELSE 1 END = e.MustBeFiltered
WHERE i.index_id IS NULL;

IF @MissingIndexes IS NOT NULL
BEGIN
    DECLARE @MissingIndexMessage nvarchar(2048) =
        N'Missing or invalid channel order indexes: ' + @MissingIndexes;
    THROW 51003, @MissingIndexMessage, 1;
END;

SELECT N'PASS' AS VerificationResult, COUNT_BIG(*) AS VerifiedIndexCount
FROM @ExpectedIndexes;
