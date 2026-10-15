/*
 * Goi API dung chung. Moi trang goi qua Api.* thay vi tu ghep URL / $.getJSON.
 *   Api.get(ENDPOINTS.reports.inventory.kpi, { whs: "WH104" })   -> jqXHR (promise)
 *   Api.url(path, params)                                        -> URL tuyet doi (bo tham so rong)
 *   Api.post(path, data)                                         -> POST kem CSRF token (thao tac ghi)
 *   Api.download(path, params)                                   -> tai file (xuat Excel)
 *   Api.dataTableSource(path, getParams, cache)                  -> ham ajax cho DataTables server-side
 */
const Api = (function () {
  function fullPath(path) {
    return `${ENDPOINTS.API_BASE}${path}`;
  }

  function url(path, params) {
    const u = new URL(fullPath(path), window.location.origin);
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== "") u.searchParams.set(k, v);
    });
    return u.toString();
  }

  function get(path, params) {
    return $.getJSON(fullPath(path), params);
  }

  function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : $("[name=csrfmiddlewaretoken]").val();
  }

  function post(path, data) {
    return $.ajax({ url: fullPath(path), method: "POST", data: data || {}, dataType: "json", headers: { "X-CSRFToken": csrfToken() } });
  }

  function download(path, params) {
    window.location.href = url(path, params);
  }

  /** Bo nho dem trang da xem cho bang DataTables (mat khi roi trang). */
  function createPageCache(maxEntries) {
    const store = new Map();
    const limit = maxEntries || APP.PAGE_CACHE_MAX;
    return {
      get: (key) => store.get(key),
      has: (key) => store.has(key),
      set(key, value) {
        if (store.size >= limit) store.delete(store.keys().next().value);
        store.set(key, value);
      },
      clear: () => store.clear(),
    };
  }

  /**
   * Nguon du lieu cho DataTables server-side, co cache theo tham so (khong tinh "draw").
   * getParams(): bo loc hien tai cua trang; cache: tu createPageCache (bo qua -> khong cache).
   */
  function dataTableSource(path, getParams, cache) {
    return function (d, callback) {
      const draw = d.draw;
      const params = Object.assign({}, d, getParams ? getParams() : {});
      delete params.draw;
      const key = `${path}?${$.param(params)}`;
      if (cache && cache.has(key)) {
        callback(Object.assign({}, cache.get(key), { draw }));
        return null;
      }
      return get(path, Object.assign({ draw }, params))
        .done((json) => {
          if (cache) cache.set(key, json);
          callback(json);
        })
        .fail(() => callback({ draw, recordsTotal: 0, recordsFiltered: 0, data: [] }));
    };
  }

  return { url, get, post, download, createPageCache, dataTableSource };
})();
