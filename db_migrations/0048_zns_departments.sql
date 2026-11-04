-- Phòng ban: nhóm người dùng được đánh dấu là phòng ban giới hạn ai thấy mẫu tin và lô gửi.
-- Mẫu và lô cũ để NULL: sync_access tự gán theo phòng ban của người tạo, không xác định được thì chỉ người xem được mọi phòng ban mới thấy.

IF OBJECT_ID('dbo.AppDepartmentGroups', 'U') IS NULL
    EXEC('CREATE TABLE dbo.AppDepartmentGroups (GroupId INT NOT NULL CONSTRAINT PK_AppDepartmentGroups PRIMARY KEY)');

IF COL_LENGTH('dbo.ZnsTemplates', 'DepartmentId') IS NULL
    EXEC('ALTER TABLE dbo.ZnsTemplates ADD DepartmentId INT NULL');

IF COL_LENGTH('dbo.ZnsSendBatches', 'DepartmentId') IS NULL
    EXEC('ALTER TABLE dbo.ZnsSendBatches ADD DepartmentId INT NULL');

IF OBJECT_ID('dbo.auth_group', 'U') IS NOT NULL
    EXEC(N'
    INSERT INTO dbo.AppDepartmentGroups (GroupId)
    SELECT g.id FROM dbo.auth_group g
    WHERE g.name IN (N''IT'', N''MKT'', N''Kế toán'')
          AND NOT EXISTS (SELECT 1 FROM dbo.AppDepartmentGroups d WHERE d.GroupId = g.id)
    ');
