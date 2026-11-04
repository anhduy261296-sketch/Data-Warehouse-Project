-- Nhật ký lưu thêm IP người thao tác. Thời lượng lô lưu đến mili giây để lô dưới 1 giây vẫn có số đo.
-- Lô cũ có SendDurationSeconds = 0 không biết chính xác bao nhiêu mili giây nên để NULL.

IF COL_LENGTH('dbo.AppAuditLog', 'IpAddress') IS NULL
    EXEC('ALTER TABLE dbo.AppAuditLog ADD IpAddress NVARCHAR(45) NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendDurationMs') IS NULL
BEGIN
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendDurationMs BIGINT NULL');
    EXEC('UPDATE dbo.ZnsSendBatches SET SendDurationMs = CAST(SendDurationSeconds AS BIGINT) * 1000 WHERE SendDurationSeconds > 0');
END

EXEC('
CREATE OR ALTER VIEW dbo.vw_AppAuditLog AS
SELECT Id, Action, Actor, TargetType, TargetId, Detail, IpAddress, DATEADD(HOUR, 7, CreatedAt) AS CreatedAtVN
FROM dbo.AppAuditLog
');

EXEC('
CREATE OR ALTER VIEW dbo.vw_ZnsSendBatches AS
SELECT
    b.Id AS BatchId,
    b.ParentBatchId,
    COALESCE(b.TemplateName, t.Name) AS TemplateName,
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
    b.SendDurationSeconds,
    b.SendDurationMs,
    CASE
        WHEN b.SendDurationMs < 1000 THEN CONCAT(b.SendDurationMs, ''ms'')
        WHEN b.SendDurationSeconds >= 60 THEN CONCAT(b.SendDurationSeconds / 60, ''m'', b.SendDurationSeconds % 60, ''s'')
        WHEN b.SendDurationSeconds > 0 THEN CONCAT(b.SendDurationSeconds, ''s'')
        WHEN b.SendDurationSeconds = 0 THEN ''<1s''
    END AS SendDuration,
    b.CreatedBy,
    b.ConfirmedBy,
    b.ApprovedBy,
    b.RejectedBy,
    b.RejectReason,
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
