/* Dinh dang so / ngay gio / HTML dung chung. */

const VN_NUMBER_FORMAT = new Intl.NumberFormat(APP.LOCALE);
// so luong ton: toi da 2 chu so thap phan
const VN_QTY_FORMAT = new Intl.NumberFormat(APP.LOCALE, { maximumFractionDigits: 2 });
const VN_PERCENT_FORMAT = new Intl.NumberFormat(APP.LOCALE, { minimumFractionDigits: 3, maximumFractionDigits: 3 });

/** So tien / so luong cho bang don hang: rong -> "—". */
function formatAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return value;
  }
  return VN_NUMBER_FORMAT.format(num);
}

/** So luong ton (toi da 2 so le): null/undefined -> "—". */
function formatQty(value) {
  return value === null || value === undefined ? "—" : VN_QTY_FORMAT.format(value);
}

function formatPercent(value) {
  return VN_PERCENT_FORMAT.format(value);
}

function renderStatusSyncBadge(value) {
  if (!value) {
    return "—";
  }
  const cssClass = value === APP.STATUS_SYNC.SYNC ? "badge-success" : "badge-danger";
  return `<span class="badge ${cssClass}">${value}</span>`;
}

/** Thoat ky tu HTML truoc khi chen chuoi tu API vao markup. */
function escapeHtml(value) {
  return $("<div>")
    .text(value === null || value === undefined ? "" : value)
    .html();
}

const VN_DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-GB", {
  timeZone: APP.TIMEZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const formatDateTimeCache = new Map();

/** Chuoi ISO -> "dd/mm/yyyy HH:MM:SS" gio Viet Nam. */
function formatDateTime(value) {
  if (!value) {
    return "—";
  }
  let formatted = formatDateTimeCache.get(value);
  if (formatted === undefined) {
    formatted = formatDateTimeUncached(value);
    formatDateTimeCache.set(value, formatted);
  }
  return formatted;
}

function formatDateTimeUncached(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const parts = VN_DATE_TIME_FORMAT.formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get("day")}/${get("month")}/${get("year")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

/** Thoi diem luu UTC khong kem mui gio (SQL Server) -> hien thi gio Viet Nam. */
function formatUtcDateTime(value) {
  if (!value) return "—";
  return formatDateTime(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

/** Bo dau tieng Viet + chu thuong, dung cho tim kiem khong phan biet dau. */
function normalizeSearchText(value) {
  return (value || "").toString().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}
