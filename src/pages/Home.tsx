import { useCallback, useEffect, useMemo, useState } from "react";
import { DashboardTable } from "@/components/DashboardTable";
import { TradeDateCalendar } from "@/components/TradeDateCalendar";
import { readJsonSafely } from "@/lib/http";
import { TIER_ORDER, TIER_STYLE } from "@/components/tierColors";
import type { DashboardDataset } from "@/types/dashboard";

const REALTIME_POLL_INTERVAL_MS = 300_000;

const FOOTER_NAV_ITEMS = [
  {
    title: "全天候量化看板",
    domain: "all-weather.dajitui.vip",
    href: "https://all-weather.dajitui.vip",
    theme: "from-[#edf2ff] to-[#e8efff]",
    accent: "bg-[#cfdcff]",
  },
  {
    title: "网格交易看板",
    domain: "grid.dajitui.vip",
    href: "https://grid.dajitui.vip",
    theme: "from-[#eefaf9] to-[#e7f6f4]",
    accent: "bg-[#cfeeed]",
  },
  {
    title: "大盘情绪看板",
    domain: "emotion.dajitui.vip",
    href: "https://emotion.dajitui.vip/?",
    theme: "from-[#f6eefc] to-[#f0e8f8]",
    accent: "bg-[#ead6f7]",
  },
  {
    title: "ETF动量排名看板",
    domain: "etf.dajitui.vip",
    href: "https://etf.dajitui.vip/",
    theme: "from-[#faf4ea] to-[#f5eee3]",
    accent: "bg-[#f3dfc7]",
  },
  {
    title: "动量轮动看板",
    domain: "momentum.dajitui.vip",
    href: "https://momentum.dajitui.vip",
    theme: "from-[#edf3ff] to-[#e9f0ff]",
    accent: "bg-[#d6e2ff]",
  },
  {
    title: "个股热榜",
    domain: "hot.dajitui.vip",
    href: "https://hot.dajitui.vip",
    theme: "from-[#fcf1eb] to-[#f8ece5]",
    accent: "bg-[#f4d8ca]",
  },
] as const;

