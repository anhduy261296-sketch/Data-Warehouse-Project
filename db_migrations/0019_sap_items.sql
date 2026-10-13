IF OBJECT_ID('dbo.SAP_ITEMS', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.SAP_ITEMS (
        ItemCode NVARCHAR(50) NOT NULL PRIMARY KEY,
        ItemName NVARCHAR(500) NULL,
        ItemForeignName NVARCHAR(500) NULL,
        InvName NVARCHAR(500) NULL,
        Barcode NVARCHAR(100) NULL,
        Color NVARCHAR(100) NULL,
        ItemGroup1 NVARCHAR(50) NULL,
        ItemGroup2 NVARCHAR(50) NULL,
        ItemGroup3 NVARCHAR(50) NULL,
        ItemGroup4 NVARCHAR(50) NULL,
        Brand NVARCHAR(50) NULL,
        Model NVARCHAR(50) NULL,
        ProCode NVARCHAR(200) NULL,
        PgiCode NVARCHAR(200) NULL,
        ItemSpec NVARCHAR(500) NULL,
        Producer NVARCHAR(200) NULL,
        Country NVARCHAR(100) NULL,
        UomGroup NVARCHAR(50) NULL,
        Uom NVARCHAR(50) NULL,
        SaleUom NVARCHAR(50) NULL,
        BatchNumber NVARCHAR(10) NULL,
        SerialNumber NVARCHAR(10) NULL,
        SalTaxGroup NVARCHAR(20) NULL,
        WarrantyDuration NVARCHAR(20) NULL,
        WarrantyDuration2 NVARCHAR(20) NULL,
        IsActive NVARCHAR(10) NULL,
        InventoryItem NVARCHAR(10) NULL,
        OutsideLength DECIMAL(18, 4) NULL,
        OutsideWidth DECIMAL(18, 4) NULL,
        OutsideHeight DECIMAL(18, 4) NULL,
        OutsideWeight DECIMAL(18, 4) NULL,
        InsideLength DECIMAL(18, 4) NULL,
        InsideWidth DECIMAL(18, 4) NULL,
        InsideHeight DECIMAL(18, 4) NULL,
        InsideWeight DECIMAL(18, 4) NULL,
        Size NVARCHAR(MAX) NULL,
        FirstLoadedAt DATETIME2 NOT NULL CONSTRAINT DF_SAP_ITEMS_FirstLoadedAt DEFAULT SYSUTCDATETIME(),
        LoadedAt DATETIME2 NOT NULL CONSTRAINT DF_SAP_ITEMS_LoadedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_SAP_ITEMS_Group ON dbo.SAP_ITEMS (ItemGroup1, ItemGroup2);
    CREATE INDEX IX_SAP_ITEMS_Brand ON dbo.SAP_ITEMS (Brand);
END

IF OBJECT_ID('dbo.SAP_ITEMS_Load_Log', 'U') IS NULL
    CREATE TABLE dbo.SAP_ITEMS_Load_Log (
        id INT IDENTITY(1, 1) PRIMARY KEY,
        from_date NVARCHAR(30) NOT NULL,
        to_date NVARCHAR(30) NOT NULL,
        row_count INT NOT NULL,
        inserted INT NOT NULL,
        updated INT NOT NULL,
        status NVARCHAR(20) NOT NULL,
        message NVARCHAR(1000) NULL,
        loaded_at DATETIME2 NOT NULL CONSTRAINT DF_SAP_ITEMS_Load_Log_loaded_at DEFAULT SYSUTCDATETIME()
    );
