import type { DashboardRealtimeState, DashboardRow } from "@/types/dashboard";
import { HeatCell } from "@/components/HeatCell";

interface DashboardTableProps {
  rows: DashboardRow[];
  tradeDates: string[];
  selectedTradeDate: string;
  realtime?: DashboardRealtimeState;
  poolSize?: number;
}

const formatTradeDate = (tradeDate: string) => tradeDate.slice(5);

export function DashboardTable({ rows, tradeDates, selectedTradeDate, realtime, poolSize }: DashboardTableProps) {
  const displayTradeDates = [...tradeDates].reverse();

  return (
    <section className="rounded-md border border-[#d8ddcf] bg-[#f5f6ef] shadow-sm">
      <div className="max-h-[calc(100vh-220px)] overflow-auto rounded-md">
        <table className="min-w-full border-separate border-spacing-0">
          <thead className="bg-[#f5f6ef]">
            <tr>
              <th className="sticky top-0 z-40 w-[180px] border-b border-r border-[#d8ddcf] bg-[#f5f6ef] px-3 py-2 text-left text-[11px] font-semibold text-[#6b7280]">
                名称
              </th>
              <th className="sticky top-0 z-40 w-[84px] border-b border-r border-[#d8ddcf] bg-[#f5f6ef] px-2 py-2 text-left text-[11px] font-semibold text-[#6b7280]">
                代码
              </th>
              {displayTradeDates.map((tradeDate) => (
                <th
                  key={tradeDate}
                  className="sticky top-0 z-30 border-b border-r border-[#d8ddcf] bg-[#f5f6ef] px-1 py-2 text-center text-[11px] font-semibold text-[#6b7280]"
                >
                  <div className="flex flex-col items-center gap-0.5">
                    <span>{formatTradeDate(tradeDate)}</span>
                    {realtime?.active && tradeDate === selectedTradeDate ? (
                      <span className="rounded bg-[#dcefdc] px-1.5 py-[1px] text-[10px] font-semibold leading-none text-[#1f6b3d]">
                        实时
                      </span>
                    ) : null}
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.map((row, index) => {
              const displayRank = row.dailyRank?.[selectedTradeDate] ?? index + 1;

              return (
                <tr key={row.fullCode} className="group">
                  <td className="z-10 border-b border-r border-[#e1e4d8] bg-[#fafbf5] px-3 py-2 text-[12px] text-[#4b5563]">
                    <div className="flex items-center gap-2 font-medium text-[#374151]">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="shrink-0 tabular-nums text-[#6b7280]">{displayRank}.</span>
                        <span className="truncate">{row.name}</span>
                      </span>
                    </div>
                  </td>

                  <td className="z-10 border-b border-r border-[#e1e4d8] bg-[#fafbf5] px-2 py-2 text-[12px] text-[#6b7280]">
                    {row.code}
                  </td>

                  {displayTradeDates.map((tradeDate) => (
                    <td key={`${row.fullCode}-${tradeDate}`} className="border-b border-r border-[#e1e4d8] p-0.5">
                      <HeatCell
                        value={row.dailyMatrix[tradeDate]}
                        rank={row.dailyRank?.[tradeDate] ?? null}
                        tier={row.dailyTier?.[tradeDate] ?? null}
                        poolSize={poolSize ?? null}
                        compact
                      />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
