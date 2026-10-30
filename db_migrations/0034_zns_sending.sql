-- Gửi ZNS qua Incom Omni: lưu tham số đã ghép, phản hồi API, chế độ gửi (dry_run / live).

IF COL_LENGTH('dbo.ZnsSendRecipients', 'Params') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD Params NVARCHAR(MAX) NULL');

IF COL_LENGTH('dbo.ZnsSendRecipients', 'ApiResponse') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD ApiResponse NVARCHAR(2000) NULL');

-- simulated = chạy thử, không gọi API thật.
IF OBJECT_ID('dbo.CK_ZnsSendRecipients_Status', 'C') IS NOT NULL
    ALTER TABLE dbo.ZnsSendRecipients DROP CONSTRAINT CK_ZnsSendRecipients_Status;
ALTER TABLE dbo.ZnsSendRecipients ADD CONSTRAINT CK_ZnsSendRecipients_Status
    CHECK (Status IN ('pending', 'invalid', 'sent', 'failed', 'cancelled', 'simulated'));

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendMode') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendMode VARCHAR(10) NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SentBy') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SentBy NVARCHAR(150) NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendStartedAt') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendStartedAt DATETIME2 NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendFinishedAt') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendFinishedAt DATETIME2 NULL');
