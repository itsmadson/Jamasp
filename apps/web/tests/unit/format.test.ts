import { describe, expect, it } from "vitest";

import { formatConfidence, formatDate, formatNumber, formatPercent } from "../../src/lib/format";

describe("formatNumber", () => {
  it("uses Persian digits for fa", () => {
    expect(formatNumber(148230, "fa")).toBe("۱۴۸٬۲۳۰");
  });

  it("uses Latin digits for en", () => {
    expect(formatNumber(148230, "en")).toBe("148,230");
  });
});

describe("formatDate", () => {
  it("uses the Jalali calendar for fa", () => {
    // 2026-07-29 Gregorian falls in year 1405 of the Jalali calendar.
    expect(formatDate("2026-07-29T12:00:00Z", "fa")).toContain("۱۴۰۵");
  });

  it("uses the Gregorian calendar for en", () => {
    expect(formatDate("2026-07-29T12:00:00Z", "en")).toContain("2026");
  });

  it("renders an em dash for a null timestamp", () => {
    expect(formatDate(null, "en")).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats a ratio as a percentage", () => {
    expect(formatPercent(0.86, "en")).toBe("86%");
  });
});

describe("formatConfidence", () => {
  it("renders an em dash when confidence is unknown", () => {
    // An unscored entity must not read as 0% confidence — that is a different claim.
    expect(formatConfidence(null, "en")).toBe("—");
  });

  it("formats a known score as a percentage", () => {
    expect(formatConfidence(0.95, "en")).toBe("95%");
  });
});
