-- Quy tắc đối soát chuyển từ chuỗi SQL trong services/pipeline/reconciliation.py sang view có version.

-- Muốn đổi cách tính RECON_* thì tạo migration mới CREATE OR ALTER VIEW, không sửa code Python.

EXEC(N'
CREATE OR ALTER VIEW dbo.vw_RECON_ECOM AS
WITH OMS AS (
    SELECT order_number, MAX(status) AS SoStatus,
           SUM(TRY_CONVERT(DECIMAL(18,0), total_amount_after_vat)) AS TotalAmt,
           MAX(TRY_CONVERT(DATETIME2, created_date)) AS OrderDate
    FROM dbo.OMS_ORDERS
    WHERE outbound_order_type IN (''L03'', ''L04'') AND order_type = ''Sales''
    GROUP BY order_number
),
OMS_RETURN AS (
    SELECT ISNULL(NULLIF(original_order_number, ''''), order_number) AS order_number,
           MAX(CASE status WHEN ''Refunded'' THEN 2 WHEN ''PackageReturned'' THEN 1 END) AS ReturnRank
    FROM dbo.OMS_ORDERS
    WHERE outbound_order_type IN (''L03'', ''L04'') AND order_type = ''Return'' AND status IN (''Refunded'', ''PackageReturned'')
    GROUP BY ISNULL(NULLIF(original_order_number, ''''), order_number)
),
SAP_LINES AS (
    SELECT U_SONo, ItemCode, ARNo,
           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''''
                THEN MAX(TRY_CONVERT(DECIMAL(18,0), ARGTotal))
                ELSE SUM(TRY_CONVERT(DECIMAL(18,0), TotalAfVAT))
           END AS ItemAmt
    FROM dbo.SAP_SO_All
    WHERE [Type] = N''Bán hàng''
    GROUP BY U_SONo, ItemCode, ARNo
),
SAP AS (
    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt
    FROM SAP_LINES
    GROUP BY U_SONo
),
WRT AS (
    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,0), TotalAmt)) AS TotalAmt
    FROM dbo.WRT_SO
    GROUP BY order_number
)
SELECT
    o.order_number AS OrderCode,
    o.TotalAmt AS OmsWmsAmount,
    s.TotalAmt AS SapAmount,
    CAST(w.TotalAmt AS DECIMAL(18,0)) AS WrtAmount,
    CASE
        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL AND w.order_number IS NOT NULL
         AND o.TotalAmt = s.TotalAmt AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,0))
         AND o.SoStatus IN (''Shipped'', ''Delivered'')
        THEN ''Sync'' ELSE ''Not Sync''
    END AS StatusSync,
    CASE r.ReturnRank WHEN 2 THEN ''Refunded'' WHEN 1 THEN ''PackageReturned'' ELSE o.SoStatus END AS SoStatus,
    o.OrderDate
FROM OMS o
LEFT JOIN OMS_RETURN r ON r.order_number = o.order_number
LEFT JOIN SAP s ON s.U_SONo = o.order_number
LEFT JOIN WRT w ON w.order_number = o.order_number
');

EXEC(N'
CREATE OR ALTER VIEW dbo.vw_RECON_DMS_DUYET AS
WITH DMS AS (
    SELECT OrderCode, MAX(OrderStatus) AS OrderStatus,
           SUM(CASE WHEN OrderType = ''L14'' THEN -TotalAmtInclVAT ELSE TotalAmtInclVAT END) AS TotalAmt,
           MAX(DocDate) AS OrderDate
    FROM dbo.DMS_SO
    WHERE OrderStatus = ''sale''
    GROUP BY OrderCode
),
OMS AS (
    SELECT order_number,
           SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt
    FROM dbo.OMS_ORDERS
    GROUP BY order_number
),
SAP_LINES AS (
    SELECT U_SONo, ItemCode, ARNo,
           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''''
                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))
                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))
           END AS ItemAmt
    FROM dbo.SAP_SO_All
    GROUP BY U_SONo, ItemCode, ARNo
),
SAP AS (
    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt
    FROM SAP_LINES
    GROUP BY U_SONo
)
SELECT
    d.OrderCode,
    CAST(d.TotalAmt AS DECIMAL(18,2)) AS DmsAmount,
    o.TotalAmt AS OmsWmsAmount,
    s.TotalAmt AS SapAmount,
    CASE
        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL
         AND CAST(d.TotalAmt AS DECIMAL(18,2)) = o.TotalAmt AND o.TotalAmt = s.TotalAmt
        THEN ''Sync'' ELSE ''Not Sync''
    END AS StatusSync,
    d.OrderStatus AS SoStatus,
    d.OrderDate
