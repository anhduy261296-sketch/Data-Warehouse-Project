
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_outbound_type') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_outbound_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
    EXEC('DROP INDEX IX_OMS_ORDERS_outbound_created ON dbo.OMS_ORDERS');
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_order_number') IS NOT NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _k_order_number');
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_outbound_type') IS NOT NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _k_outbound_type');

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length = -1)
   AND NOT EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE LEN(order_number) > 100)
    EXEC('ALTER TABLE dbo.OMS_ORDERS ALTER COLUMN order_number NVARCHAR(100) NULL');

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'outbound_order_type' AND max_length = -1)
   AND NOT EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE LEN(outbound_order_type) > 20)
    EXEC('ALTER TABLE dbo.OMS_ORDERS ALTER COLUMN outbound_order_type NVARCHAR(20) NULL');

IF COL_LENGTH('dbo.OMS_ORDERS', '_k_created_at') IS NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS ADD _k_created_at AS TRY_CONVERT(DATETIME2, created_date, 126) PERSISTED');

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_outbound_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'outbound_order_type' AND max_length <> -1)
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length <> -1)
    EXEC('CREATE INDEX IX_OMS_ORDERS_outbound_created ON dbo.OMS_ORDERS (outbound_order_type, _k_created_at) INCLUDE (order_number)');

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_order_number' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length <> -1)
    EXEC('CREATE INDEX IX_OMS_ORDERS_order_number ON dbo.OMS_ORDERS (order_number)');

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
    EXEC('CREATE INDEX IX_OMS_ORDERS_created ON dbo.OMS_ORDERS (_k_created_at)');

DECLARE @whseid_has_data BIT = 1;
IF COL_LENGTH('dbo.OMS_ORDERS', '_whseid') IS NOT NULL
    EXEC sp_executesql N'SELECT @h = CASE WHEN EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE _whseid IS NOT NULL) THEN 1 ELSE 0 END',
                       N'@h BIT OUTPUT', @h = @whseid_has_data OUTPUT;
IF COL_LENGTH('dbo.OMS_ORDERS', '_whseid') IS NOT NULL AND @whseid_has_data = 0
BEGIN
    DECLARE @df SYSNAME = (SELECT dc.name FROM sys.default_constraints dc
                           JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
                           WHERE dc.parent_object_id = OBJECT_ID('dbo.OMS_ORDERS') AND c.name = '_whseid');
    IF @df IS NOT NULL EXEC('ALTER TABLE dbo.OMS_ORDERS DROP CONSTRAINT ' + @df);
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _whseid');
END
