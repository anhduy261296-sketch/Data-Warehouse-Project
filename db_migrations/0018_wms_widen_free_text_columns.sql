DECLARE @t SYSNAME, @name SYSNAME, @len INT, @target INT, @sql NVARCHAR(400);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR
    SELECT OBJECT_NAME(col.object_id), col.name, col.max_length / 2
    FROM sys.columns col
    WHERE col.object_id IN (OBJECT_ID('dbo.WMS_INBOUND'), OBJECT_ID('dbo.WMS_OUTBOUND'))
      AND TYPE_NAME(col.user_type_id) = 'nvarchar'
      AND col.max_length <> -1
      AND col.max_length / 2 < 200
      AND col.name NOT LIKE '[_]%'
      AND NOT EXISTS (SELECT 1 FROM sys.index_columns ic WHERE ic.object_id = col.object_id AND ic.column_id = col.column_id);
OPEN c;
FETCH NEXT FROM c INTO @t, @name, @len;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @target = CASE WHEN @name LIKE 'susr%' THEN 1000 ELSE 200 END;
    SET @sql = N'ALTER TABLE dbo.' + QUOTENAME(@t) + N' ALTER COLUMN ' + QUOTENAME(@name) + N' NVARCHAR(' + CAST(@target AS NVARCHAR(10)) + N') NULL';
    EXEC sp_executesql @sql;
    FETCH NEXT FROM c INTO @t, @name, @len;
END
CLOSE c;
DEALLOCATE c;

DECLARE c2 CURSOR LOCAL FAST_FORWARD FOR
    SELECT OBJECT_NAME(col.object_id), col.name
    FROM sys.columns col
    WHERE col.object_id IN (OBJECT_ID('dbo.WMS_INBOUND'), OBJECT_ID('dbo.WMS_OUTBOUND'))
      AND TYPE_NAME(col.user_type_id) = 'nvarchar'
      AND col.max_length <> -1
      AND col.max_length / 2 < 1000
      AND col.name LIKE 'susr%'
      AND NOT EXISTS (SELECT 1 FROM sys.index_columns ic WHERE ic.object_id = col.object_id AND ic.column_id = col.column_id);
OPEN c2;
FETCH NEXT FROM c2 INTO @t, @name;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'ALTER TABLE dbo.' + QUOTENAME(@t) + N' ALTER COLUMN ' + QUOTENAME(@name) + N' NVARCHAR(1000) NULL';
    EXEC sp_executesql @sql;
    FETCH NEXT FROM c2 INTO @t, @name;
END
CLOSE c2;
DEALLOCATE c2;
