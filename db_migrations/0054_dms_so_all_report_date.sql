IF COL_LENGTH('dbo.DMS_SO_ALL', 'report_date') IS NULL
    ALTER TABLE dbo.DMS_SO_ALL
    ADD report_date AS (COALESCE(document_date, created_at)) PERSISTED;

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.DMS_SO_ALL') AND name = 'IX_DMS_SO_ALL_DocumentDate'
)
    DROP INDEX IX_DMS_SO_ALL_DocumentDate ON dbo.DMS_SO_ALL;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.DMS_SO_ALL') AND name = 'IX_DMS_SO_ALL_ReportDate'
)
    CREATE INDEX IX_DMS_SO_ALL_ReportDate ON dbo.DMS_SO_ALL(report_date DESC)
    INCLUDE (document_type, order_type, state_code, amount_total);
