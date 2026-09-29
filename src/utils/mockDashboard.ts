import { ETF_POOL } from "@/data/etfPool";
import type { DashboardDataset, DashboardFilterState, DashboardRow, EtfPoolItem } from "@/types/dashboard";
import { getTradingDays } from "@/utils/tradingDays";

const hashCode = (input: string) =>
  input.split("").reduce((acc, char) => acc * 31 + char.charCodeAt(0), 7);

const groupBias: Record<EtfPoolItem["group"], number> = {
  港美海外: 0.18,
  医药医疗: 0.14,
  大宗商品: 0.24,
  临时搜索: 0.0,
  宽基指数: 0.1,
  红利金融地产: 0.08,
  科技通信: 0.2,
  周期制造军工: 0.16,
  消费与主题: 0.12,
};

const round = (value: number, digits = 2) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

const buildDailyMatrix = (item: EtfPoolItem, tradeDates: string[]) => {
  const seed = hashCode(item.code);
  const momentumBase = ((seed % 11) - 5) * 0.18 + groupBias[item.group];
  const volatility = 0.9 + ((seed % 13) / 10);
  let close = 0.9 + (seed % 90) / 100;

  const dailyMatrix: Record<string, number> = {};

  tradeDates.forEach((tradeDate, index) => {
    const phase = index / 4.6;
    const wave = Math.sin(phase + seed / 19) * volatility;
    const drift = momentumBase * (index > tradeDates.length - 8 ? 1.18 : 0.82);
    const shock = Math.cos((index + 1) / 3.8 + seed / 11) * 0.9;
    const dailyReturn = round(drift + wave * 0.92 + shock * 0.56, 1);
    dailyMatrix[tradeDate] = dailyReturn;
    close *= 1 + dailyReturn / 100;
  });

  return {
    dailyMatrix,
    latestClose: round(close, 3),
  };
};

export const buildDashboardDataset = (days = 30): DashboardDataset => {
  const tradeDates = getTradingDays(days);
  const rows: DashboardRow[] = ETF_POOL.map((item) => {
    const { dailyMatrix, latestClose } = buildDailyMatrix(item, tradeDates);

    return {
      name: item.name,
      code: item.code,
      fullCode: item.fullCode,
      group: item.group,
      market: item.market,
      latestClose,
      dailyMatrix,
    };
  });

  return {
    tradeDate: tradeDates[tradeDates.length - 1],
    tradeDates,
    availableTradeDates: [...tradeDates].reverse(),
    rows,
    updatedAt: `${tradeDates[tradeDates.length - 1]} 16:18:00`,
  };
};

const compareText = (left: string, right: string, order: DashboardFilterState["sortOrder"]) =>
  order === "asc" ? left.localeCompare(right, "zh-CN") : right.localeCompare(left, "zh-CN");

const normalizeComparableNumber = (value: number | null) => (value === null ? Number.NEGATIVE_INFINITY : value);

const compareNumber = (left: number | null, right: number | null, order: DashboardFilterState["sortOrder"]) => {
  const leftValue = normalizeComparableNumber(left);
  const rightValue = normalizeComparableNumber(right);
  return order === "asc" ? leftValue - rightValue : rightValue - leftValue;
};

export const filterAndSortRows = (dataset: DashboardDataset, filter: DashboardFilterState) => {
  const latestDate = dataset.tradeDates[dataset.tradeDates.length - 1];
  const keyword = filter.keyword.trim();

  return dataset.rows
    .filter((row) => {
      const inGroup = filter.group === "全部" || row.group === filter.group;
      const inKeyword =
        keyword.length === 0 ||
        row.name.includes(keyword) ||
        row.code.includes(keyword) ||
        row.fullCode.includes(keyword);
      return inGroup && inKeyword;
    })
    .sort((left, right) => {
      if (filter.sortField === "name") return compareText(left.name, right.name, filter.sortOrder);
      if (filter.sortField === "code") return compareText(left.code, right.code, filter.sortOrder);
      return compareNumber(left.dailyMatrix[latestDate], right.dailyMatrix[latestDate], filter.sortOrder);
    });
};
