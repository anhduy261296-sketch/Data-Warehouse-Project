-- Lô giữ tên mẫu lúc gửi, để sửa mẫu về sau không làm đổi lịch sử.
-- Nhật ký mẫu lưu cả nội dung trước và sau khi sửa (nội dung tối đa 2000 ký tự mỗi bản) nên Detail cần dài hơn.

IF COL_LENGTH('dbo.ZnsSendBatches', 'TemplateName') IS NULL
BEGIN
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD TemplateName NVARCHAR(200) NULL');
    EXEC('
    UPDATE b SET TemplateName = t.Name
    FROM dbo.ZnsSendBatches b JOIN dbo.ZnsTemplates t ON t.Id = b.TemplateId
    WHERE b.Status <> ''draft''
    ');
END

ALTER TABLE dbo.ZnsTemplateChangeLog ALTER COLUMN Detail NVARCHAR(MAX) NULL;

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
