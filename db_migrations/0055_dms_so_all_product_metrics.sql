IF COL_LENGTH('dbo.DMS_SO_ALL', 'sku_count') IS NULL
    ALTER TABLE dbo.DMS_SO_ALL ADD sku_count INT NULL;

IF COL_LENGTH('dbo.DMS_SO_ALL', 'quantity_total') IS NULL
    ALTER TABLE dbo.DMS_SO_ALL ADD quantity_total DECIMAL(28,6) NULL;
