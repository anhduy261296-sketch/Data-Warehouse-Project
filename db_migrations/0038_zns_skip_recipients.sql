-- Bỏ qua khách lỗi kèm lý do: khách không còn được tính là lỗi và không gửi lại được nữa.

IF COL_LENGTH('dbo.ZnsSendRecipients', 'SkipReason') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendRecipients ADD SkipReason NVARCHAR(500) NULL, SkippedBy NVARCHAR(150) NULL, SkippedAt DATETIME2 NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SkippedRows') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SkippedRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_SkippedRows DEFAULT 0');

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ZnsSendRecipients_Status')
    ALTER TABLE dbo.ZnsSendRecipients DROP CONSTRAINT CK_ZnsSendRecipients_Status;
ALTER TABLE dbo.ZnsSendRecipients ADD CONSTRAINT CK_ZnsSendRecipients_Status
    CHECK (Status IN ('pending', 'sending', 'invalid', 'sent', 'failed', 'unknown', 'skipped', 'cancelled', 'simulated'));

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
    b.SkippedRows,
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
        WHEN ''sent'' THEN N''Thành công''
        WHEN ''failed'' THEN N''Thất bại''
        WHEN ''unknown'' THEN N''Chưa rõ''
        WHEN ''skipped'' THEN N''Bỏ qua''
        WHEN ''cancelled'' THEN N''Đã hủy''
        WHEN ''simulated'' THEN N''Chạy thử''
        ELSE r.Status
    END AS StatusLabel,
    r.ErrorKind,
    r.ErrorMessage,
    r.SkipReason,
    r.SkippedBy,
    r.AttemptCount,
    r.RetryCount,
    r.RetriedInBatchId,
    r.ZaloMsgId,
    r.Content,
    r.Params,
    r.ApiResponse,
    DATEADD(HOUR, 7, r.SkippedAt) AS SkippedAtVN,
    DATEADD(HOUR, 7, r.SentAt) AS SentAtVN,
    DATEADD(HOUR, 7, r.CreatedAt) AS CreatedAtVN
FROM dbo.ZnsSendRecipients r
');