const getTodayTradeDate = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export default function Home() {
  const [dataset, setDataset] = useState<DashboardDataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [overlayMessage, setOverlayMessage] = useState<string | null>(null);
  const [pendingTradeDate, setPendingTradeDate] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [activeSearchCode, setActiveSearchCode] = useState<string | null>(null);
  const [syncingDashboard, setSyncingDashboard] = useState(false);

  const fetchDashboard = useCallback(async (tradeDate?: string, code?: string | null, background = false) => {
    if (!background) {
      setLoading(true);
      setError(null);
    }

    try {
      const search = new URLSearchParams();
      if (tradeDate) {
        search.set("trade_date", tradeDate);
      }
      if (code) {
        search.set("code", code);
      }

      const response = await fetch(`/api/dashboard${search.toString() ? `?${search.toString()}` : ""}`);
      const payload = await readJsonSafely<DashboardDataset & { detail?: string }>(response);

      if (!response.ok) {
        throw new Error(payload?.detail || "看板接口请求失败");
      }

      if (!payload) {
        throw new Error("看板接口返回空响应");
      }

      setDataset(payload);
      setActiveSearchCode(payload.selectedCode || null);
      return payload;
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : background ? "后台刷新失败" : "加载数据失败");
      return null;
    } finally {
      if (!background) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  useEffect(() => {
    if (!dataset?.realtime?.active) {
      return;
    }

    const timer = window.setInterval(() => {
      if (document.hidden) {
        return;
      }
      void fetchDashboard(undefined, activeSearchCode, true);
    }, REALTIME_POLL_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [activeSearchCode, dataset?.realtime?.active, fetchDashboard]);

  const handleTradeDateSelect = useCallback(
    async (tradeDate: string) => {
      if (!dataset || tradeDate === dataset.tradeDate || pendingTradeDate) {
        setCalendarOpen(false);
        return;
      }

      setPendingTradeDate(tradeDate);
      setCalendarOpen(false);
      setError(null);
      setSyncMessage(null);

      try {
        const todayTradeDate = getTodayTradeDate();
        if (dataset.realtime?.enabled && tradeDate === todayTradeDate) {
          await fetchDashboard(undefined, activeSearchCode);
          return;
        }

        const statusResponse = await fetch(`/api/trade-date-status?trade_date=${encodeURIComponent(tradeDate)}`);
        const statusPayload = await readJsonSafely<{ ready?: boolean; detail?: string }>(statusResponse);
        if (!statusResponse.ok) {
          throw new Error(statusPayload?.detail || "交易日状态检查失败");
        }

        if (!statusPayload?.ready) {
          setOverlayMessage(`正在下载 ${tradeDate} 的历史数据，请稍候...`);
          const ensureResponse = await fetch(`/api/admin/ensure-trade-date?trade_date=${encodeURIComponent(tradeDate)}`, {
            method: "POST",
          });
          const ensurePayload = await readJsonSafely<{ detail?: string }>(ensureResponse);

          if (!ensureResponse.ok) {
            throw new Error(ensurePayload?.detail || "历史数据下载失败");
          }
        }

        if (activeSearchCode) {
          const etfStatusResponse = await fetch(
            `/api/etf-status?code=${encodeURIComponent(activeSearchCode)}&trade_date=${encodeURIComponent(tradeDate)}`,
          );
          const etfStatusPayload = await readJsonSafely<{ ready?: boolean; detail?: string }>(etfStatusResponse);
          if (!etfStatusResponse.ok) {
            throw new Error(etfStatusPayload?.detail || "搜索ETF状态检查失败");
          }

          if (!etfStatusPayload?.ready) {
            setOverlayMessage(`正在补齐 ETF ${activeSearchCode} 在 ${tradeDate} 的历史数据，请稍候...`);
            const ensureEtfResponse = await fetch(
              `/api/admin/ensure-etf?code=${encodeURIComponent(activeSearchCode)}&trade_date=${encodeURIComponent(tradeDate)}`,
              { method: "POST" },
            );
            const ensureEtfPayload = await readJsonSafely<{ detail?: string }>(ensureEtfResponse);
            if (!ensureEtfResponse.ok) {
              throw new Error(ensureEtfPayload?.detail || "搜索ETF历史数据下载失败");
            }
          }
        }

        await fetchDashboard(tradeDate, activeSearchCode);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "切换交易日失败");
      } finally {
        setOverlayMessage(null);
        setPendingTradeDate(null);
      }
    },
    [activeSearchCode, dataset, fetchDashboard, pendingTradeDate],
  );

  const handleSearch = useCallback(async () => {
    if (!dataset) {
      return;
    }

    const code = searchInput.trim();
    if (!/^\d{6}$/.test(code)) {
      setError("请输入6位ETF代码");
      return;
    }

    setError(null);
    setSyncMessage(null);
    setCalendarOpen(false);

    try {
      const referenceTradeDate = dataset.realtime?.active ? dataset.availableTradeDates[0] : dataset.tradeDate;
      const statusResponse = await fetch(
        `/api/etf-status?code=${encodeURIComponent(code)}&trade_date=${encodeURIComponent(referenceTradeDate ?? dataset.tradeDate)}`,
      );
      const statusPayload = await readJsonSafely<{ ready?: boolean; detail?: string }>(statusResponse);
      if (!statusResponse.ok) {
        throw new Error(statusPayload?.detail || "ETF状态检查失败");
      }

      if (!statusPayload?.ready) {
        setOverlayMessage(`正在下载 ETF ${code} 的历史数据，请稍候...`);
        const ensureTradeDate = referenceTradeDate ?? dataset.tradeDate;
        const ensureResponse = await fetch(
          `/api/admin/ensure-etf?code=${encodeURIComponent(code)}&trade_date=${encodeURIComponent(ensureTradeDate)}`,
          { method: "POST" },
        );
        const ensurePayload = await readJsonSafely<{ detail?: string }>(ensureResponse);

        if (!ensureResponse.ok) {
          throw new Error(ensurePayload?.detail || "ETF历史数据下载失败");
        }
      }

      await fetchDashboard(dataset.realtime?.active ? undefined : dataset.tradeDate, code);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "ETF搜索失败");
    } finally {
      setOverlayMessage(null);
    }
  }, [dataset, fetchDashboard, searchInput]);

  const handleResetSearch = useCallback(async () => {
    if (!dataset || !activeSearchCode) {
      return;
    }
    setSearchInput("");
    setSyncMessage(null);
    await fetchDashboard(dataset.realtime?.active ? undefined : dataset.tradeDate, null);
  }, [activeSearchCode, dataset, fetchDashboard]);

  const handleManualSync = useCallback(async () => {
    if (syncingDashboard) {
      return;
    }

    const previousTradeDate = dataset?.tradeDate ?? null;
    setSyncingDashboard(true);
    setCalendarOpen(false);
    setError(null);
    setSyncMessage(null);
    setOverlayMessage("正在同步最新正式数据，请稍候...");

    try {
      const syncResponse = await fetch("/api/admin/sync", { method: "POST" });
      const syncPayload = await readJsonSafely<{ detail?: string }>(syncResponse);
      if (!syncResponse.ok) {
        throw new Error(syncPayload?.detail || "手工同步失败");
      }

      const refreshed = await fetchDashboard(undefined, activeSearchCode);
      if (!refreshed) {
        throw new Error("同步完成，但刷新看板失败");
      }

      const latestOfficialTradeDate = refreshed.latestOfficialTradeDate || refreshed.tradeDate;
      if (previousTradeDate && latestOfficialTradeDate !== previousTradeDate) {
        setSyncMessage(`同步完成，最新正式展示已更新至 ${latestOfficialTradeDate}。`);
      } else {
        setSyncMessage(`同步完成，当前最新正式展示仍为 ${latestOfficialTradeDate}，今日正式数据可能尚未就绪。`);
      }
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "手工同步失败");
    } finally {
      setOverlayMessage(null);
      setSyncingDashboard(false);
    }
  }, [activeSearchCode, dataset?.tradeDate, fetchDashboard, syncingDashboard]);

  const filteredRows = useMemo(() => {
    if (!dataset) {
      return [];
    }
    const latestDate = dataset.tradeDate;
    return [...dataset.rows].sort((left, right) => {
      const leftValue = left.dailyMatrix[latestDate] ?? Number.NEGATIVE_INFINITY;
      const rightValue = right.dailyMatrix[latestDate] ?? Number.NEGATIVE_INFINITY;
      return rightValue - leftValue;
    });
  }, [dataset]);

  const latestTradeDate = dataset?.tradeDate || "--";
  const metricName = dataset?.metricName || "20日斜率动量";
  const availableTradeDates = dataset?.availableTradeDates || [];
  const realtimeStatus = dataset?.realtime;

  const realtimeDescription = useMemo(() => {
    if (!realtimeStatus?.enabled) {
      return null;
    }
    const realtimeAsOf = realtimeStatus.asOf || realtimeStatus.as_of || "--";
    if (realtimeStatus.active) {
      return `当前处于盘中实时模式，300秒窗口内仅展示临时表数据，最新快照时间：${realtimeAsOf}`;
    }
    if (realtimeStatus.stale) {
      return "实时临时快照已超过300秒且刷新失败，当前已回退到正式收盘口径。";
    }
    return null;
  }, [realtimeStatus]);

  return (
    <main className="min-h-screen bg-[#efefe8] px-2 py-3 text-[#4b5563] sm:px-3 lg:px-4">
      {overlayMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(17,24,39,0.28)] px-4">
          <div className="flex min-w-[300px] max-w-[420px] flex-col items-center gap-3 rounded-xl border border-[#d8ddcf] bg-[#f7f8f2] px-6 py-8 shadow-xl">
            <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-[#d1d5db] border-t-[#4b5563]" />
            <div className="text-[15px] font-semibold text-[#111827]">数据在下载中</div>
            <div className="text-center text-[13px] leading-6 text-[#4b5563]">{overlayMessage}</div>
          </div>
        </div>
      )}

      <div className="mx-auto flex max-w-[1800px] flex-col gap-6">
        <section className="rounded-md border border-[#d8ddcf] bg-[#f7f8f2] px-3 py-3 shadow-sm sm:px-4">
          <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_236px] lg:items-start lg:gap-3 xl:grid-cols-[minmax(0,1fr)_248px]">
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-[#d8ddcf] bg-white px-2 py-1 text-[11px] font-semibold tracking-[0.08em] text-[#4b5563]">
                  ETF 动量看板
                </span>
                <span className="inline-flex items-center rounded-full border border-[#ebece3] bg-[#f1f2ea] px-2 py-1 text-[11px] font-medium text-[#6b7280]">
                  固定 ETF 池 · 最近 30 个交易日
                </span>
              </div>

              <h1 className="max-w-[18ch] text-[28px] font-semibold leading-[1.35] tracking-tight text-[#111827] sm:max-w-none sm:text-[22px]">
                主流ETF20日动量排名统计表 - 大鸡腿V2.0版
              </h1>

              <p className="text-[12px] leading-6 text-[#4b5563] sm:text-[13px]">
                以<span className="font-semibold text-[#1f2937]">{metricName}</span>为核心展示指标，统计固定ETF池最近
                <span className="font-semibold text-[#1f2937]">30个交易日</span>的20日斜率动量矩阵，日期按
                <span className="font-semibold text-[#1f2937]">从近到远、从左到右</span>排列。
              </p>

              <p className="text-[12px] leading-6 text-[#4b5563] sm:text-[13px]">
                数据口径：20日斜率动量=对最近20个交易日收盘价取对数后，按权重从1线性增至2做加权最小二乘回归，
                年化斜率乘以加权拟合优度R²。当前最新交易日：
                <span className="font-semibold text-[#1f2937]">{latestTradeDate}</span>，
                最近更新时间：
                <span className="font-semibold text-[#1f2937]">{dataset?.updatedAt || "--"}</span>。
              </p>

              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#6b7280]">
                <span className="font-semibold text-[#4b5563]">动量档位：</span>
                {TIER_ORDER.map((tier) => (
                  <span key={tier} className="flex items-center gap-1">
                    <span
                      className="inline-block h-3.5 w-3.5 rounded-sm border border-[#d9dccf]"
                      style={{ backgroundColor: TIER_STYLE[tier].bg }}
                    />
                    <span className="tabular-nums text-[#9ca3af]">{tier}</span>
                  </span>
                ))}
                <span className="ml-1 text-[#9ca3af]">（绿=最弱 · 红=最强；格子内数字为全池名次，下方小字为动量值；全池共 {dataset?.poolSize ?? "--"} 只）</span>
              </div>

              {realtimeDescription && (
                <p className={`text-[12px] ${realtimeStatus?.active ? "text-[#1f6b3d]" : "text-[#92400e]"}`}>{realtimeDescription}</p>
              )}
              {error && <p className="text-[12px] text-[#b91c1c]">异常：{error}</p>}
              {syncMessage && !error && <p className="text-[12px] text-[#1f6b3d]">{syncMessage}</p>}
            </div>

            <div className="flex w-full shrink-0 flex-col gap-2.5 lg:w-[236px] xl:w-[248px]">
              <div className="grid gap-2 grid-cols-1 lg:grid-cols-1">
                <button
                  type="button"
                  onClick={() => {
                    void handleManualSync();
                  }}
                  disabled={loading || syncingDashboard || Boolean(pendingTradeDate)}
                  className="inline-flex h-10 w-full items-center justify-center rounded-md border border-[#d8ddcf] bg-white px-3 py-2 text-[12px] font-semibold text-[#374151] shadow-sm transition hover:border-[#c5ccbc] hover:bg-[#fcfcf8] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {syncingDashboard ? "同步中..." : "同步今日数据"}
                </button>

                <div className="relative shrink-0">
                  <button
                    type="button"
                    onClick={() => setCalendarOpen((value) => !value)}
                    disabled={Boolean(pendingTradeDate) || syncingDashboard}
                    className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-[#d8ddcf] bg-white px-3 py-2 text-[12px] font-medium text-[#374151] shadow-sm transition hover:border-[#c5ccbc] hover:bg-[#fcfcf8] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <svg viewBox="0 0 20 20" className="h-4 w-4 text-[#6b7280]" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <rect x="3.5" y="4.5" width="13" height="12" rx="2" />
                      <path d="M6.5 2.8V6M13.5 2.8V6M3.5 8.2H16.5" strokeLinecap="round" />
                    </svg>
                    <span>{pendingTradeDate || latestTradeDate}</span>
                  </button>

                  {calendarOpen && availableTradeDates.length > 0 && (
                    <TradeDateCalendar
                      availableTradeDates={availableTradeDates}
                      selectedTradeDate={latestTradeDate}
                      disabled={Boolean(pendingTradeDate) || syncingDashboard}
                      onSelect={(tradeDate) => {
                        void handleTradeDateSelect(tradeDate);
                      }}
                    />
                  )}
                </div>
              </div>

              <div className="w-full rounded-md border border-[#d8ddcf] bg-[#f3f4ed] p-2 lg:p-1.5">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold tracking-[0.06em] text-[#6b7280]">池外ETF检索</div>
                  <div className="text-right text-[11px] text-[#6b7280]">
                    {activeSearchCode ? `当前临时展示：${activeSearchCode}` : "未搜索时展示默认ETF集合"}
                  </div>
                </div>

                <div className="flex flex-col gap-2 rounded-md border border-[#d8ddcf] bg-white px-2 py-2 shadow-sm sm:flex-row sm:items-center lg:flex-row lg:gap-1.5 lg:px-1.5 lg:py-1.5">
                  <input
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void handleSearch();
                      }
                    }}
                    placeholder="输入ETF六位代码"
                    className="h-8 min-w-0 flex-1 border-0 bg-transparent px-1 text-[13px] text-[#374151] outline-none placeholder:text-[#9ca3af] lg:h-7 lg:px-0.5 lg:text-[12px]"
                  />

                  <div className="flex items-center gap-2 sm:shrink-0 lg:gap-1.5">
                    {activeSearchCode && (
                      <button
                        type="button"
                        onClick={() => {
                          void handleResetSearch();
                        }}
                        className="inline-flex h-8 flex-1 items-center justify-center rounded-md border border-[#e1e4d8] px-2 text-[11px] font-medium text-[#6b7280] transition hover:border-[#c5ccbc] hover:bg-[#f7f8f2] sm:flex-none lg:h-7 lg:px-1.5 lg:text-[10px]"
                      >
                        恢复默认
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        void handleSearch();
                      }}
                      disabled={!dataset || loading || syncingDashboard || Boolean(pendingTradeDate)}
                      className="inline-flex h-8 flex-1 items-center justify-center rounded-md bg-[#3f4d3f] px-4 text-[12px] font-semibold text-white transition hover:bg-[#334033] disabled:cursor-not-allowed disabled:bg-[#9ca3af] sm:flex-none lg:h-7 lg:px-2.5 lg:text-[11px]"
                    >
                      搜索
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {dataset ? (
          <DashboardTable
            rows={filteredRows}
            tradeDates={dataset.tradeDates}
            selectedTradeDate={dataset.tradeDate}
            realtime={dataset.realtime}
            poolSize={dataset.poolSize}
          />
        ) : (
          <section className="rounded-md border border-dashed border-[#d8ddcf] bg-[#f5f6ef] px-6 py-10 text-sm text-[#6b7280]">
            {loading ? "正在加载后端数据..." : error || "暂无数据，请等待定时更新或后端同步完成。"}
          </section>
        )}

        <section className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {FOOTER_NAV_ITEMS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                target="_blank"
                rel="noreferrer"
                className={`group relative overflow-hidden rounded-[18px] border border-[#d8ddcf] bg-gradient-to-br ${item.theme} px-4 py-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md`}
              >
                <span
                  className={`pointer-events-none absolute -bottom-3 -right-3 h-14 w-14 rounded-full opacity-65 transition group-hover:scale-105 ${item.accent}`}
                />
                <span className="relative block text-[11px] font-semibold tracking-[0.06em] text-[#8b95a7]">相关导航</span>
                <strong className="relative mt-1 block text-[16px] font-semibold tracking-tight text-[#24324b]">{item.title}</strong>
                <span className="relative mt-1 block text-[12px] text-[#6f7a8d]">{item.domain}</span>
              </a>
            ))}
          </div>

          <section className="rounded-[22px] border border-[#d8ddcf] bg-[#f7f8f2] px-4 py-4 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0 flex-1">
                <h3 className="text-[22px] font-semibold tracking-tight text-[#22314a]">交流与反馈</h3>
                <p className="mt-2 max-w-[78ch] text-[13px] leading-7 text-[#5b6474]">
                  欢迎扫码进群交流，获取最新策略动态、量化研究思路和产品更新通知；如果二维码失效，也可以直接添加微信沟通。
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-[#edf2ff] px-3 py-1 text-[12px] font-medium text-[#4b5f9a]">
                    扫码进群交流
                  </span>
                  <span className="inline-flex items-center rounded-full bg-[#edf2ff] px-3 py-1 text-[12px] font-semibold text-[#4b5f9a]">
                    微信号: Code_Mvp
                  </span>
                </div>
                <div className="mt-3 text-[12px] text-[#6b7280]">进群后可交流策略想法、页面建议和功能反馈。</div>
              </div>

              <div className="self-start rounded-2xl border border-[#d8ddcf] bg-white p-2 shadow-sm">
                <img className="h-28 w-28 rounded-xl object-cover" src="/wechat_qr.jpg" alt="大鸡腿策略馆微信二维码" />
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
