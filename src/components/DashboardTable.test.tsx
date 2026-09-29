import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DashboardTable } from "@/components/DashboardTable";
import type { DashboardRow } from "@/types/dashboard";

const row: DashboardRow = {
  name: "沪深300ETF",
  code: "510300",
  fullCode: "510300.SH",
  group: "宽基指数",
  market: "XSHG",
  latestClose: 4.2,
  dailyMatrix: { "2026-07-31": 0.18 },
};

describe("DashboardTable", () => {
  it("ETF 名称仅展示文本，不再提供详情页链接", () => {
    render(
      <MemoryRouter>
        <DashboardTable rows={[row]} tradeDates={["2026-07-31"]} selectedTradeDate="2026-07-31" />
      </MemoryRouter>,
    );

    expect(screen.getByText("沪深300ETF")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /沪深300ETF/ })).not.toBeInTheDocument();
  });
});
