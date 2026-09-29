import { buildDashboardDataset, filterAndSortRows } from "@/utils/mockDashboard";

describe("mockDashboard", () => {
  it("应生成完整 ETF 数据集", () => {
    const dataset = buildDashboardDataset(30);
    expect(dataset.tradeDates).toHaveLength(30);
    expect(dataset.rows).toHaveLength(50);
    expect(Object.keys(dataset.rows[0].dailyMatrix)).toHaveLength(30);
  });

  it("应支持按分组筛选并按最新交易日排序", () => {
    const dataset = buildDashboardDataset(30);
    const rows = filterAndSortRows(dataset, {
      tradeDate: dataset.tradeDate,
      group: "科技通信",
      keyword: "",
      sortField: "latestDay",
      sortOrder: "desc",
    });

    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.group === "科技通信")).toBe(true);
    expect(rows[0].dailyMatrix[dataset.tradeDates[29]]).toBeGreaterThanOrEqual(
      rows[rows.length - 1].dailyMatrix[dataset.tradeDates[29]],
    );
  });
});
