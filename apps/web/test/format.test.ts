import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatMinutes,
  formatMs,
  formatNumber,
  formatPercent,
  formatRatio,
  formatRelative,
  formatTokens,
  formatUsd,
  initials,
  toNumber,
} from "@/lib/format";

describe("numbers", () => {
  it("groups thousands and handles missing values", () => {
    expect(formatNumber(14923)).toBe("14,923");
    expect(formatNumber(null)).toBe("n/a");
    expect(formatNumber(Number.NaN)).toBe("n/a");
  });
  it("shows ratios and percentages with one decimal, dropping .0", () => {
    expect(formatRatio(0.2462)).toBe("24.6%");
    expect(formatRatio(1)).toBe("100%");
    expect(formatPercent(60)).toBe("60%");
    expect(formatRatio(undefined)).toBe("n/a");
  });
  it("sizes bytes in B, KB and MB", () => {
    expect(formatBytes(812)).toBe("812 B");
    expect(formatBytes(4300)).toBe("4.2 KB");
    expect(formatBytes(12 * 1024 * 1024)).toBe("12 MB");
  });
});

describe("dates", () => {
  const now = new Date("2026-10-28T12:00:00Z");
  it("says how long ago, then falls back to a date", () => {
    expect(formatRelative("2026-10-28T11:59:40Z", now)).toBe("just now");
    expect(formatRelative("2026-10-28T11:55:00Z", now)).toBe("5m ago");
    expect(formatRelative("2026-10-28T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelative("2026-10-26T12:00:00Z", now)).toBe("2d ago");
    expect(formatRelative("2026-09-01T12:00:00Z", now)).toMatch(/Sep 1, 2026/);
    expect(formatRelative(null, now)).toBe("Never");
  });
  it("never throws on bad input", () => {
    expect(formatDateTime("not a date")).toBe("n/a");
    expect(formatDateTime(undefined)).toBe("n/a");
  });
  it("builds avatar initials", () => {
    expect(initials("Avery Chen")).toBe("AC");
    expect(initials("Mei")).toBe("M");
    expect(initials("")).toBe("?");
  });
});

describe("money, tokens and durations", () => {
  it("is honest about tiny AI costs and reads decimal strings", () => {
    expect(formatUsd(0)).toBe("$0");
    expect(formatUsd("0.00042")).toBe("$0.0004");
    expect(formatUsd(0.00001)).toBe("<$0.0001");
    expect(formatUsd("0.0125")).toBe("$0.013");
    expect(formatUsd(0.99)).toBe("$0.99");
    expect(formatUsd("12.4")).toBe("$12.40");
    expect(formatUsd(1240.4)).toBe("$1,240");
    expect(formatUsd(-0.5)).toBe("-$0.5");
    expect(formatUsd(null)).toBe("n/a");
    expect(formatUsd("abc")).toBe("n/a");
  });
  it("parses API decimals", () => {
    expect(toNumber("1.50")).toBe(1.5);
    expect(toNumber("")).toBeNull();
    expect(toNumber(undefined)).toBeNull();
  });
  it("shortens token counts", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(12_400)).toBe("12.4k");
    expect(formatTokens(3_100_000)).toBe("3.1M");
    expect(formatTokens(undefined)).toBe("n/a");
  });
  it("formats spans from seconds to days", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(240)).toBe("4m");
    expect(formatDuration(4800)).toBe("1h 20m");
    expect(formatDuration(7200)).toBe("2h");
    expect(formatDuration(183_600)).toBe("2d 3h");
    expect(formatDuration(-5)).toBe("0s");
    expect(formatDuration(null)).toBe("n/a");
    expect(formatMinutes(90)).toBe("1h 30m");
  });
  it("formats latencies", () => {
    expect(formatMs(320.4)).toBe("320 ms");
    expect(formatMs(1400)).toBe("1.4 s");
    expect(formatMs(undefined)).toBe("n/a");
  });
});
