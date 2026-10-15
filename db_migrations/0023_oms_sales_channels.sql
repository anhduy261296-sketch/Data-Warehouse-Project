IF OBJECT_ID('dbo.OMS_SALES_CHANNELS', 'U') IS NULL
    CREATE TABLE dbo.OMS_SALES_CHANNELS (
        code NVARCHAR(50) NOT NULL PRIMARY KEY,
        display_name NVARCHAR(200) NULL,
        description NVARCHAR(500) NULL,
        operation NVARCHAR(20) NULL,
        status NVARCHAR(50) NULL,
        priority_order INT NULL,
        oms_id NVARCHAR(100) NULL,
        created_date NVARCHAR(50) NULL,
        updated_date NVARCHAR(50) NULL,
        loaded_at DATETIME2 NOT NULL CONSTRAINT DF_OMS_SALES_CHANNELS_loaded_at DEFAULT SYSUTCDATETIME()
    );
