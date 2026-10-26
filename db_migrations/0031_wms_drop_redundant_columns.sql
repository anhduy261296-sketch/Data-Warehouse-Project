IF COL_LENGTH('dbo.WMS_INBOUND', '_storerkey') IS NOT NULL
    EXEC('ALTER TABLE dbo.WMS_INBOUND DROP COLUMN _storerkey');
IF COL_LENGTH('dbo.WMS_OUTBOUND', '_storerkey') IS NOT NULL
    EXEC('ALTER TABLE dbo.WMS_OUTBOUND DROP COLUMN _storerkey');
IF COL_LENGTH('dbo.WMS_INVENTORY', '_storerkey') IS NOT NULL
    EXEC('ALTER TABLE dbo.WMS_INVENTORY DROP COLUMN _storerkey');

IF COL_LENGTH('dbo.WMS_TRANSACTION', '_whseid') IS NOT NULL
BEGIN
    EXEC('UPDATE dbo.WMS_TRANSACTION SET whseid = _whseid WHERE whseid IS NULL OR whseid <> _whseid');
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_TRANSACTION_whse_date' AND object_id = OBJECT_ID('dbo.WMS_TRANSACTION'))
        EXEC('DROP INDEX IX_WMS_TRANSACTION_whse_date ON dbo.WMS_TRANSACTION');
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_TRANSACTION_sku_whse' AND object_id = OBJECT_ID('dbo.WMS_TRANSACTION'))
        EXEC('DROP INDEX IX_WMS_TRANSACTION_sku_whse ON dbo.WMS_TRANSACTION');
    EXEC('ALTER TABLE dbo.WMS_TRANSACTION DROP COLUMN _whseid');
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_TRANSACTION_whse_date' AND object_id = OBJECT_ID('dbo.WMS_TRANSACTION'))
    EXEC('CREATE INDEX IX_WMS_TRANSACTION_whse_date ON dbo.WMS_TRANSACTION (whseid, _txn_date)');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_TRANSACTION_sku_whse' AND object_id = OBJECT_ID('dbo.WMS_TRANSACTION'))
    EXEC('CREATE INDEX IX_WMS_TRANSACTION_sku_whse ON dbo.WMS_TRANSACTION (sku, whseid)
        INCLUDE (trantype, status, tostatus, qty, adddate, sourcetype, sourcekey, fromlpnid, tolpnid, fromloc, toloc)');
