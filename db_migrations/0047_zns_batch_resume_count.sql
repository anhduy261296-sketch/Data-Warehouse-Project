-- Số lần lô được chạy tiếp sau khi tiến trình gửi dừng: quá giới hạn thì tạm dừng, tránh lặp vô hạn mà mỗi vòng vẫn gửi thêm tin.

IF COL_LENGTH('dbo.ZnsSendBatches', 'SendResumeCount') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD SendResumeCount INT NOT NULL CONSTRAINT DF_ZnsSendBatches_SendResumeCount DEFAULT 0');
