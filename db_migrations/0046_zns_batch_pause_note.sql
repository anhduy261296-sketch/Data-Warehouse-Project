-- Lý do lô tạm dừng khi không phải do lỗi cấu hình, vd. tiến trình gửi đã dừng quá lâu nên hệ thống không tự gửi tiếp.

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendPauseNote') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendPauseNote NVARCHAR(300) NULL');
