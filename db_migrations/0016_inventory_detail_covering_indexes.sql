-- Index phủ cho popup chi tiết Tồn kho SAP-WMS: đọc thẳng từ index, không phải tra ngược bảng gốc (bảng rộng).

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SAP_INOUT_ItemCode_Detail' AND object_id = OBJECT_ID('dbo.SAP_INOUT'))
    CREATE INDEX IX_SAP_INOUT_ItemCode_Detail ON dbo.SAP_INOUT (ItemCode)
        INCLUDE (IN_WhsCode, IN_BinCode, OUT_WhsCode, OUT_BinCode, InStock, SoCT_NhapXuat, DocDate_NhapXuat, TenLoaiCT, DocType, DocEntry, DocLineNum);

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SAP_INOUT_ItemCode' AND object_id = OBJECT_ID('dbo.SAP_INOUT'))
    DROP INDEX IX_SAP_INOUT_ItemCode ON dbo.SAP_INOUT;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_INBOUND_sku_whseid_Detail' AND object_id = OBJECT_ID('dbo.WMS_INBOUND'))
    CREATE INDEX IX_WMS_INBOUND_sku_whseid_Detail ON dbo.WMS_INBOUND (sku, _whseid)
        INCLUDE (toloc, conditioncode, externreceiptkey, datereceived, adddate, type, qtyreceivedpcs);

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_INBOUND_sku_whseid' AND object_id = OBJECT_ID('dbo.WMS_INBOUND'))
    DROP INDEX IX_WMS_INBOUND_sku_whseid ON dbo.WMS_INBOUND;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_OUTBOUND_sku_whseid_Detail' AND object_id = OBJECT_ID('dbo.WMS_OUTBOUND'))
    CREATE INDEX IX_WMS_OUTBOUND_sku_whseid_Detail ON dbo.WMS_OUTBOUND (sku, _whseid)
        INCLUDE (fromloc, conditioncode, externorderkey, orderkey, orderlinenumber, actualshipdate, adddate, type, shippedqtypcs);

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WMS_OUTBOUND_sku_whseid' AND object_id = OBJECT_ID('dbo.WMS_OUTBOUND'))
    DROP INDEX IX_WMS_OUTBOUND_sku_whseid ON dbo.WMS_OUTBOUND;
