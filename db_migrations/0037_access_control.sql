-- Duyệt lô gửi trước khi gửi, hạn mức theo chủ hàng, nhật ký thao tác.
-- Vai trò và quyền dùng auth_group / auth_permission của Django (lệnh sync_access tạo sẵn).

IF COL_LENGTH('dbo.ZnsSendBatches', 'ApprovedBy') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD ApprovedBy NVARCHAR(150) NULL, ApprovedAt DATETIME2 NULL,
          RejectedBy NVARCHAR(150) NULL, RejectedAt DATETIME2 NULL, RejectReason NVARCHAR(500) NULL, PauseReason NVARCHAR(300) NULL');

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ZnsSendBatches_Status')
    ALTER TABLE dbo.ZnsSendBatches DROP CONSTRAINT CK_ZnsSendBatches_Status;
ALTER TABLE dbo.ZnsSendBatches ADD CONSTRAINT CK_ZnsSendBatches_Status
    CHECK (Status IN ('draft', 'pending', 'pending_approval', 'rejected', 'sending', 'paused', 'done', 'partial', 'failed', 'cancelled'));

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ZnsSendLimits')
BEGIN
    CREATE TABLE dbo.ZnsSendLimits (
        Owner NVARCHAR(20) NOT NULL CONSTRAINT PK_ZnsSendLimits PRIMARY KEY,
        MaxPerBatch INT NULL,
        LimitBasis NVARCHAR(10) NOT NULL CONSTRAINT DF_ZnsSendLimits_Basis DEFAULT 'count'
            CONSTRAINT CK_ZnsSendLimits_Basis CHECK (LimitBasis IN ('count', 'budget')),
        MaxPerMonth INT NULL,
        UnitPrice DECIMAL(18, 2) NULL,
        MaxBudgetPerMonth DECIMAL(18, 2) NULL,
        UpdatedBy NVARCHAR(150) NULL,
        UpdatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsSendLimits_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
    INSERT INTO dbo.ZnsSendLimits (Owner, MaxPerBatch, MaxPerMonth) VALUES ('PGI', 1000, 10000), ('AWG', 1000, 10000);
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'AppAuditLog')
BEGIN
    CREATE TABLE dbo.AppAuditLog (
        Id BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_AppAuditLog PRIMARY KEY,
        Action NVARCHAR(50) NOT NULL,
        Actor NVARCHAR(150) NOT NULL,
        TargetType NVARCHAR(30) NULL,
        TargetId NVARCHAR(150) NULL,
        Detail NVARCHAR(2000) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_AppAuditLog_CreatedAt DEFAULT SYSUTCDATETIME()
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ZnsSendAttempts_CreatedAt' AND object_id = OBJECT_ID('dbo.ZnsSendAttempts'))
    CREATE INDEX IX_ZnsSendAttempts_CreatedAt ON dbo.ZnsSendAttempts (CreatedAt) INCLUDE (BatchId, Result);

EXEC('
CREATE OR ALTER VIEW dbo.vw_ZnsSendBatches AS
SELECT
    b.Id AS BatchId,
    b.ParentBatchId,
    t.Name AS TemplateName,
    t.ZnsCode,
    b.Owner,
    b.FileName,
    b.Status,
    CASE b.Status
        WHEN ''pending'' THEN N''Chờ gửi''
        WHEN ''pending_approval'' THEN N''Chờ duyệt''
        WHEN ''rejected'' THEN N''Từ chối''
        WHEN ''sending'' THEN N''Đang gửi''
        WHEN ''paused'' THEN N''Tạm dừng''
        WHEN ''done'' THEN CASE WHEN b.SendMode = ''dry_run'' THEN N''Đã chạy thử'' ELSE N''Đã gửi'' END
        WHEN ''partial'' THEN N''Gửi một phần''
        WHEN ''failed'' THEN N''Thất bại''
        WHEN ''cancelled'' THEN N''Đã hủy''
        ELSE b.Status
    END AS StatusLabel,
    b.SendMode,
    b.TotalRows,
    b.ValidRows,
    b.InvalidRows,
    b.SentRows,
    b.FailedRows,
    b.UnknownRows,
    b.CreatedBy,
    b.ConfirmedBy,
    b.ApprovedBy,
    b.RejectedBy,
    b.RejectReason,
    b.PauseReason,
    b.CancelledBy,
    DATEADD(HOUR, 7, b.CreatedAt) AS CreatedAtVN,
    DATEADD(HOUR, 7, b.ConfirmedAt) AS ConfirmedAtVN,
    DATEADD(HOUR, 7, b.ApprovedAt) AS ApprovedAtVN,
    DATEADD(HOUR, 7, b.RejectedAt) AS RejectedAtVN,
    DATEADD(HOUR, 7, b.SendStartedAt) AS SendStartedAtVN,
    DATEADD(HOUR, 7, b.SendFinishedAt) AS SendFinishedAtVN,
    DATEADD(HOUR, 7, b.CancelledAt) AS CancelledAtVN
FROM dbo.ZnsSendBatches b
LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
WHERE b.Status <> ''draft''
');

EXEC('
CREATE OR ALTER VIEW dbo.vw_AppAuditLog AS
SELECT Id, Action, Actor, TargetType, TargetId, Detail, DATEADD(HOUR, 7, CreatedAt) AS CreatedAtVN
FROM dbo.AppAuditLog
');
