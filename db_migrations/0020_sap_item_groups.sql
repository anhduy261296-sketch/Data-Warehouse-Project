IF OBJECT_ID('dbo.SAP_ITEM_GROUPS', 'U') IS NULL
    CREATE TABLE dbo.SAP_ITEM_GROUPS (
        ItmsGrpCod NVARCHAR(20) NOT NULL PRIMARY KEY,
        ItmsGrpNam NVARCHAR(200) NULL,
        LoadedAt DATETIME2 NOT NULL CONSTRAINT DF_SAP_ITEM_GROUPS_LoadedAt DEFAULT SYSUTCDATETIME()
    );

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_INVENTORY_sku' AND object_id = OBJECT_ID('dbo.WMS_INVENTORY'))
    CREATE INDEX IX_WMS_INVENTORY_sku ON dbo.WMS_INVENTORY (sku) INCLUDE (_whseid, status, qty, qtyavailable, qtyallocated, qtypicked, uom, description);
