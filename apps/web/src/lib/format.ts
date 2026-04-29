export function fmtCurrency(n: number | undefined | null, currency = "EGP", locale = "en") {
  if (n === undefined || n === null || isNaN(Number(n))) return "—";
  return new Intl.NumberFormat(locale === "ar" ? "ar-EG" : "en-EG", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(n));
}

export function fmtNumber(n: number | undefined | null, locale = "en") {
  if (n === undefined || n === null || isNaN(Number(n))) return "—";
  return new Intl.NumberFormat(locale === "ar" ? "ar-EG" : "en-EG", {
    maximumFractionDigits: 1,
  }).format(Number(n));
}

export function fmtPct(n: number | undefined | null, locale = "en") {
  if (n === undefined || n === null || isNaN(Number(n))) return "—";
  const f = new Intl.NumberFormat(locale === "ar" ? "ar-EG" : "en-EG", {
    maximumFractionDigits: 1,
  }).format(Number(n));
  return `${f}%`;
}

export function compactCurrency(n: number, currency = "EGP", locale = "en") {
  if (n === undefined || n === null || isNaN(Number(n))) return "—";
  return new Intl.NumberFormat(locale === "ar" ? "ar-EG" : "en-EG", {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(n));
}
