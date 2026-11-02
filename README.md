# 美股 / 世界经济温度计 · US & World Economy Dashboard

> **在线看板（点开即用）**：<https://wj624.github.io/us-world-economy-dashboard/>

一个覆盖**美股与世界经济**的 28 面板指标看板。**单文件、自包含、离线可看**，手机可「加到主屏幕」当 App。
每日北京时间 **06:30**（美股收盘后）自动更新。

顶部一个**综合温度计 + 超标提示条**（打开即知哪些指标越线，点标签直接跳到对应图），下面分五个方向：
**估值**（贵不贵）、**情绪/风险**（热不热、紧不紧）、**全球**（资金怎么流）、**宏观景气**（经济基本面）、**通胀/利率**（物价与政策）。
每张图带历史分位徽章、阈值参考线，以及灰色**衰退阴影带**（直接从 NBER 衰退区间画出）。

本项目**依托** [earl-etf-dashboard](https://github.com/wj624/earl-etf-dashboard) 的工程架构
（`fetch_data.py → data.json → build.py → 单文件 index.html` + AI 摘要 + GitHub Actions 每日更新），
但指标与数据源**全部换成美股/全球口径**，是独立的新仓库，不改动原仓库。

---

## 直达链接（可直接复制）

| 用途 | 地址 |
|---|---|
| **看板主页**（人看） | <https://wj624.github.io/us-world-economy-dashboard/> |
| **给 AI 的文本摘要**（推荐发这个） | <https://wj624.github.io/us-world-economy-dashboard/llms.txt> |
| 同一份摘要的 Markdown 版 | <https://wj624.github.io/us-world-economy-dashboard/snapshot.md> |
| 精简机器数据（约 4KB） | <https://wj624.github.io/us-world-economy-dashboard/latest.json> |
| 全量机器数据（全历史，约数百 KB） | <https://wj624.github.io/us-world-economy-dashboard/data.json> |
| 源码仓库 | <https://github.com/wj624/us-world-economy-dashboard> |

一次性复制全部地址：

```text
看板主页        https://wj624.github.io/us-world-economy-dashboard/
AI 文本摘要     https://wj624.github.io/us-world-economy-dashboard/llms.txt
摘要 Markdown   https://wj624.github.io/us-world-economy-dashboard/snapshot.md
精简机器数据    https://wj624.github.io/us-world-economy-dashboard/latest.json
全量机器数据    https://wj624.github.io/us-world-economy-dashboard/data.json
源码仓库        https://github.com/wj624/us-world-economy-dashboard
```

> 三个给 AI / 机器读的文件（`llms.txt` / `snapshot.md` / `latest.json`）由 `make_llm_summary.py`
> 每天从 `data.json` 自动生成。看板本体是 1MB 的单文件 HTML，数值在 JS 里、图是 canvas，
> AI 的网页抓取器读不到，所以单独产出纯文本摘要——**发给大模型就用 `llms.txt`**。

## 生成效果

- **单文件 `index.html`**：ECharts 与全部数据内联，`file://` 双击、任意静态目录、GitHub Pages 都能直接打开；离线可用。
- **表头美林时钟**：增长 7 信号 × 通胀 5 信号（加权 + 3 月平滑）定四象限，标出当前周期与占优资产。
- **顶部综合温度计**：估值/情绪/信用/通胀四个分位合成 0–100，一眼看「冷/热」；下方**超标提示条**列出所有越线指标，点标签直接跳到该图。
- **6 组 28 个面板**，自适应手机/电脑；每面板含：当前值、历史分位徽章、阈值参考线、判读一句话、数据截止日。
- **衰退阴影**：用 FRED `USREC` 的官方衰退区间，在所有时间序列图上画灰色带。
- **多序列归一化图**：全球股市地图、避险资产，各自重置为 100 便于横向比较。

## 数据源（免费、免商业授权）

| 源 | 用途 | 说明 |
|---|---|---|
| **FRED**（美联储经济数据库） | 宏观 / 估值 / 情绪主力 | 免费 API key（`api.stlouisfed.org`）。政府站点，数据权威 |
| **Yahoo Finance** | 美股/全球 ETF 与指数日线 | v8 chart API，无 key |
| **Stooq** | 价格兜底 | CSV，无 key；Yahoo 被拦时自动切换 |

> 注：席勒 CAPE 的数据源（multpl / Shiller 官方 xls / Nasdaq Data Link）均因反爬墙或云 IP 拦截，无法在 CI 稳定自动更新，故用 **FRED 巴菲特指标（M1b）** 作为估值面板。

> **重要（部署相关）**：`fredgraph.csv` 免 key 通道在 GitHub Actions 的云 IP 上可能被墙（实测超时），
> 因此**务必在仓库 Secrets 里配置 `FRED_API_KEY`**，让脚本走官方 API 域名。价格类（M7/M9/M13）走 Yahoo/Stooq，Actions 实测可通。

## 21 个面板（五大主线）

| 组 | 面板 | 数据源 | 怎么读 |
|---|---|---|---|
| **估值** | M1 美股长期估值偏离（纳指·10年·实际价格） | FRED | >+20% 长期偏贵、<-20% 低位 |
| | M2 S&P500 偏离五年均线 | FRED | >+10% 偏贵、<-20% 底部 |
| | M3 实际利率（10Y − CPI） | FRED | 转正走高=收紧，压制估值 |
| | M1b 巴菲特指标（股权市值/GDP） | FRED | >200% 偏高；当前处历史最高分位 |
| **情绪/风险** | M4 VIX 恐慌指数 | FRED | >30 恐慌、<15 自满 |
| | M5 信用利差（BAA−10Y） | FRED | 走阔=信用收缩 |
| | M6 收益率曲线倒挂（10Y−2Y） | FRED | 转负=衰退预警 |
| | M14 VIX 期限结构（VIX/VIX3M） | FRED | >1 短端恐慌、期限倒挂 |
| | M15 收益率曲线（10Y−3M） | FRED | Fed 更看重的倒挂口径，<0 预警 |
| | M13 跨资产相关性 | Yahoo/Stooq | 股债同跌=避险失效 |
| | M27 圣路易斯联储金融压力指数 | FRED | 正=压力高于均值，领先走弱 |
| **全球/世界经济** | M7 全球股市地图（归一化） | Yahoo/Stooq | 谁在上方=资金青睐；EEM 落后常伴强美元 |
| | M8 美元指数（广义加权） | FRED | 强美元压制新兴市场 |
| | M9 避险资产（金/长债/商品） | Yahoo/Stooq | 避险 vs 通胀交易 |
| **宏观景气** | M10 失业率 + Sahm | FRED | Sahm>0.5pt 触发衰退信号 |
| | M12 衰退信号汇总 | FRED | 官方+曲线+Sahm ≥2 项触发=共振 |
| | M16 初请失业金（4周均） | FRED | 周频领先；同比>+15% 警惕 |
| | M19 实际 GDP 增速 | FRED | <0 收缩、<1 乏力 |
| | M20 密歇根消费者信心 | FRED | <70 低迷 |
| **领先指标/景气** | M22 纽约联储周度经济指数（WEI） | FRED | >0 扩张、<0 收缩（周度领先） |
| | M23 芝加哥联储全国活动指数 | FRED | <-0.7 衰退阈值 |
| | M24 营建许可 | FRED | 地产周期领先 |
| | M25 制造业新订单 | FRED | 订单领先生产 |
| | M26 平均周工时（全私企） | FRED | 先于裁员下降=衰退前兆 |
| **通胀/利率** | M11 通胀（CPI 同比） | FRED | >5% 过热，对标 2% |
| | M17 核心 PCE 同比 | FRED | Fed 口径；>3% 顽固 |
| | M18 5年通胀预期（盈亏平衡） | FRED | >2.5% 预期升温 |
| | M21 联邦基金利率（有效） | FRED | >5% 紧缩 |

## 架构

```
fetch_data.py        # 三源抓取(并发/串行 + 当日TTL/增量缓存 + 重试 + 降级) + 28 面板 + 历史分位 → data.json
template.html        # 通用 ECharts 渲染器（读 window.DATA，自动画各面板，含衰退阴影）
build.py             # template.html + echarts + data.json 打包成单文件 index.html
make_llm_summary.py  # data.json → llms.txt / snapshot.md / latest.json
cache/               # 各源原始数据缓存（失败回退用）
.github/workflows/update.yml  # 每日 22:30 UTC(=北京 06:30) 自动跑
```

## 本地运行

```bash
pip install -r requirements.txt      # 仅需 numpy
export FRED_API_KEY=你的key           # 可选；不设则走 fredgraph 免 key 通道
python fetch_data.py                 # 抓数 → data.json（联网）
python build.py                      # → index.html（单文件）
python make_llm_summary.py           # → llms.txt / snapshot.md / latest.json
```

离线验证模板渲染：`python make_sample.py && python build.py`（用合成样例数据，不联网）。

## 部署（GitHub Pages）

1. 仓库 Settings → Pages → Source 选 `main` 分支 `/ (root)`。
2. Settings → Secrets and variables → Actions 加 `FRED_API_KEY`（**推荐/必要**，见数据源说明）。
3. Actions 里手动跑一次「每日自动更新看板」，即生成真实数据并部署。

## 免责声明

仅为公开市场数据的可视化复现，用于观察与学习，**不构成任何投资建议**。
分位基于有限历史样本；长历史估值用纳指代理（S&P/道指在 FRED 因授权限制仅 2016 起）。
