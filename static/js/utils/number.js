const VN_NUMBER_FORMAT = new Intl.NumberFormat("vi-VN");

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

function renderStatusSyncBadge(value) {
  if (!value) {
    return "—";
  }
  const isSync = value === "Sync";
  const cssClass = isSync ? "badge-success" : "badge-danger";
  return `<span class="badge ${cssClass}">${value}</span>`;
}