FROM DMS d
LEFT JOIN OMS o ON o.order_number = d.OrderCode
LEFT JOIN SAP s ON s.U_SONo = d.OrderCode
');

EXEC(N'
CREATE OR ALTER VIEW dbo.vw_RECON_DMS_XUATKHO AS
WITH DMS_DONE AS (
    SELECT OrderCode, MAX(OrderStatus) AS OrderStatus,
           SUM(CASE WHEN OrderType = ''L14'' THEN -TotalAmtInclVAT ELSE TotalAmtInclVAT END) AS TotalAmt
    FROM dbo.DMS_SO
    GROUP BY OrderCode
),
OMS AS (
    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt,
           MAX(TRY_CONVERT(DATETIME2, created_date)) AS OrderDate
    FROM dbo.OMS_ORDERS
    WHERE outbound_order_type IN (''L01'', ''L05'', ''L07'', ''L08'', ''L12'', ''L14'', ''L18'', ''L25'')
    GROUP BY order_number
),
SAP_LINES AS (
    SELECT U_SONo, ItemCode, ARNo,
           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''''
                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))
                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))
           END AS ItemAmt
    FROM dbo.SAP_SO_All
    GROUP BY U_SONo, ItemCode, ARNo
),
SAP AS (
    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt
    FROM SAP_LINES
    GROUP BY U_SONo
),
WRT AS (
    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,4), TotalAmt)) AS TotalAmt
    FROM dbo.WRT_SO
    GROUP BY order_number
)
SELECT
    o.order_number AS OrderCode,
    CAST(d.TotalAmt AS DECIMAL(18,2)) AS DmsAmount,
    o.TotalAmt AS OmsWmsAmount,
    s.TotalAmt AS SapAmount,
    CAST(w.TotalAmt AS DECIMAL(18,2)) AS WrtAmount,
    CASE
        WHEN d.OrderCode IS NOT NULL AND s.U_SONo IS NOT NULL AND w.order_number IS NOT NULL
         AND CAST(d.TotalAmt AS DECIMAL(18,2)) = o.TotalAmt
         AND o.TotalAmt = s.TotalAmt
         AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,2))
        THEN ''Sync'' ELSE ''Not Sync''
    END AS StatusSync,
    d.OrderStatus AS SoStatus,
    o.OrderDate
FROM OMS o
LEFT JOIN DMS_DONE d ON d.OrderCode = o.order_number
LEFT JOIN SAP s ON s.U_SONo = o.order_number
LEFT JOIN WRT w ON w.order_number = o.order_number
');

EXEC(N'
CREATE OR ALTER VIEW dbo.vw_RECON_WRT AS
WITH WRT AS (
    SELECT order_number, MAX(OrderStatus) AS OrderStatus, MAX(Type) AS Type,
           SUM(TRY_CONVERT(DECIMAL(18,4), TotalAmt)) AS TotalAmt,
           MAX(postingDate) AS OrderDate
    FROM dbo.WRT_SO
    WHERE IsCreateBy = ''SYSTEM''
    GROUP BY order_number
),
OMS AS (
    SELECT order_number, SUM(TRY_CONVERT(DECIMAL(18,2), total_amount_after_vat)) AS TotalAmt
    FROM dbo.OMS_ORDERS
    GROUP BY order_number
),
SAP_LINES AS (
    SELECT U_SONo, ItemCode, ARNo,
           CASE WHEN ARNo IS NOT NULL AND ARNo <> ''''
                THEN MAX(TRY_CONVERT(DECIMAL(18,2), ARGTotal))
                ELSE SUM(TRY_CONVERT(DECIMAL(18,2), TotalAfVAT))
           END AS ItemAmt
    FROM dbo.SAP_SO_All
    GROUP BY U_SONo, ItemCode, ARNo
),
SAP AS (
    SELECT U_SONo, SUM(ItemAmt) AS TotalAmt
    FROM SAP_LINES
    GROUP BY U_SONo
)
SELECT
    w.order_number AS OrderCode,
    o.TotalAmt AS OmsWmsAmount,
    s.TotalAmt AS SapAmount,
    CAST(w.TotalAmt AS DECIMAL(18,2)) AS WrtAmount,
    CASE
        WHEN o.order_number IS NOT NULL AND s.U_SONo IS NOT NULL
         AND o.TotalAmt = s.TotalAmt AND s.TotalAmt = CAST(w.TotalAmt AS DECIMAL(18,2))
         AND w.OrderStatus IN (''Shipped'', ''Delivered'', ''done'')
        THEN ''Sync'' ELSE ''Not Sync''
    END AS StatusSync,
    w.OrderStatus AS SoStatus,
    w.Type AS Type,
    w.OrderDate
FROM WRT w
LEFT JOIN OMS o ON o.order_number = w.order_number
LEFT JOIN SAP s ON s.U_SONo = w.order_number
');

EXEC(N'
CREATE OR ALTER VIEW dbo.vw_RECON_INVENTORY AS
WITH S AS (
    SELECT ItemCode, WhsCode, CASE WHEN WhsCode IN (''W114'', ''W998'') THEN '''' ELSE StatusItem END AS StatusItem, MAX(ItemName) AS ItemName, MAX(WhsName) AS WhsName,
           SUM(OnHand) AS Qty, MAX(InvntryUom) AS Uom
    FROM dbo.SAP_INVENTORY
    GROUP BY ItemCode, WhsCode, CASE WHEN WhsCode IN (''W114'', ''W998'') THEN '''' ELSE StatusItem END
),
W AS (
    SELECT sku AS ItemCode, ''W'' + SUBSTRING(whseid, 3, 10) AS WhsCode, CASE WHEN ''W'' + SUBSTRING(whseid, 3, 10) IN (''W114'', ''W998'') THEN '''' ELSE ISNULL(status, '''') END AS StatusItem,
           MAX(description) AS ItemName, SUM(TRY_CONVERT(DECIMAL(21,6), qty)) AS Qty, MAX(uom) AS Uom
    FROM dbo.WMS_INVENTORY
    GROUP BY sku, whseid, CASE WHEN ''W'' + SUBSTRING(whseid, 3, 10) IN (''W114'', ''W998'') THEN '''' ELSE ISNULL(status, '''') END
),
WHS AS (
    SELECT WhsCode, MAX(WhsName) AS WhsName FROM dbo.SAP_INVENTORY GROUP BY WhsCode
)
SELECT
    CASE
        WHEN s.ItemCode IS NOT NULL AND w.ItemCode IS NOT NULL
            THEN CASE WHEN s.Qty = w.Qty THEN N''Khớp'' ELSE N''Lệch'' END
        WHEN s.WhsCode IN (''W101'', ''W999'') THEN N''Không quản lý trên WMS''
        WHEN w.ItemCode IS NULL THEN N''Chỉ có SAP''
        ELSE N''Chỉ có WMS''
    END AS StatusSync,
    COALESCE(s.ItemCode, w.ItemCode) AS ItemCode,
    COALESCE(s.ItemName, w.ItemName) AS ItemName,
    COALESCE(s.WhsCode, w.WhsCode) AS WhsCode,
    COALESCE(s.WhsName, whs.WhsName) AS WhsName,
    COALESCE(s.StatusItem, w.StatusItem) AS StatusItem,
    s.Qty AS SapQty,
    w.Qty AS WmsQty,
    ABS(ISNULL(s.Qty, 0) - ISNULL(w.Qty, 0)) AS DiffQty,
    COALESCE(s.Uom, w.Uom) AS InvntryUom
FROM S s
FULL OUTER JOIN W w ON w.ItemCode = s.ItemCode AND w.WhsCode = s.WhsCode AND w.StatusItem = s.StatusItem
LEFT JOIN WHS whs ON whs.WhsCode = COALESCE(s.WhsCode, w.WhsCode)
');

IF OBJECT_ID('dbo.DQ_Results', 'U') IS NULL
    CREATE TABLE dbo.DQ_Results (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        check_name VARCHAR(100) NOT NULL,
        severity VARCHAR(10) NOT NULL,
        violations INT NOT NULL,
        status VARCHAR(10) NOT NULL,
        detail NVARCHAR(400) NULL,
        checked_at DATETIME2 NOT NULL CONSTRAINT DF_DQ_Results_checked_at DEFAULT SYSUTCDATETIME()
    );
