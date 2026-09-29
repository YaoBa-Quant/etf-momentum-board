import { getTradingDays } from "@/utils/tradingDays";

describe("getTradingDays", () => {
  it("应返回指定数量的交易日", () => {
    const days = getTradingDays(5, new Date("2026-07-17T00:00:00"));
    expect(days).toHaveLength(5);
    expect(days[0]).toBe("2026-07-13");
    expect(days[4]).toBe("2026-07-17");
  });

  it("应跳过周末", () => {
    const days = getTradingDays(3, new Date("2026-07-20T00:00:00"));
    expect(days).toEqual(["2026-07-16", "2026-07-17", "2026-07-20"]);
  });
});
