IF OBJECT_ID('dbo.SAP_INVENTORY') IS NOT NULL AND OBJECT_ID('dbo.SAP_INOUT') IS NULL
   AND COL_LENGTH('dbo.SAP_INVENTORY', 'SoCT_NhapXuat') IS NOT NULL
    EXEC sp_rename 'dbo.SAP_INVENTORY', 'SAP_INOUT';

IF OBJECT_ID('dbo.SAP_INVENTORY_Staging') IS NOT NULL AND OBJECT_ID('dbo.SAP_INOUT_Staging') IS NULL
   AND COL_LENGTH('dbo.SAP_INVENTORY_Staging', 'SoCT_NhapXuat') IS NOT NULL
    EXEC sp_rename 'dbo.SAP_INVENTORY_Staging', 'SAP_INOUT_Staging';

IF OBJECT_ID('dbo.SAP_INVENTORY_Load_Log') IS NOT NULL AND OBJECT_ID('dbo.SAP_INOUT_Load_Log') IS NULL
    EXEC sp_rename 'dbo.SAP_INVENTORY_Load_Log', 'SAP_INOUT_Load_Log';

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SAP_INVENTORY_DocDate_NhapXuat' AND object_id = OBJECT_ID('dbo.SAP_INOUT'))
    EXEC sp_rename 'dbo.SAP_INOUT.IX_SAP_INVENTORY_DocDate_NhapXuat', 'IX_SAP_INOUT_DocDate_NhapXuat', 'INDEX';

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SAP_INVENTORY_ItemCode' AND object_id = OBJECT_ID('dbo.SAP_INOUT'))
    EXEC sp_rename 'dbo.SAP_INOUT.IX_SAP_INVENTORY_ItemCode', 'IX_SAP_INOUT_ItemCode', 'INDEX';

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SAP_INVENTORY_Doc' AND object_id = OBJECT_ID('dbo.SAP_INOUT'))
    EXEC sp_rename 'dbo.SAP_INOUT.IX_SAP_INVENTORY_Doc', 'IX_SAP_INOUT_Doc', 'INDEX';

IF OBJECT_ID('dbo.DF_SAP_INVENTORY_Staging_LoadedAt') IS NOT NULL
    EXEC sp_rename 'dbo.DF_SAP_INVENTORY_Staging_LoadedAt', 'DF_SAP_INOUT_Staging_LoadedAt', 'OBJECT';
