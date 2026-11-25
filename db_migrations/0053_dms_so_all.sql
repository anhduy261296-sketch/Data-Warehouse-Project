IF OBJECT_ID('dbo.DMS_SO_ALL', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DMS_SO_ALL (
        _row_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        model NVARCHAR(100) NULL,
        document_id INT NOT NULL,
        document_type NVARCHAR(200) NULL,
        document_code NVARCHAR(200) NULL,
        order_type NVARCHAR(100) NULL,
        document_date DATETIME2(6) NULL,
        created_at DATETIME2(6) NULL,
        state_code NVARCHAR(100) NULL,
        state NVARCHAR(200) NULL,
        partner_code NVARCHAR(200) NULL,
        partner_name NVARCHAR(MAX) NULL,
        source_warehouse_code NVARCHAR(100) NULL,
        source_warehouse NVARCHAR(MAX) NULL,
        destination_warehouse_code NVARCHAR(100) NULL,
        destination_warehouse NVARCHAR(MAX) NULL,
        salesperson NVARCHAR(MAX) NULL,
        amount_total DECIMAL(28,6) NULL,
        currency NVARCHAR(100) NULL,
        oms_count BIGINT NULL,
        oms_codes NVARCHAR(MAX) NULL,
        oms_states NVARCHAR(MAX) NULL,
        company NVARCHAR(MAX) NULL
    );
END;

IF OBJECT_ID('dbo.DMS_SO_ALL_Load_Log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DMS_SO_ALL_Load_Log (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        start_at DATETIME2(6) NOT NULL,
        end_at DATETIME2(6) NOT NULL,
        row_count INT NOT NULL,
        status VARCHAR(20) NOT NULL,
        loaded_at DATETIME2(6) NOT NULL
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.DMS_SO_ALL') AND name = 'IX_DMS_SO_ALL_DocumentDate'
)
    CREATE INDEX IX_DMS_SO_ALL_DocumentDate ON dbo.DMS_SO_ALL(document_date DESC)
    INCLUDE (document_type, order_type, state_code, amount_total);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.DMS_SO_ALL') AND name = 'IX_DMS_SO_ALL_DocumentCode'
)
    CREATE INDEX IX_DMS_SO_ALL_DocumentCode ON dbo.DMS_SO_ALL(document_code);
