

IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'OMS_ORDERS' AND COLUMN_NAME = 'employee_code'
      AND DATA_TYPE = 'nvarchar' AND CHARACTER_MAXIMUM_LENGTH = -1
)
BEGIN
    -- Doi tu NVARCHAR(MAX) sang NVARCHAR(50) - NVARCHAR(MAX) khong the lam
    -- key column cua index. Da xac nhan do dai thuc te toi da 6 ky tu, an
    -- toan khong mat du lieu.
    ALTER TABLE dbo.OMS_ORDERS ALTER COLUMN employee_code NVARCHAR(50);
END

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'IX_OMS_ORDERS_EmployeeCode'
)
BEGIN
    CREATE INDEX IX_OMS_ORDERS_EmployeeCode ON dbo.OMS_ORDERS(employee_code);
END

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.DMS_SO') AND name = 'IX_DMS_SO_SaleEmployeeCode'
)
BEGIN
    CREATE INDEX IX_DMS_SO_SaleEmployeeCode ON dbo.DMS_SO(SaleEmployeeCode);
END
