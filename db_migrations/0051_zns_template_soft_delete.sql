-- Xóa mẫu tin là xóa mềm: ẩn khỏi giao diện nhưng vẫn giữ trong DB. Mã của mẫu đã xóa được dùng lại nên ràng buộc trùng mã chỉ xét mẫu chưa xóa.

IF COL_LENGTH('dbo.ZnsTemplates', 'DeletedAt') IS NULL
    EXEC('ALTER TABLE dbo.ZnsTemplates ADD DeletedAt DATETIME2 NULL, DeletedBy NVARCHAR(150) NULL');

IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id = OBJECT_ID('dbo.ZnsTemplates') AND name = 'UQ_ZnsTemplates_Owner_Code')
    ALTER TABLE dbo.ZnsTemplates DROP CONSTRAINT UQ_ZnsTemplates_Owner_Code;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.ZnsTemplates') AND name = 'UQ_ZnsTemplates_Owner_Code')
    EXEC('CREATE UNIQUE INDEX UQ_ZnsTemplates_Owner_Code ON dbo.ZnsTemplates (Owner, ZnsCode) WHERE DeletedAt IS NULL');
