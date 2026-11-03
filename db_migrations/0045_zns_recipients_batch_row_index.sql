-- Danh sách khách và luồng gửi đều đọc theo lô, xếp theo RowNo. Có index này thì không phải sort,
-- nên không phải xin bộ nhớ cho sort: lúc server thiếu RAM, câu lệnh không bị xếp hàng chờ tới 25 giây (RESOURCE_SEMAPHORE).

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ZnsSendRecipients_BatchRow' AND object_id = OBJECT_ID('dbo.ZnsSendRecipients'))
    CREATE INDEX IX_ZnsSendRecipients_BatchRow ON dbo.ZnsSendRecipients (BatchId, RowNo);
