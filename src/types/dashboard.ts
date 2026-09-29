export type EtfGroup =
  | "港美海外"
  | "医药医疗"
  | "大宗商品"
  | "临时搜索"
  | "宽基指数"
  | "红利金融地产"
  | "科技通信"
  | "周期制造军工"
  | "消费与主题";

export type EtfMarket = "XSHE" | "XSHG";

export interface EtfPoolItem {
  name: string;
  code: string;
  fullCode: string;
  group: EtfGroup;
  market: EtfMarket;
}

export interface DashboardMetric {
  latestClose: number;
}

export interface DashboardRow {
  name: string;
  code: string;
  fullCode: string;
  group: EtfGroup;
  market: EtfMarket;
  latestClose: number;
  dailyMatrix: Record<string, number | null>;
  latestPriceSource?: "realtime" | "official";
  latestPriceTime?: string | null;
  dailyRank?: Record<string, number | null>;
  dailyTier?: Record<string, string | null>;
}

export interface DashboardRealtimeState {
  enabled: boolean;
  active: boolean;
  source: "tencent" | "mootdx" | "fallback";
  asOf: string | null;
  as_of?: string | null;
  stale: boolean;
  displayMode: "intraday" | "official_close";
}

export interface DashboardDataset {
  tradeDates: string[];
  availableTradeDates: string[];
  latestOfficialTradeDate?: string | null;
  showSyncTodayButton?: boolean;
  rows: DashboardRow[];
  poolSize?: number;
  updatedAt: string;
  tradeDate: string;
  selectedCode?: string | null;
  metricName?: string;
  realtime?: DashboardRealtimeState;
}

export interface DashboardFilterState {
  tradeDate: string;
  group: EtfGroup | "全部";
  keyword: string;
  sortField: "name" | "code" | "latestDay";
  sortOrder: "asc" | "desc";
}
