交流与反馈
欢迎扫码进群交流，获取最新策略动态、量化研究思路和产品更新通知。
<img width="300" height="300" alt="image" src="https://github.com/user-attachments/assets/b23b5eac-b965-4c45-8ac2-4957a9cc4dd5" />
<br>
扫码进群交流,微信号: Code_Mvp


# ETF 20 日斜率动量看板

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

把固定 ETF 池最近 **30 个交易日**的 **20 日斜率动量**渲染成横向热力矩阵——支持交易日回看、池外 ETF 临时检索、盘中实时快照与 Excel 导出。

前端 React + TypeScript + Vite + Tailwind CSS，后端 FastAPI + SQLite，数据源 Tushare Pro（盘后日线）与腾讯行情（盘中实时）。

![看板总览] 
<img width="3200" height="2000" alt="image" src="https://github.com/user-attachments/assets/b3249761-4fd5-49e7-b1a2-c44115c3814a" />


---

## 目录

- [功能](#功能)
- [界面说明](#界面说明)
- [指标口径](#指标口径)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [API](#api)
- [配置项](#配置项)
- [项目结构](#项目结构)
- [已知限制](#已知限制)
- [Roadmap](#roadmap)
- [免责声明](#免责声明)

---

## 功能

| 能力 | 说明 |
|---|---|
| 固定 ETF 池 | 50 只主流 ETF，按 8 个主题分组（港美海外 12 / 科技通信 7 / 宽基指数 7 / 大宗商品 6 / 周期制造军工 6 / 消费与主题 5 / 红利金融地产 5 / 医药医疗 2），定义见 `api/etf_pool.py` |
| 热力矩阵 | 最近 30 个交易日横向铺开，日期由近到远、从左到右排列 |
| 左侧固定列 | 名称、全池名次、代码、分组、最新价 |
| 双重视觉编码 | 20 日斜率动量连续色阶 + 横截面 P1–P10 档位分色（绿=最弱，红=最强） |
| 单元格内容 | 大字为**全池名次**，下方小字为**动量值**；悬停显示完整口径（名次/池容量/档位/四位小数动量） |
| 交易日回看 | 已落库 480 个交易日（约两年）可任选，缺失数据自动按需下载 |
| 池外检索 | 输入六位代码临时查询任意 ETF，不改变原池名次 |
| 盘中实时 | 盘中启用实时快照（300 秒窗口），收盘后自动回退正式口径 |
| Excel 导出 | 后端生成 xlsx，口径与当前看板一致 |

---

## 界面说明

### 单元格构成

矩阵每个单元格同时承载三层信息：**背景色**表示横截面档位（P1–P10），**大字**是全池名次，**下方小字**是该日动量值。

![单元格细节] <img width="1960" height="1040" alt="image" src="https://github.com/user-attachments/assets/575af8fc-a9b8-4ae4-ac47-14d2d967b349" />


> 注意：名次在**过滤之前**完成。分组筛选与关键词搜索只在展示层生效，不改变名次，因此单元格内的数字始终反映全池位置，而非当前筛选结果。

### 交易日回看

点击右上角日期按钮可展开交易日历，任选历史交易日；若该日数据尚未落库，后端会自动补拉。

![交易日回看] <img width="3200" height="2000" alt="image" src="https://github.com/user-attachments/assets/f455d4bd-0469-41ca-96bd-591cbc043cd4" />


### 池外 ETF 检索

输入六位代码即可临时并入矩阵查看，检索结果不参与原池排名（名次与档位显示为空，色阶回退为连续模式）。

![池外 ETF 检索] <img width="3200" height="2000" alt="image" src="https://github.com/user-attachments/assets/9a94e5f2-86b7-453e-8d37-e881ecb03b5b" />


---

## 指标口径

### 20 日斜率动量

对最近 **20 个交易日**的收盘价序列执行**加权最小二乘回归**：

1. 对收盘价取自然对数：`y_i = ln(close_i)`
2. 自变量 `x_i = 0, 1, ..., n-1`
3. 权重线性递增：`w_i = 1 + i / (n - 1)`，即 `n = 20` 时权重从 `1.0` 线性增至 `2.0`（近期权重更高）
4. 加权重心：`x̄ = Σw·x / Σw`，`ȳ = Σw·y / Σw`
5. 回归斜率：`slope = Σ w(x - x̄)(y - ȳ) / Σ w(x - x̄)²`
6. 加权决定系数：`R² = 1 - SS_res / SS_tot`（同为加权口径，截断至 `[0, 1]`）
7. 对数斜率**指数年化**：`slope_annual = exp(slope × 252) - 1`
8. 最终动量值：**`momentum = slope_annual × R²`**

> 年化采用指数形式 `exp(slope × 252) - 1`，不是线性乘 252；再乘以加权 R² 作为**趋势质量惩罚项**——同样斜率的走势，越贴合直线（R² 越高）动量值越高，震荡上行的会被打折。

**边界处理**（实现见 `api/metrics.py: calc_slope_momentum_from_closes()`）：

| 情形 | 返回值 |
|---|---|
| 样本数 `< 2` | `null`（前端回退为连续色阶） |
| 任一收盘价为 `null` 或 `≤ 0` | `null` |
| 加权总离差 `Σw(x - x̄)² ≤ 0` | `null` |
| 加权总平方和 `SS_tot ≤ 1e-12`（价格完全不动） | `R²` 记为 `0`，动量归零 |

### 名次与档位

- **名次 rank**：同一交易日内全池按动量值**降序**排列，`rank = 1` 为最强；动量值相同按 `fullCode` 升序打破并列。
- **档位 tier**：`rank` 在横截面内等分为 10 档，`tier = P(10 - min(9, (rank - 1) × 10 // n))`。即最强 1/10 归入 `P10`，最弱 1/10 归入 `P1`。
- **排名在过滤之前完成**，筛选与搜索不改变名次。
- 样本不足（`n < 2`）或单只 ETF 检索时，名次与档位为 `null`。

### 配色

遵循 A 股惯例 **红涨绿跌**：`P1` 深绿（最弱）→ `P10` 红（最强）。色板定义见 `src/components/tierColors.ts`。

---

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 · TypeScript 5.8 · Vite 6 · Tailwind CSS 3 · React Router 7 |
| 后端 | FastAPI · Uvicorn · Pydantic |
| 存储 | SQLite（本地单文件，首次启动自动建表） |
| 数据 | Tushare Pro（盘后日线 `fund_daily`）· 腾讯行情 / mootdx（盘中实时） |
| 导出 | XlsxWriter |
| 测试 | Vitest · Testing Library · jsdom |

---

## 快速开始

### 1. 环境要求

- Node.js ≥ 18
- Python ≥ 3.10

### 2. 安装依赖

```bash
npm install
python -m pip install -r requirements.txt
```

### 3. 配置密钥

```bash
cp .env.example .env.local
```

编辑 `.env.local`，填入 Tushare Token：

```ini
TUSHARE_TOKEN=你的_token
```

> **Tushare 权限要求**：本项目使用 `fund_daily` 接口拉取 ETF 日线，需账户具备相应积分权限。详见 [tushare.pro](https://tushare.pro/)。
> `.env.local` 已在 `.gitignore` 中，不会被提交。

### 4. 启动

```bash
# 终端 1：启动后端（默认 http://127.0.0.1:18000）
npm run dev:api

# 终端 2：启动前端开发服务器（已配置 /api 反向代理到后端）
npm run dev
```

> 后端首次启动会在生命周期钩子中**同步执行一次全量同步**，期间端口暂不响应属正常现象；数据落库后即可访问。

后端启动后会自动尝试一次同步。若首次无数据，可手动触发：

```bash
curl -X POST http://127.0.0.1:18000/api/admin/sync
```

或使用页面右上角的「同步今日数据」按钮。

### 5. 校验与构建

```bash
npm run check   # TypeScript 类型检查
npm run lint    # ESLint 静态检查
npm run test    # 单元测试
npm run build   # 生产构建，产物在 dist/
```

---

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查，返回最近一次同步任务状态与最新交易日 |
| GET | `/api/dashboard` | 看板主数据。参数：`trade_date`、`group_name`、`keyword`、`code` |
| GET | `/api/trade-date-status` | 检查指定交易日数据是否就绪 |
| GET | `/api/etf-status` | 检查指定 ETF 在指定交易日的数据是否就绪 |
| GET | `/api/export` | 导出当前看板为 xlsx，参数同 `/api/dashboard` |
| GET | `/api/jobs/latest` | 最近一次 ETL 任务日志 |
| POST | `/api/admin/sync` | 触发盘后同步 |
| POST | `/api/admin/ensure-trade-date` | 按需补齐某交易日历史数据 |
| POST | `/api/admin/ensure-etf` | 按需补齐某 ETF 历史数据 |

> 交互式文档：后端启动后访问 `http://127.0.0.1:18000/docs`。

---

## 配置项

全部通过 `.env.local` 配置，可选项见 `.env.example`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TUSHARE_TOKEN` | 空 | **必填**，Tushare Pro Token |
| `SQLITE_PATH` | `data/etf_dashboard.db` | SQLite 相对路径 |
| `REALTIME_ENABLED` | `false` | 是否启用盘中实时快照 |
| `REALTIME_SOURCE` | `tencent` | 实时数据源：`tencent` / `mootdx` |
| `REALTIME_REFRESH_WINDOW_SECONDS` | `300` | 实时快照有效窗口（秒） |
| `REALTIME_STALE_THRESHOLD_SECONDS` | `300` | 快照过期阈值（秒），超时回退正式口径 |

---

## 项目结构

```text
├── api/                              # FastAPI 后端
│   ├── main.py                       # 路由入口
│   ├── config.py                     # 环境变量与配置
│   ├── db.py                         # SQLite 建表、迁移与连接
│   ├── etf_pool.py                   # 固定 ETF 池定义（50 只 / 8 分组）
│   ├── metrics.py                    # 20 日斜率动量计算
│   ├── service.py                    # 同步、查询、名次档位与导出
│   ├── realtime_service.py           # 盘中实时快照调度
│   ├── realtime_types.py             # 实时数据结构定义
│   ├── realtime_source_tencent.py    # 腾讯行情实时源
│   └── realtime_source_mootdx.py     # mootdx 实时源
├── src/                              # React 前端
│   ├── pages/Home.tsx                # 看板主页面
│   ├── components/
│   │   ├── DashboardTable.tsx        # 热力矩阵表格
│   │   ├── HeatCell.tsx              # 单元格（档位分色 / 连续色阶回退）
│   │   ├── TradeDateCalendar.tsx     # 交易日选择器
│   │   └── tierColors.ts             # P1–P10 档位色板
│   ├── lib/http.ts                   # API 请求封装
│   ├── types/dashboard.ts            # 接口类型定义
│   └── utils/                        # 交易日工具与本地模拟数据集
├── docs/screenshots/                 # README 配图
├── public/                           # 静态资源
├── data/                             # SQLite 落库目录（不入版本库，自动创建）
└── exports/                          # 导出产物目录（不入版本库）
```

---

## 已知限制

- 数据依赖 Tushare Pro，接口权限与频率受账户积分限制。
- SQLite 单文件存储，适合单机自用；多实例部署需自行升级到 PostgreSQL 等。
- 管理类接口（`/api/admin/*`）目前**无鉴权**，仅适用于本机或受信内网部署，请勿直接暴露公网。
- 交易日历依赖 `trade_calendar` 表，首次同步前无法生成看板。
- 界面中的相关导航与交流入口指向作者自有的其他看板站点与社群，与本项目功能无关。

## Roadmap

- [ ] 盘后定时跑批（APScheduler）
- [ ] `/api/admin/*` 增加鉴权
- [ ] 将 `src/utils/mockDashboard.ts` 接入路由，提供免 Token 的演示模式
- [ ] 日线数据存储升级为可插拔后端

---

## 免责声明

本项目为量化数据可视化工具，所有指标均由公开行情数据计算得出，**不构成任何投资建议**。使用者需自行承担依据本项目输出所做决策的全部风险。作者不对数据的准确性、完整性或及时性作任何保证。

---

## License

[MIT](LICENSE)
