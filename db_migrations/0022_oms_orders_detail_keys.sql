-- OMS_ORDERS: 77/80 cot la NVARCHAR(MAX) -> khong danh index duoc (SQL Server khong cho MAX lam khoa index).
-- Bang Chi tiet don hang (E-com, DMS xuat kho, DH theo NV - OMS) phai quet ca bang moi lan doi trang.
--   1. order_number, outbound_order_type: doi kieu tai cho sang NVARCHAR co do dai (giong tien le employee_code - 0003)
--      Gioi han rong (100 / 20) so voi thuc te (23 / 3). Chi doi khi du lieu hien co vua - khong thi bo qua (khong loi).
--   2. created_date: GIU NGUYEN chuoi ISO (pipeline OMS xoa theo khoang ngay bang so sanh chuoi '...Z'; hien thi giu mui gio)
--      -> them 1 cot tinh san _k_created_at (PERSISTED) de loc ngay co index.
--   3. _whseid: khong code nao dung -> xoa neu cot rong hoan toan.
-- Moi buoc kiem tra truoc / dung EXEC rieng (cot moi phai ton tai truoc khi tao index trong cung batch).

-- 0. Don ban thu nghiem cu cua migration nay (chi tung chay o DB local): 2 cot tinh san _k_order_number, _k_outbound_type
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_outbound_type') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_outbound_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
    EXEC('DROP INDEX IX_OMS_ORDERS_outbound_created ON dbo.OMS_ORDERS');
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_order_number') IS NOT NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _k_order_number');
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_outbound_type') IS NOT NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _k_outbound_type');

-- 1. Doi kieu cot khoa (chi khi dang la MAX va du lieu vua gioi han moi)
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length = -1)
   AND NOT EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE LEN(order_number) > 100)
    EXEC('ALTER TABLE dbo.OMS_ORDERS ALTER COLUMN order_number NVARCHAR(100) NULL');

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'outbound_order_type' AND max_length = -1)
   AND NOT EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE LEN(outbound_order_type) > 20)
    EXEC('ALTER TABLE dbo.OMS_ORDERS ALTER COLUMN outbound_order_type NVARCHAR(20) NULL');

-- 2. Ngay tao dang ngay gio (created_date la chuoi ISO 8601, vd 2026-09-30T15:50:00.698161+00:00; style 126 cho phep PERSISTED)
IF COL_LENGTH('dbo.OMS_ORDERS', '_k_created_at') IS NULL
    EXEC('ALTER TABLE dbo.OMS_ORDERS ADD _k_created_at AS TRY_CONVERT(DATETIME2, created_date, 126) PERSISTED');

-- 3. Index (chi tao khi cot khoa da doi kieu thanh cong)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_outbound_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'outbound_order_type' AND max_length <> -1)
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length <> -1)
    EXEC('CREATE INDEX IX_OMS_ORDERS_outbound_created ON dbo.OMS_ORDERS (outbound_order_type, _k_created_at) INCLUDE (order_number)');

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_order_number' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.OMS_ORDERS') AND name = 'order_number' AND max_length <> -1)
    EXEC('CREATE INDEX IX_OMS_ORDERS_order_number ON dbo.OMS_ORDERS (order_number)');

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OMS_ORDERS_created' AND object_id = OBJECT_ID('dbo.OMS_ORDERS'))
    EXEC('CREATE INDEX IX_OMS_ORDERS_created ON dbo.OMS_ORDERS (_k_created_at)');

-- 4. Xoa cot _whseid khong dung (chi khi rong hoan toan; go rang buoc mac dinh truoc neu co)
--    (kiem tra du lieu bang SQL dong: neu DB khong co cot _whseid thi cau lenh tinh van bien dich duoc)
DECLARE @whseid_has_data BIT = 1;
IF COL_LENGTH('dbo.OMS_ORDERS', '_whseid') IS NOT NULL
    EXEC sp_executesql N'SELECT @h = CASE WHEN EXISTS (SELECT 1 FROM dbo.OMS_ORDERS WHERE _whseid IS NOT NULL) THEN 1 ELSE 0 END',
                       N'@h BIT OUTPUT', @h = @whseid_has_data OUTPUT;
IF COL_LENGTH('dbo.OMS_ORDERS', '_whseid') IS NOT NULL AND @whseid_has_data = 0
BEGIN
    DECLARE @df SYSNAME = (SELECT dc.name FROM sys.default_constraints dc
                           JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
                           WHERE dc.parent_object_id = OBJECT_ID('dbo.OMS_ORDERS') AND c.name = '_whseid');
    IF @df IS NOT NULL EXEC('ALTER TABLE dbo.OMS_ORDERS DROP CONSTRAINT ' + @df);
    EXEC('ALTER TABLE dbo.OMS_ORDERS DROP COLUMN _whseid');
END
