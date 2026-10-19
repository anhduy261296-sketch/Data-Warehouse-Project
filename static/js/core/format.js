const VN_NUMBER_FORMAT = new Intl.NumberFormat(APP.LOCALE);
const VN_QTY_FORMAT = new Intl.NumberFormat(APP.LOCALE, { maximumFractionDigits: 2 });
const VN_PERCENT_FORMAT = new Intl.NumberFormat(APP.LOCALE, { minimumFractionDigits: 3, maximumFractionDigits: 3 });

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

function formatQty(value) {
  return value === null || value === undefined ? "—" : VN_QTY_FORMAT.format(value);
}

function formatMoneyShort(value, digits) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const units = [
    [1e9, "tỷ"],
    [1e6, "triệu"],
    [1e3, "nghìn"],
  ];
  const unit = units.find(([size]) => Math.abs(n) >= size);
  if (!unit) return VN_NUMBER_FORMAT.format(n);
  const fmt = new Intl.NumberFormat(APP.LOCALE, { maximumFractionDigits: digits === undefined ? 2 : digits });
  return `${fmt.format(n / unit[0])} ${unit[1]}`;
}

function formatRate(value, digits) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toLocaleString(APP.LOCALE, { minimumFractionDigits: digits ?? 1, maximumFractionDigits: digits ?? 1 })}%`;
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

function formatUtcDateTime(value) {
  if (!value) return "—";
  return formatDateTime(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

function normalizeSearchText(value) {
  return (value || "").toString().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}
