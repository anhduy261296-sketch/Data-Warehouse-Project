-- Bao cao > E-commerce: doanh thu KHONG tru hang tra (doi tu 0024). Dinh nghia lai view dbo.ECOM_ORDER_LINES.
--   net_amount / net_qty: chi dong ban (order_type = Sales), khong KM, khong huy; dong tra hang (Return) = 0
--   (dong tra hang van nam trong view: bang chi tiet, dem don tra hang o KPI)
--   status_group: success (Delivered, Shipped) | cancel | return | processing
EXEC(N'
CREATE OR ALTER VIEW dbo.ECOM_ORDER_LINES AS
SELECT
    o._row_id,
    o.order_number,
    o.order_type,
    CASE WHEN o.order_type = ''Return'' THEN N''Trả'' ELSE N''Bán'' END AS line_type,
    CAST(o.status AS NVARCHAR(50)) AS status,
    g.status_group,
    CASE g.status_group WHEN ''success'' THEN N''Thành công'' WHEN ''cancel'' THEN N''Hủy''
         WHEN ''return'' THEN N''Trả hàng'' ELSE N''Đang xử lý'' END AS status_group_label,
    k.sales_channel,
    CASE WHEN c.operation = ''online'' AND ISNULL(c.display_name, N'''') <> N'''' THEN c.display_name ELSE k.sales_channel END AS channel_name,
    k.shop_id,
    CAST(ISNULL(NULLIF(o.shop_name, N''''), k.sales_channel + N'' '' + k.shop_id) AS NVARCHAR(200)) AS shop_name,
    o.employee_code,
    CAST(o.employee_name AS NVARCHAR(200)) AS employee_name,
    o._k_created_at AS created_at_utc,
    DATEADD(HOUR, 7, o._k_created_at) AS created_at,
    k.sku,
    CAST(ISNULL(i.ItemName, o.logistic_sku_name) AS NVARCHAR(400)) AS item_name,
    CASE WHEN o.item_type_display = ''KM'' THEN 1 ELSE 0 END AS is_gift,
    CASE WHEN o.item_type_display = ''KM'' THEN N''KM'' ELSE N''Hàng bán'' END AS item_kind,
    q.quantity,
    q.amount,
    q.amount_before_vat,
    CASE WHEN o.item_type_display = ''KM'' OR g.status_group = ''cancel'' OR o.order_type = ''Return'' THEN 0
         ELSE q.quantity END AS net_qty,
    CASE WHEN o.item_type_display = ''KM'' OR g.status_group = ''cancel'' OR o.order_type = ''Return'' THEN 0
         ELSE q.amount END AS net_amount
FROM dbo.OMS_ORDERS o
-- cot OMS la NVARCHAR(MAX): ep ve do dai co dinh (thuc te <= 30 ky tu) de GROUP BY / JOIN nhanh
CROSS APPLY (
    SELECT CAST(o.sales_channel AS NVARCHAR(50)) AS sales_channel, CAST(o.shop_id AS NVARCHAR(50)) AS shop_id,
           CAST(o.logistic_sku AS NVARCHAR(50)) AS sku
) k
CROSS APPLY (
    SELECT CASE
        WHEN o.status IN (''Delivered'', ''Shipped'') THEN ''success''
        WHEN o.status IN (''Cancelled'', ''Cancel'', ''InCancel'') THEN ''cancel''
        WHEN o.status IN (''PackageReturned'', ''Refunded'', ''Returned'', ''Returning'', ''RefundRejected'', ''PackageReturn'', ''Lostdamaged'') THEN ''return''
        ELSE ''processing'' END AS status_group
) g
CROSS APPLY (
    SELECT TRY_CONVERT(DECIMAL(18, 2), o.quantity) AS quantity,
           TRY_CONVERT(DECIMAL(18, 2), o.total_amount_after_vat) AS amount,
           TRY_CONVERT(DECIMAL(18, 2), o.total_amount_before_vat) AS amount_before_vat
) q
LEFT JOIN dbo.OMS_SALES_CHANNELS c ON c.code = k.sales_channel
LEFT JOIN dbo.SAP_ITEMS i ON i.ItemCode = k.sku
WHERE o.outbound_order_type IN (''L03'', ''L04'')
');
