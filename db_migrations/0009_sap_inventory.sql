IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SAP_INVENTORY')
BEGIN
    CREATE TABLE dbo.SAP_INVENTORY (
        LoaiCT NVARCHAR(52) NULL,
        TenLoaiCT NVARCHAR(100) NULL,
        SoCT NVARCHAR(40) NULL,
        DocDate DATETIME2(0) NULL,
        SlpName NVARCHAR(155) NULL,
        BoPhan NVARCHAR(30) NULL,
        CreatedBy NVARCHAR(155) NULL,
        SoCT_NhapXuat NVARCHAR(50) NULL,
        DocDate_NhapXuat DATETIME2(0) NULL,
        DocType INT NULL,
        DocEntry INT NULL,
        DocLineNum INT NULL,
        BaseType INT NULL,
        BaseEntry INT NULL,
        BaseLine INT NULL,
        IN_WhsCode NVARCHAR(8) NULL,
        IN_WhsName NVARCHAR(100) NULL,
        IN_BinCode NVARCHAR(228) NULL,
        OUT_WhsCode NVARCHAR(8) NULL,
        OUT_WhsName NVARCHAR(100) NULL,
        OUT_BinCode NVARCHAR(228) NULL,
        U_ItemProducer NVARCHAR(50) NULL,
        NSX NVARCHAR(100) NULL,
        ItmsGrpCod SMALLINT NULL,
        ItmsGrpNam NVARCHAR(100) NULL,
        ItemCode NVARCHAR(50) NULL,
        U_PGICode NVARCHAR(50) NULL,
        ItemName NVARCHAR(200) NULL,
        InvntryUom NVARCHAR(100) NULL,
        DistNumber NVARCHAR(50) NULL,
        InStock DECIMAL(28,6) NULL,
        Cost DECIMAL(38,18) NULL,
        TransValue DECIMAL(28,6) NULL,
        Comments NVARCHAR(254) NULL,
        CardCode NVARCHAR(15) NULL,
        CardName NVARCHAR(200) NULL,
        U_IMNo NVARCHAR(50) NULL,
        LoadedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_SAP_INVENTORY_DocDate_NhapXuat ON dbo.SAP_INVENTORY (DocDate_NhapXuat);
    CREATE INDEX IX_SAP_INVENTORY_ItemCode ON dbo.SAP_INVENTORY (ItemCode);
    CREATE INDEX IX_SAP_INVENTORY_Doc ON dbo.SAP_INVENTORY (DocType, DocEntry, DocLineNum);
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SAP_INVENTORY_Staging')
    SELECT TOP 0 * INTO dbo.SAP_INVENTORY_Staging FROM dbo.SAP_INVENTORY;

IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = 'DF_SAP_INVENTORY_Staging_LoadedAt')
    ALTER TABLE dbo.SAP_INVENTORY_Staging ADD CONSTRAINT DF_SAP_INVENTORY_Staging_LoadedAt DEFAULT SYSUTCDATETIME() FOR LoadedAt;

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SAP_INVENTORY_Load_Log')
BEGIN
    CREATE TABLE dbo.SAP_INVENTORY_Load_Log (
        id INT IDENTITY(1,1) PRIMARY KEY,
        start_at VARCHAR(10) NOT NULL,
        end_at VARCHAR(10) NOT NULL,
        row_count INT NOT NULL,
        status VARCHAR(20) NOT NULL,
        message NVARCHAR(1000) NULL,
        loaded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
