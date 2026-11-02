# 美股 / 世界经济温度计 · US & World Economy Dashboard

> **在线看板（部署后）**：`https://wj624.github.io/us-world-economy-dashboard/`
> **给 AI 的文本摘要**：`.../llms.txt`　·　**精简机读**：`.../latest.json`

一个覆盖**美股与世界经济**的 13 面板指标看板。单文件、自包含、离线可看，手机可「加到主屏幕」当 App。
每日北京时间 **06:30**（美股收盘后）自动更新。

本项目**依托** [earl-etf-dashboard](https://github.com/wj624/earl-etf-dashboard) 的工程架构
（`fetch_data.py → data.json → build.py → 单文件 index.html` + AI 摘要 + GitHub Actions 每日更新），
但指标与数据源**全部换成美股/全球口径**，是独立的新仓库，不改动原仓库。

---

## 数据源（全部免费、免 key、免商业授权）

| 源 | 用途 | 说明 |
|---|---|---|
| **FRED**（美联储经济数据库） | 宏观 / 估值 / 情绪主力 | `fredgraph.csv` 免 key 通道；若设 `FRED_API_KEY` 则走官方 API（更快、限流更宽）。政府站点，服务器端最稳 |
| **Yahoo Finance** | 美股/全球 ETF 与指数日线 | v8 chart API，无 key |
| **Stooq** | 价格兜底 | CSV，无 key；Yahoo 被拦时使用 |
| **multpl.com** | 席勒 CAPE（可选增强） | 拿不到就自动跳过，不影响其它面板 |

> 价格类（M7/M9/M13）若 Yahoo+Stooq 都被拦，会**优雅降级**：这几个面板缺席，但宏观面板（FRED）照常产出，看板整体不崩。

## 13 个面板（四大主线）

| 组 | 面板 | 数据源 | 怎么读 |
|---|---|---|---|
| **估值** | M1 巴菲特指标（市值/GDP） | FRED | >100% 偏贵、>130% 危险 |
| | M2 S&P500 偏离五年均线 | FRED | >+10% 偏贵、<-20% 底部 |
| | M3 实际利率（10Y − CPI） | FRED | 转正走高=收紧，压制估值 |
| | M1b 席勒 CAPE（可选） | multpl | >30 高估、<15 偏低 |
| **情绪/风险** | M4 VIX 恐慌指数 | FRED | >30 恐慌、<15 自满 |
| | M5 信用利差（BAA−10Y） | FRED | 走阔=信用收缩 |
| | M6 收益率曲线倒挂（10Y−2Y） | FRED | 转负=衰退预警 |
| **全球/世界经济** | M7 全球股市地图（归一化） | Yahoo/Stooq | 谁在上方=资金青睐 |
| | M8 美元指数（广义加权） | FRED | 强美元压制新兴市场 |
| | M9 避险资产（金/长债/商品） | Yahoo/Stooq | 避险 vs 通胀交易 |
| **宏观景气** | M10 失业率 + Sahm | FRED | Sahm>0.5pt 触发 |
| | M11 通胀（CPI 同比） | FRED | 对标 2% 目标 |
| | M12 衰退信号汇总 | FRED | ≥2 项触发=共振 |
| | M13 跨资产相关性 | Yahoo/Stooq | 股债同跌=避险失效 |

## 架构

```
fetch_data.py        # 三源抓取(缓存/重试/降级) + 13 面板计算 + 历史分位 → data.json
template.html        # 通用 ECharts 渲染器（读 window.DATA，自动画各面板）
build.py             # template.html + echarts + data.json 打包成单文件 index.html
make_llm_summary.py  # data.json → llms.txt / snapshot.md / latest.json
cache/               # 各源原始数据缓存（失败回退用）
.github/workflows/update.yml  # 每日 22:30 UTC(=北京 06:30) 自动跑
```

## 本地运行

```bash
pip install -r requirements.txt      # 仅需 numpy
python fetch_data.py                 # 抓数 → data.json（联网）
python build.py                      # → index.html（单文件）
python make_llm_summary.py           # → llms.txt / latest.json
```

离线验证模板渲染：`python make_sample.py && python build.py`（用合成样例数据，不联网）。

## 部署（GitHub Pages）

1. 仓库 Settings → Pages → Source 选 `main` 分支 `/ (root)`。
2. 在 Settings → Secrets and variables → Actions 里可加 `FRED_API_KEY`（可选，不加也能跑）。
3. Actions 里手动跑一次「每日自动更新看板」，即生成真实数据并部署。

## 免责声明

仅为公开市场数据的可视化复现，用于观察与学习，**不构成任何投资建议**。
分位基于有限历史样本；巴菲特指标用 `Wilshire5000/GDP` 近似，绝对值略高于市值口径。
