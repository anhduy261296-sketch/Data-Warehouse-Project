-- Xử lý khách gửi lỗi: phân loại lỗi, nhật ký từng lần gọi API, lô gửi một phần / thất bại / tạm dừng, gửi lại.

IF COL_LENGTH('dbo.ZnsSendRecipients', 'ErrorKind') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD ErrorKind VARCHAR(12) NULL');
IF COL_LENGTH('dbo.ZnsSendRecipients', 'AttemptCount') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD AttemptCount INT NOT NULL CONSTRAINT DF_ZnsSendRecipients_AttemptCount DEFAULT 0');
IF COL_LENGTH('dbo.ZnsSendRecipients', 'RetryCount') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD RetryCount INT NOT NULL CONSTRAINT DF_ZnsSendRecipients_RetryCount DEFAULT 0');
IF COL_LENGTH('dbo.ZnsSendRecipients', 'RetriedInBatchId') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD RetriedInBatchId INT NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'UnknownRows') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD UnknownRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_UnknownRows DEFAULT 0');
IF COL_LENGTH('dbo.ZnsSendBatches', 'ParentBatchId') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD ParentBatchId INT NULL');

IF OBJECT_ID('dbo.CK_ZnsSendRecipients_Status', 'C') IS NOT NULL
    ALTER TABLE dbo.ZnsSendRecipients DROP CONSTRAINT CK_ZnsSendRecipients_Status;
ALTER TABLE dbo.ZnsSendRecipients ADD CONSTRAINT CK_ZnsSendRecipients_Status
    CHECK (Status IN ('pending', 'sending', 'invalid', 'sent', 'failed', 'unknown', 'cancelled', 'simulated'));

IF OBJECT_ID('dbo.CK_ZnsSendBatches_Status', 'C') IS NOT NULL
    ALTER TABLE dbo.ZnsSendBatches DROP CONSTRAINT CK_ZnsSendBatches_Status;
ALTER TABLE dbo.ZnsSendBatches ADD CONSTRAINT CK_ZnsSendBatches_Status
    CHECK (Status IN ('draft', 'pending', 'sending', 'paused', 'done', 'partial', 'failed', 'cancelled'));

IF OBJECT_ID('dbo.ZnsSendAttempts', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ZnsSendAttempts (
        Id BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ZnsSendAttempts PRIMARY KEY,
        BatchId INT NOT NULL,
        RecipientId BIGINT NOT NULL CONSTRAINT FK_ZnsSendAttempts_Recipient REFERENCES dbo.ZnsSendRecipients (Id),
        AttemptNo INT NOT NULL,
        TriggerType VARCHAR(10) NOT NULL,
        TriggeredBy NVARCHAR(150) NULL,
        Result VARCHAR(12) NOT NULL,
        HttpStatus INT NULL,
        DurationMs INT NULL,
        ErrorMessage NVARCHAR(1000) NULL,
        ApiResponse NVARCHAR(2000) NULL,
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_ZnsSendAttempts_CreatedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ZnsSendAttempts_Recipient ON dbo.ZnsSendAttempts (RecipientId, AttemptNo);
    CREATE INDEX IX_ZnsSendAttempts_Batch ON dbo.ZnsSendAttempts (BatchId);
END

-- Dữ liệu cũ: lỗi cấu hình đã biết, và các lô từng bị ghi "Đã gửi" dù có khách lỗi.
EXEC('
UPDATE dbo.ZnsSendRecipients SET ErrorKind = ''config''
WHERE Status = ''failed'' AND ErrorKind IS NULL AND (ErrorMessage LIKE ''Incom -6:%'' OR ErrorMessage LIKE ''Incom -2:%'');
UPDATE dbo.ZnsSendRecipients SET ErrorKind = ''business'' WHERE Status = ''failed'' AND ErrorKind IS NULL;
UPDATE dbo.ZnsSendBatches SET Status = CASE WHEN SentRows = 0 THEN ''failed'' ELSE ''partial'' END
WHERE Status = ''done'' AND FailedRows > 0;
');

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
    b.CancelledBy,
    DATEADD(HOUR, 7, b.CreatedAt) AS CreatedAtVN,
    DATEADD(HOUR, 7, b.ConfirmedAt) AS ConfirmedAtVN,
    DATEADD(HOUR, 7, b.SendStartedAt) AS SendStartedAtVN,
    DATEADD(HOUR, 7, b.SendFinishedAt) AS SendFinishedAtVN,
    DATEADD(HOUR, 7, b.CancelledAt) AS CancelledAtVN
FROM dbo.ZnsSendBatches b
LEFT JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
WHERE b.Status <> ''draft''
');

EXEC('
CREATE OR ALTER VIEW dbo.vw_ZnsSendRecipients AS
SELECT
    r.Id AS RecipientId,
    r.BatchId,
    r.RowNo,
    r.Phone,
    r.CustomerName,
    r.Status,
    CASE r.Status
        WHEN ''pending'' THEN N''Chờ gửi''
        WHEN ''sending'' THEN N''Đang gửi''
        WHEN ''invalid'' THEN N''Lỗi dữ liệu''
        WHEN ''sent'' THEN N''Đã gửi thành công''
        WHEN ''failed'' THEN N''Gửi thất bại''
        WHEN ''unknown'' THEN N''Chưa rõ kết quả''
        WHEN ''cancelled'' THEN N''Đã hủy''
        WHEN ''simulated'' THEN N''Chạy thử (không gửi)''
        ELSE r.Status
    END AS StatusLabel,
    r.ErrorKind,
    r.ErrorMessage,
    r.AttemptCount,
    r.RetryCount,
    r.RetriedInBatchId,
    r.ZaloMsgId,
    r.Content,
    r.Params,
    r.ApiResponse,
    DATEADD(HOUR, 7, r.SentAt) AS SentAtVN,
    DATEADD(HOUR, 7, r.CreatedAt) AS CreatedAtVN
FROM dbo.ZnsSendRecipients r
');

EXEC('
CREATE OR ALTER VIEW dbo.vw_ZnsSendAttempts AS
SELECT
    a.Id AS AttemptId,
    a.BatchId,
    a.RecipientId,
    r.RowNo,
    r.Phone,
    r.CustomerName,
    a.AttemptNo,
    a.TriggerType,
    a.TriggeredBy,
    a.Result,
    a.HttpStatus,
    a.DurationMs,
    a.ErrorMessage,
    a.ApiResponse,
    DATEADD(HOUR, 7, a.CreatedAt) AS CreatedAtVN
FROM dbo.ZnsSendAttempts a
JOIN dbo.ZnsSendRecipients r ON r.Id = a.RecipientId
');
