-- Mẫu bị từ chối luôn ở trạng thái ngừng hoạt động (khi từ chối từ nay hệ thống tự tắt).
UPDATE dbo.ZnsTemplates SET IsActive = 0 WHERE ApprovalStatus = 'rejected' AND IsActive = 1;
