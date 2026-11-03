-- Bật READ_COMMITTED_SNAPSHOT: đọc không bị ghi chặn và ngược lại, tránh deadlock giữa màn hình và luồng gửi ZNS.
-- Chạy tay một lần trên từng server bằng login có quyền ALTER DATABASE, đang đứng ở đúng database (local và prod: DMS_POSTGRE hoặc tên tương ứng).
-- Không để trong db_migrations/: login của app không có quyền này và migration chạy trong transaction nên lệnh sẽ lỗi, làm container không khởi động.
-- Trước khi chạy: chọn lúc không có DAG / job đang ghi. Sau 30 giây, transaction còn mở trong database này sẽ bị rollback và các kết nối khác bị ngắt.

SELECT DB_NAME() AS DatabaseName, is_read_committed_snapshot_on AS BeforeChange FROM sys.databases WHERE name = DB_NAME();

ALTER DATABASE CURRENT SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK AFTER 30 SECONDS;

SELECT DB_NAME() AS DatabaseName, is_read_committed_snapshot_on AS AfterChange FROM sys.databases WHERE name = DB_NAME();
