SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() IN (N'master', N'model', N'msdb', N'tempdb')
    THROW 51000, N'Refusing to create channel order tables in a system database.', 1;

IF SCHEMA_ID(N'dbo') IS NULL
    THROW 51000, N'Required dbo schema does not exist.', 1;

SELECT
    DB_NAME() AS TargetDatabase,
    CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS SqlServerVersion;
