import { describe, expect, it } from "vitest";

import { grantRef } from "./watermark";

describe("watermark reference", () => {
  it("test_grantRef_short_uppercase_and_stable", () => {
    expect(grantRef("82e9a883-c0ab-42dc-b9c6-49f7594fd7d2")).toBe("82E9A883");
    expect(grantRef("82e9a883-c0ab-42dc-b9c6-49f7594fd7d2")).toBe(grantRef("82E9A883-C0AB-42DC-B9C6-49F7594FD7D2"));
  });
});
