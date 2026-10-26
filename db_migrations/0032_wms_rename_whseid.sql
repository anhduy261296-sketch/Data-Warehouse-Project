IF COL_LENGTH('dbo.WMS_INBOUND', '_whseid') IS NOT NULL AND COL_LENGTH('dbo.WMS_INBOUND', 'whseid') IS NULL
    EXEC sp_rename 'dbo.WMS_INBOUND._whseid', 'whseid', 'COLUMN';
IF COL_LENGTH('dbo.WMS_OUTBOUND', '_whseid') IS NOT NULL AND COL_LENGTH('dbo.WMS_OUTBOUND', 'whseid') IS NULL
    EXEC sp_rename 'dbo.WMS_OUTBOUND._whseid', 'whseid', 'COLUMN';
IF COL_LENGTH('dbo.WMS_INVENTORY', '_whseid') IS NOT NULL AND COL_LENGTH('dbo.WMS_INVENTORY', 'whseid') IS NULL
    EXEC sp_rename 'dbo.WMS_INVENTORY._whseid', 'whseid', 'COLUMN';
IF COL_LENGTH('dbo.WMS_INVENTORY_ChangeLog', '_whseid') IS NOT NULL AND COL_LENGTH('dbo.WMS_INVENTORY_ChangeLog', 'whseid') IS NULL
    EXEC sp_rename 'dbo.WMS_INVENTORY_ChangeLog._whseid', 'whseid', 'COLUMN';
