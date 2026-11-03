-- Mỗi lô chỉ một tiến trình được gửi: SendRunId là tiến trình đang giữ lô, SendHeartbeatAt là lần cuối tiến trình đó còn hoạt động.
-- Lô "Đang gửi" im quá lâu nghĩa là tiến trình đã dừng (restart, deploy, lỗi DB): hệ thống tự nhận lại và gửi tiếp.

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendRunId') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendRunId CHAR(36) NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendHeartbeatAt') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendHeartbeatAt DATETIME2 NULL');
