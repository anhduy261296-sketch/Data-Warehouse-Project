


const VN_DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
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
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  
  
  
  
  
  const parts = VN_DATE_TIME_FORMAT.formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get("day")}/${get("month")}/${get("year")} ${get("hour")}:${get("minute")}:${get("second")}`;
}
