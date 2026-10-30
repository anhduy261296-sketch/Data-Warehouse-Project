IF OBJECT_ID('dbo.ZnsTemplates', 'U') IS NULL
    CREATE TABLE dbo.ZnsTemplates (
        Id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsTemplates PRIMARY KEY,
        Name NVARCHAR(200) NOT NULL,
        ZnsCode NVARCHAR(50) NOT NULL,
        Owner VARCHAR(10) NOT NULL CONSTRAINT CK_ZnsTemplates_Owner CHECK (Owner IN ('PGI', 'AWG')),
        Content NVARCHAR(MAX) NOT NULL,
        DataTable SYSNAME NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_ZnsTemplates_IsActive DEFAULT 1,
        CreatedBy NVARCHAR(150) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsTemplates_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedBy NVARCHAR(150) NULL,
        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsTemplates_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_ZnsTemplates_Owner_Code UNIQUE (Owner, ZnsCode)
    );

IF OBJECT_ID('dbo.ZnsTemplateVariables', 'U') IS NULL
    CREATE TABLE dbo.ZnsTemplateVariables (
        Id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsTemplateVariables PRIMARY KEY,
        TemplateId INT NOT NULL CONSTRAINT FK_ZnsTemplateVariables_Template REFERENCES dbo.ZnsTemplates (Id),
        Name VARCHAR(50) NOT NULL,
        Label NVARCHAR(200) NULL,
        DataType VARCHAR(10) NOT NULL CONSTRAINT CK_ZnsTemplateVariables_Type CHECK (DataType IN ('text', 'number', 'date', 'datetime')),
        Source VARCHAR(10) NOT NULL CONSTRAINT CK_ZnsTemplateVariables_Source CHECK (Source IN ('customer', 'fixed')),
        IsRequired BIT NOT NULL CONSTRAINT DF_ZnsTemplateVariables_IsRequired DEFAULT 0,
        DefaultValue NVARCHAR(500) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_ZnsTemplateVariables_IsActive DEFAULT 1,
        SortOrder INT NOT NULL CONSTRAINT DF_ZnsTemplateVariables_SortOrder DEFAULT 0,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsTemplateVariables_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsTemplateVariables_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_ZnsTemplateVariables_Name UNIQUE (TemplateId, Name)
    );

IF OBJECT_ID('dbo.ZnsTemplateChangeLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ZnsTemplateChangeLog (
        Id BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsTemplateChangeLog PRIMARY KEY,
        TemplateId INT NOT NULL CONSTRAINT FK_ZnsTemplateChangeLog_Template REFERENCES dbo.ZnsTemplates (Id),
        VariableName VARCHAR(50) NULL,
        Action VARCHAR(30) NOT NULL,
        Detail NVARCHAR(1000) NULL,
        ChangedBy NVARCHAR(150) NULL,
        ChangedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsTemplateChangeLog_ChangedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ZnsTemplateChangeLog_Template ON dbo.ZnsTemplateChangeLog (TemplateId, ChangedAt);
END

IF OBJECT_ID('dbo.ZnsSendBatches', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ZnsSendBatches (
        Id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsSendBatches PRIMARY KEY,
        TemplateId INT NULL CONSTRAINT FK_ZnsSendBatches_Template REFERENCES dbo.ZnsTemplates (Id),
        Owner VARCHAR(10) NULL,
        FileName NVARCHAR(255) NOT NULL,
        RawData NVARCHAR(MAX) NULL,
        ColumnMapping NVARCHAR(MAX) NULL,
        FixedValues NVARCHAR(MAX) NULL,
        TotalRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_TotalRows DEFAULT 0,
        ValidRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_ValidRows DEFAULT 0,
        InvalidRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_InvalidRows DEFAULT 0,
        Status VARCHAR(20) NOT NULL CONSTRAINT CK_ZnsSendBatches_Status CHECK (Status IN ('draft', 'pending', 'sending', 'done', 'cancelled')),
        CreatedBy NVARCHAR(150) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsSendBatches_CreatedAt DEFAULT SYSUTCDATETIME(),
        ConfirmedBy NVARCHAR(150) NULL,
        ConfirmedAt DATETIME2 NULL,
        CancelledBy NVARCHAR(150) NULL,
        CancelledAt DATETIME2 NULL
    );
    CREATE INDEX IX_ZnsSendBatches_Status ON dbo.ZnsSendBatches (Status, CreatedAt);
END

IF OBJECT_ID('dbo.ZnsSendRecipients', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ZnsSendRecipients (
        Id BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsSendRecipients PRIMARY KEY,
        BatchId INT NOT NULL CONSTRAINT FK_ZnsSendRecipients_Batch REFERENCES dbo.ZnsSendBatches (Id),
        RowNo INT NOT NULL,
        Phone VARCHAR(20) NULL,
        CustomerName NVARCHAR(200) NULL,
        Content NVARCHAR(MAX) NULL,
        Status VARCHAR(20) NOT NULL CONSTRAINT CK_ZnsSendRecipients_Status CHECK (Status IN ('pending', 'invalid', 'sent', 'failed', 'cancelled')),
        ErrorMessage NVARCHAR(1000) NULL,
        ZaloMsgId NVARCHAR(100) NULL,
        SentAt DATETIME2 NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsSendRecipients_CreatedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ZnsSendRecipients_Batch ON dbo.ZnsSendRecipients (BatchId, Status);
END

IF COL_LENGTH('dbo.ZnsTemplateVariables', 'DefaultValue') IS NULL
    EXEC('ALTER TABLE dbo.ZnsTemplateVariables ADD DefaultValue NVARCHAR(500) NULL');
