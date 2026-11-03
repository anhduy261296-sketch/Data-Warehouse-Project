-- Chuyển bước duyệt từ lô gửi sang mẫu tin: chỉ mẫu đã duyệt mới dùng để gửi, sửa mẫu thì phải duyệt lại.
-- Mẫu đang có được coi là đã duyệt. Lô còn chờ duyệt theo luồng cũ chuyển sang Đã hủy, tuyệt đối không tự gửi.

IF COL_LENGTH('dbo.ZnsTemplates', 'ApprovalStatus') IS NULL
BEGIN
    EXEC('ALTER TABLE dbo.ZnsTemplates ADD ApprovalStatus VARCHAR(10) NOT NULL CONSTRAINT DF_ZnsTemplates_ApprovalStatus DEFAULT ''pending''
              CONSTRAINT CK_ZnsTemplates_ApprovalStatus CHECK (ApprovalStatus IN (''pending'', ''approved'', ''rejected'')),
          SubmittedBy NVARCHAR(150) NULL, ApprovedBy NVARCHAR(150) NULL, ApprovedAt DATETIME2 NULL,
          RejectedBy NVARCHAR(150) NULL, RejectedAt DATETIME2 NULL, RejectReason NVARCHAR(500) NULL');
    EXEC('UPDATE dbo.ZnsTemplates SET ApprovalStatus = ''approved'', SubmittedBy = UpdatedBy');
END

EXEC('
UPDATE r SET Status = ''cancelled''
FROM dbo.ZnsSendRecipients r JOIN dbo.ZnsSendBatches b ON b.Id = r.BatchId
WHERE b.Status = ''pending_approval'' AND r.Status = ''pending''
');
EXEC('
UPDATE dbo.ZnsSendBatches SET Status = ''cancelled'', CancelledBy = ''system'', CancelledAt = SYSUTCDATETIME()
WHERE Status = ''pending_approval''
');
