import { describe, expect, it } from "vitest";

import { formatRemaining } from "./format";

describe("formatRemaining", () => {
  it("formatRemaining_everyScale_showsTickingSeconds", () => {
    expect(formatRemaining(299_000)).toBe("04:59");
    expect(formatRemaining((23 * 3600 + 4 * 60 + 59) * 1000)).toBe("23:04:59");
    expect(formatRemaining(((6 * 24 + 23) * 3600 + 4 * 60 + 59) * 1000)).toBe("6 d 23:04:59");
  });

  it("formatRemaining_pastDeadline_showsZero", () => {
    expect(formatRemaining(-5000)).toBe("00:00");
  });
});
