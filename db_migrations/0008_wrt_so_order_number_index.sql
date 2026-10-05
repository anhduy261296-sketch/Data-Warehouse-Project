IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WRT_SO_order_number' AND object_id = OBJECT_ID('dbo.WRT_SO'))
BEGIN
    CREATE INDEX IX_WRT_SO_order_number ON dbo.WRT_SO (order_number);
END
