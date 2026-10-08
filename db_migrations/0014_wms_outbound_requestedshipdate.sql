IF COL_LENGTH('dbo.WMS_OUTBOUND', 'requestedshipdate') IS NULL
    ALTER TABLE dbo.WMS_OUTBOUND ADD requestedshipdate DATETIME2 NULL;
