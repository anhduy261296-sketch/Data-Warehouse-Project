-- Lưu sẵn số đã gửi / gửi lỗi trên lô, và 2 view hiển thị giờ Việt Nam (UTC+7) để xem trực tiếp trong DB.
-- Bảng gốc vẫn lưu UTC như toàn hệ thống.

IF COL_LENGTH('dbo.ZnsSendBatches', 'SentRows') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SentRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_SentRows DEFAULT 0');

IF COL_LENGTH('dbo.ZnsSendBatches', 'FailedRows') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD FailedRows INT NOT NULL CONSTRAINT DF_ZnsSendBatches_FailedRows DEFAULT 0');

EXEC('
UPDATE b SET
    SentRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status IN (''sent'', ''simulated'')),
    FailedRows = (SELECT COUNT(*) FROM dbo.ZnsSendRecipients r WHERE r.BatchId = b.Id AND r.Status = ''failed'')
FROM dbo.ZnsSendBatches b
');

EXEC('
CREATE OR ALTER VIEW dbo.vw_ZnsSendBatches AS
SELECT
    b.Id AS BatchId,
    t.Name AS TemplateName,
    t.ZnsCode,
    b.Owner,
    b.FileName,
    b.Status,
    CASE b.Status
        WHEN ''pending'' THEN N''Chờ gửi''
        WHEN ''sending'' THEN N''Đang gửi''
        WHEN ''done'' THEN CASE WHEN b.SendMode = ''dry_run'' THEN N''Đã chạy thử'' ELSE N''Đã gửi'' END
        WHEN ''cancelled'' THEN N''Đã hủy''
        ELSE b.Status
    END AS StatusLabel,
    b.SendMode,
    b.TotalRows,
    b.ValidRows,
    b.InvalidRows,
    b.SentRows,
    b.FailedRows,
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
        WHEN ''invalid'' THEN N''Lỗi dữ liệu''
        WHEN ''sent'' THEN N''Đã gửi thành công''
        WHEN ''failed'' THEN N''Gửi thất bại''
        WHEN ''cancelled'' THEN N''Đã hủy''
        WHEN ''simulated'' THEN N''Chạy thử (không gửi)''
        ELSE r.Status
    END AS StatusLabel,
    r.ErrorMessage,
    r.ZaloMsgId,
    r.Content,
    r.Params,
    r.ApiResponse,
    DATEADD(HOUR, 7, r.SentAt) AS SentAtVN,
    DATEADD(HOUR, 7, r.CreatedAt) AS CreatedAtVN
FROM dbo.ZnsSendRecipients r
');
