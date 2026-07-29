import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import fa from "../../messages/fa.json";
import { directionFor, routing } from "../../src/i18n/routing";

function flatten(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n", () => {
  it("defaults to Persian", () => {
    expect(routing.defaultLocale).toBe("fa");
    expect(routing.locales).toEqual(["fa", "en"]);
  });

  it("maps Persian to RTL and English to LTR", () => {
    expect(directionFor("fa")).toBe("rtl");
    expect(directionFor("en")).toBe("ltr");
  });

  it("has identical key sets in both catalogs", () => {
    // A missing key ships as a raw key name to a user. Catch it here, not in prod.
    expect(flatten(en).sort()).toEqual(flatten(fa).sort());
  });

  it("has no empty translations", () => {
    const empties = Object.entries({ fa, en }).flatMap(([locale, catalog]) =>
      JSON.stringify(catalog).includes('""') ? [locale] : [],
    );
    expect(empties).toEqual([]);
  });
});
