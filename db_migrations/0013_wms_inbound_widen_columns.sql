DECLARE @cols TABLE (name SYSNAME, len INT);
INSERT INTO @cols (name, len) VALUES
    ('skudesc', 500), ('noteitem', 2000),
    ('lottable01', 200), ('lottable02', 200), ('lottable03', 200), ('lottable06', 200), ('lottable07', 200),
    ('lottable08', 200), ('lottable09', 200), ('lottable10', 200),
    ('suppliercode', 100), ('pokey', 100), ('externalreceiptkey2', 100), ('upccode', 100), ('toloc', 100),
    ('category', 100), ('unitid', 100), ('cartonid', 100), ('palletid', 100), ('addwho', 100), ('editwho', 100),
    ('skugroup', 100),
    ('company', 200), ('supplier_address', 500), ('consigneename', 200),
    ('sku_susr1', 200), ('sku_susr2', 200), ('sku_susr3', 200), ('sku_susr4', 200), ('sku_susr5', 200),
    ('sku_susr6', 200), ('sku_susr7', 200), ('sku_susr8', 200), ('sku_susr9', 200), ('sku_susr10', 200),
    ('susr1', 200), ('susr4', 200), ('susr5', 200), ('susr12', 200);

DECLARE @name SYSNAME, @len INT, @sql NVARCHAR(400);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT name, len FROM @cols;
OPEN c;
FETCH NEXT FROM c INTO @name, @len;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.WMS_INBOUND') AND name = @name
               AND max_length <> -1 AND max_length / 2 < @len)
    BEGIN
        SET @sql = N'ALTER TABLE dbo.WMS_INBOUND ALTER COLUMN ' + QUOTENAME(@name) + N' NVARCHAR(' + CAST(@len AS NVARCHAR(10)) + N') NULL';
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM c INTO @name, @len;
END
CLOSE c;
DEALLOCATE c;
