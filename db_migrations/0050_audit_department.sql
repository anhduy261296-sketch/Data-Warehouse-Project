-- Nhật ký chiến dịch xem theo phòng ban: mỗi dòng log của mẫu tin, lô gửi lưu phòng ban tại thời điểm ghi.
-- Log cũ để NULL: sync_access tự gán theo mẫu / lô tương ứng.

IF COL_LENGTH('dbo.AppAuditLog', 'DepartmentId') IS NULL
    EXEC('ALTER TABLE dbo.AppAuditLog ADD DepartmentId INT NULL');

EXEC('
CREATE OR ALTER VIEW dbo.vw_AppAuditLog AS
SELECT Id, Action, Actor, TargetType, TargetId, DepartmentId, Detail, IpAddress, DATEADD(HOUR, 7, CreatedAt) AS CreatedAtVN
FROM dbo.AppAuditLog
');
