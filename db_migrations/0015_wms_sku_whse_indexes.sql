IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_INBOUND_sku_whseid' AND object_id = OBJECT_ID('dbo.WMS_INBOUND'))
    CREATE INDEX IX_WMS_INBOUND_sku_whseid ON dbo.WMS_INBOUND (sku, _whseid);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_OUTBOUND_sku_whseid' AND object_id = OBJECT_ID('dbo.WMS_OUTBOUND'))
    CREATE INDEX IX_WMS_OUTBOUND_sku_whseid ON dbo.WMS_OUTBOUND (sku, _whseid);
