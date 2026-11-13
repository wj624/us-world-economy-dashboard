# 美股 / 世界经济温度计 · US & World Economy Dashboard

> **在线看板（点开即用）**：<https://wj624.github.io/us-world-economy-dashboard/>

一个覆盖**美股与世界经济**的 28 面板指标看板。**单文件、自包含、离线可看**，手机可「加到主屏幕」当 App。
每日北京时间 **06:30**（美股收盘后）自动更新。

顶部一个**综合温度计 + 超标提示条**（打开即知哪些指标越线，点标签直接跳到对应图），下面分六个板块：
**估值**（贵不贵）、**情绪/风险**（热不热、紧不紧）、**全球**（资金怎么流）、**宏观景气**（经济基本面）、
**领先指标**（未来 1–2 个季度往哪走）、**通胀/利率**（物价与政策）。
每张图带历史分位徽章、阈值参考线，以及灰色**衰退阴影带**（直接从 NBER 衰退区间画出）。

本项目**依托** [earl-etf-dashboard](https://github.com/wj624/earl-etf-dashboard) 的工程架构
（`fetch_data.py → data.json → build.py → 单文件 index.html` + AI 摘要 + GitHub Actions 每日更新），
但指标与数据源**全部换成美股/全球口径**，是独立的新仓库，不改动原仓库。

---

## 直达链接（可直接复制）

| 用途 | 地址 |
|---|---|
| **看板主页**（人看） | <https://wj624.github.io/us-world-economy-dashboard/> |
| **看板中心（聚合入口）** | <https://wj-dashboards.pages.dev/> |
| **给 AI 的文本摘要**（推荐发这个） | <https://wj624.github.io/us-world-economy-dashboard/llms.txt> |
| 同一份内容的另一文件名（`llms.txt` 与 `snapshot.md` 内容完全相同，供不同下游使用） | <https://wj624.github.io/us-world-economy-dashboard/snapshot.md> |
| 精简机器数据 | <https://wj624.github.io/us-world-economy-dashboard/latest.json> |
| 全量机器数据（全历史） | <https://wj624.github.io/us-world-economy-dashboard/data.json> |
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
> 每天从 `data.json` 自动生成。看板本体是 MB 级的自包含单文件 HTML（体积以仓库实际文件为准），数值在 JS 里、图是 canvas，
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

> **重要（部署相关）**：FRED 有两条通道——官方 API（配 `FRED_API_KEY` 时走）与 `fredgraph.csv` 免 key 通道（不配 key 时的默认）；
> 后者在 GitHub Actions 的云 IP 上实测常被墙/超时，因此**强烈建议在仓库 Secrets 里配置 `FRED_API_KEY`**。价格类（M7/M9/M13）走 Yahoo/Stooq，Actions 实测可通。

## 28 个面板（六大板块）

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
build.py             # template.html + echarts + 运行时生成的 data.js 打包成单文件 index.html
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

离线验证模板渲染：`python make_sample.py && python build.py`（用合成样例数据，不联网）。样例输出到 `sample_data.json`，不会覆盖生产 `data.json`。

## 部署（GitHub Pages）

1. 仓库 Settings → Pages → Source 选 `main` 分支 `/ (root)`。
2. Settings → Secrets and variables → Actions 加 `FRED_API_KEY`（**强烈建议**：两条通道都在，不配则走 `fredgraph.csv` 免 key 通道，但该通道在 Actions 云 IP 上常被墙/超时，见数据源说明）。
3. Actions 里手动跑一次「每日自动更新看板」，即生成真实数据并部署。

## 给 AI 的维护提示词

> 把下面「提示词」整段复制给 AI 即可接手维护；前面两节是「哪里容易改漏」，人也可以先看。

### 仓库速览

| 项 | 内容 |
| --- | --- |
| 用途 | 美股 / 世界经济 **28 面板**温度计，产出单文件自包含 HTML 看板 |
| 抓数 + 指标计算 | `fetch_data.py`（单文件承担全部三源抓取与全部面板指标） |
| 渲染 | `template.html`（**通用** ECharts 渲染器，读 `window.DATA` 自动画图）+ `build.py` → `index.html` |
| AI 摘要 | `make_llm_summary.py` → `llms.txt` / `snapshot.md` / `latest.json` |
| 调度 | `.github/workflows/update.yml`，`cron: '30 22 * * *'`（UTC）= 北京 06:30 |
| 依赖 | `numpy`（其余全用标准库） |
| 密钥 | `FRED_API_KEY`（**强烈建议配置**：两条通道都在，不配则走 `fredgraph.csv` 免 key 通道，但该通道在 Actions 云 IP 上常被墙/超时） |
| 产物（勿手改） | `index.html` / `llms.txt` / `snapshot.md` / `latest.json` / `version.txt` |

### 改代码前必须知道的三个坑

1. **免 key 且已有缓存时，脚本以「有缓存」短路、永不联网，数据静默冻结。** 不配 key 时走免 key 的
   `fredgraph.csv` 通道，该通道在 GitHub Actions 云 IP 上实测**会被墙/超时**；旧逻辑拿到缓存就跳过联网，
   数值看着正常却再不更新。现已修成「按当日 TTL 判断是否需要联网、缓存只作兜底」（依据：`fetch_data.py`
   `fetch_fred()` 的 `_ttl_hit()` 当日 TTL 判定），仍**强烈建议配置 `FRED_API_KEY`**；**不要删 `cache/`**（见坑 2）。
2. **`cache/` 目录别删。** 里面是每条序列的 CSV 快照（`fred_*.csv` / `yahoo_*.csv`），
   抓取失败时脚本回退读它 —— 这是本项目唯一的降级手段。删掉就只剩「抓不到就空着」。
3. **新增 / 改名面板要动两处。** 面板本体在 `fetch_data.py`（`panel_line(...)` 系列 + 底部
   综合温度计的 `add("估值", [...], 0.35)` 权重）；而 `make_llm_summary.py` 的 `reading(p)`
   决定该面板在 `llms.txt` / 邮件摘要里怎么用一句话判读。**只改前者不会报错**，但 AI 摘要里那一项会缺失或说不清。

### 提示词（复制这段给 AI）

```text
你在维护 GitHub 仓库 wj624/us-world-economy-dashboard —— 一个美股/世界经济 28 面板指标看板。
先读 README.md（「数据源」与「给 AI 的维护提示词」两节）。

【流水线】fetch_data.py → data.json → build.py → 单文件 index.html；
make_llm_summary.py → llms.txt / snapshot.md / latest.json；GitHub Actions 每天 UTC 22:30 自动跑。

【数据源与降级顺序】
- FRED（api.stlouisfed.org，需 FRED_API_KEY）：宏观/估值/情绪主力。
  无 key 时会退回 fredgraph.csv 免 key 通道，但该通道在 Actions 云 IP 上会被墙 —— 所以务必保留 key 逻辑。
- Yahoo Finance v8 chart API（无 key）：美股/全球 ETF 与指数日线。多个 host 轮换，tries=1、timeout=8。
- Stooq（无 key，CSV）：Yahoo 被拦时的价格兜底。
- 三源之外的第四层是读 cache/ 下的 CSV 快照。改抓取逻辑时不要破坏这条回退链。

【铁律】
1. 不要删 cache/ 目录，也不要让抓取失败变成「写空值」——失败应当回退到 cache，而不是覆盖成 null。
2. index.html / llms.txt / snapshot.md / latest.json / version.txt 都是构建产物，不要手改。
3. 新增或改名面板时：fetch_data.py 加面板 + 检查底部综合温度计的权重 add(...) +
   同步 make_llm_summary.py 的 reading()（决定 AI 摘要里的判读句）。漏了不报错，但摘要会缺项。
4. 分位（percentile）是本看板的核心读数，改指标口径会整体挪动分位；
   若换了数据源导致水平值变化，阈值与判读文字必须重新设定（否则「高位/低位」的灯会一直错着亮）。
5. 衰退阴影来自 FRED USREC 官方区间，不要用估算替代。

【验证】
- 本地：pip install -r requirements.txt && export FRED_API_KEY=xxx && python fetch_data.py
  → python build.py → python make_llm_summary.py
  检查 data.json 里每条序列的最新日期是否推进、有没有整条为空的序列。
- 离线验证模板渲染（不联网）：python make_sample.py && python build.py
- 云端：Actions 手动跑「每日自动更新看板」，确认抓数步骤无 timeout、提交里有 index.html 与 llms.txt。

【收尾】改了数据源/面板数量/调度，同步更新 README 的「数据源」「28 个面板」「架构」三节。
```

## 免责声明

仅为公开市场数据的可视化复现，用于观察与学习，**不构成任何投资建议**。
分位基于有限历史样本；长历史估值用纳指代理（S&P/道指在 FRED 因授权限制仅 2016 起）。

---

## 附录 · 2026-11-05 全量整改记录（给维护者 / 给 AI 读）

> **这一节是什么**：AI 维护助手在 2026-11-05 对账号下 6 个仓库做完一次「大范围彻底修复」后追加的说明。目的只有一个——**让下一次维护（不管人或 AI）能看懂每个改动为什么做、哪些绝对不能回退**。
>
> **怎么读**：改任何代码之前，先读本 README 前文的「维护须知 / 铁律 / 给 AI 的维护提示词」，再读本附录。**两者冲突时以前文铁律为准**；本附录只解释本次改动，不新增、不覆盖任何设计口径。
>
> **本次原则**：用户要求「稳定、基本无维护、占用空间少、不自动生成垃圾」，并明确「修改前先看 README 的设计思路与维护须知」。因此本次只修**确定性 bug、静默失败、危险工作流行为、文档与代码不一致、依赖版本失控、运行时垃圾文件**；**没有做架构改造，没有删任何数据资产，没有改任何口径/阈值/单位/cron/构建顺序**。
>
> **本次改动范围**：6 仓共 40 个文件、0 删除；逐仓白名单精确提交，全程无 `--force`、无 rebase 冲突。**上线后的串行补测又追加了一次 pandas 3.x 兼容性修复（3 仓 6 文件，见 F 节），所以最终线上状态以 F 节为准，A 表里凡是写 `pandas<4` 的地方都已收紧为 `pandas<3`**。

### A. 本次改了什么（逐文件）

| 文件 | 原始缺陷（为什么必须改） | 本次修法 | 依据 / 约束 |
|---|---|---|---|
| `fetch_data.py`（3 处） | `CTX` 关闭了 TLS 证书校验（`CERT_NONE` / `check_hostname=False`），存在中间人风险；缓存读/写失败 `except: pass` 完全静默；**免 key FRED 通道「已有缓存就短路」，导致数据永久静默冻结**（README「坑 1」原来说反了方向） | 恢复 `ssl.create_default_context()` 默认校验；缓存读写失败打 `[WARN]` 并返回布尔；免 key 通道改按 `_ttl_hit(ttl_key)` 判断是否联网——有缓存也要按当日 TTL 决定是否刷新，增量只取末日期前 10 天，失败**回退缓存、绝不写空值** | 「不要删 cache/，也不要让抓取失败变成写空值——失败应当回退到 cache」；「给 AI 的维护提示词」坑 1 |
| `make_sample.py`（2 处） | 离线样例会**覆盖生产 `data.json`**，而 README 还把它当验证命令推荐，一跑就毁生产数据 | 输出改 `sample_data.json`；副标题动态计算面板数 | 「产物不要手改」 |
| `build.py`（2 处） | ECharts 注释写 5.5.1 但实际 5.6.0；`version.txt` 写入失败被吞异常，前端版本探针会静默失效 | 注释订正；写入失败抛 `RuntimeError` 终止构建 | 前端版本探针依赖 `version.txt` |
| `template.html` | 数据源说明缺 Stooq / 本地缓存通道 | 补齐 | 「数据源」节 |
| `requirements.txt` | 依赖无主版本上界，未来主版本可能不兼容 | 加 `numpy<3` 等上界（**不上钉具体小版本**，避免 Python 未来版本装不上） | 「稳定、基本无维护」 |
| `.github/workflows/update.yml` | 无数据有效性守卫，产物为空/坏 JSON 也会照常提交 | 插入守卫：只验关键产物**存在 / 非空 / JSON 合法**；**不做「必须是今天」判定**——节假日与披露滞后属正常，严格日期会误杀 | 维护须知；28 面板口径 |
| `.github/workflows/monthly-snapshot.yml` | 每月 1 号自动用 Git Data API 造 `parents: []` root commit 并 `force=true` 强推 `main`，会抹掉 `cache/` 等数据资产历史、破坏外部克隆/fork，回滚 SHA 90 天过期即不可恢复 | **停用 `schedule`**，保留 `workflow_dispatch` 手动入口（不删文件、不改主体）；guard 增加 `*.json` 合法性校验；回滚 SHA artifact `retention-days` 90 → 365 | 保留手动能力，仅去掉「自动且不可回滚」的部分 |
| `.gitignore` | 新增的 `sample_data.json` 会被 git 跟踪 | 追加 `sample_data.json` | 「不自动生成垃圾」 |
| `README.md` | FRED key 描述前后矛盾；「坑 1」方向说反；`llms.txt` / `snapshot.md` 说明含糊；体积/行数过时；架构里 `build.py` 读取的文件写错 | 统一为「两通道并存；不配 key 走 fredgraph，但云 IP 常被墙/超时，强烈建议配 key」；坑 1 改成真实风险「有缓存短路 → 数据静默冻结」并注明已按当日 TTL 修复；说明两份摘要是同源内容的两份文件名；架构改为 `build.py` 读运行时生成的 `data.js`；`make_sample.py` 补输出说明；过时数字改定性 | 28 面板、分位口径、USREC 衰退阴影等维护须知**全部保留** |

### B. 本次坚决没改（硬约束，改了就是破坏设计）

- **`cache/` 未删、未忽略、未改回 `actions/cache`**：它是唯一降级手段。
- **`llms.txt` / `snapshot.md` / `version.txt` 仍随提交**（不同下游各自读）。
- 28 个面板、分位算法、USREC 衰退阴影、产物入库设计、cron、`make_llm_summary.py` 链路均未改。
- 局部 `except: pass`（TTL 状态、日志编码、临时文件清理）按回退链设计**保留**，只把主流程的静默失败显式化。

### C. 明令作废的旧建议（别再走回头路）

第一轮「只读体检报告」里提出过若干架构建议，**读完各仓 README 的维护须知后已全部作废**，本次一个都没采纳：

- ❌ **「产物不入库 / 数据与页面不进 git」**：本仓产物是 Pages / EdgeOne Pages / GAS 的**数据源本身**，从仓库检出，必须入库。
- ❌ **「删 `cache/` / 改回 `actions/cache`」**：`cache/` 是断网降级与历史累积的命根子。
- ❌ **「删数据资产 / 删摘要文件 / 清理 `echarts.min.js` / 删 `akshare` / 删 `westock-data`」**：均被 README 明确点名保护。
- ❌ **「把 `except: pass` 全改抛错」**：局部容错（TTL 状态、日志编码、临时文件清理、上游回退链）是设计，不是缺陷；本次只把**主流程**的静默失败改成显式失败。
- ❌ 早期报告曾把 GAS 脚本里的 `RECEIVER_EMAIL` 硬编码列为 bug —— **不是 bug**，它是 `CONFIG` 里明确列出的默认配置项，本次未改。

> 若下次 AI 读到 `wj624-仓库体检与整改思路.md` 或 `wj624-整改落地手册.md` 里的 P1/P2 建议，请以本附录为准：**那两份是整改前的中间产物，已作废**。


### D. 给 AI 的维护边界（可复制这段）

```
你在维护 wj624/us-world-economy-dashboard（每日自动出 28 面板看板）。动手前：
1. 先读 README「给 AI 的维护提示词」三个坑，再读本附录；尤其坑 1 现在是「有缓存短路会静默冻结」。
2. 绝对不要：删 cache/；让抓取失败写空值或覆盖 null；手改产物；把 make_sample.py 改回写 data.json；
   恢复 monthly-snapshot.yml 的自动 schedule。
3. 免 key 通道必须按 _ttl_hit(ttl_key) 判断联网，不能「有缓存就 return」。
4. 改了数据源/面板数/调度，同步更新 README 的「数据源」「28 个面板」「架构」三节 + build.py 注释。
5. 改完必须：python fetch_data.py && python build.py && python make_llm_summary.py，
   检查每条序列最新日期是否推进、有没有整条为空；离线模板渲染用 make_sample.py（输出 sample_data.json，不碰生产）。
6. 线上写操作：精确 git add、中文 commit、git pull --rebase、绝不 force。
```
### E. 验证与回滚

| 项目 | 说明 |
|---|---|
| 本地验证 | 补丁脚本在从原仓库 `git archive HEAD` 导出的**干净副本**上端到端重跑：59/59 替换、2 处追加、2 个新建 `.gitignore`、5 个 `monthly-snapshot.yml` 降级；`.py` 用 `ast.parse`、`worker.js` 用 `node --check`、`.yml` 用 `yaml.safe_load`，语法自检 26 项全 PASS |
| README 硬约束复核 | 61 项，实际 61/61 通过（初检 5 项 FAIL 均为检查规则误报） |
| 线上内容核验 | GitHub API 独立核验：commit 主题、变更文件集合与白名单逐仓一致、**0 删除**、关键修复内容、数据资产 12/12 在线 |
| 线上实测 | 2026-11-05 串行手动触发 4 个核心 workflow 并逐个核验：4/4 全部 success、每仓产物 commit 均 removed=0、关键数据资产完好。第一次补测在 rotation-monitor 暴露 pandas 3.x 移除 resample('M') 的问题，双保险修复后重跑通过。明细与最终线上 HEAD 见下方「F. 补测实测记录」 |
| 令牌 / 垃圾 | 交付文件 `ghp_` / `github_pat_` 0 命中；仓库内不生成 `__pycache__` |

**回滚**：优先 `git revert <整改 commit>` 生成反向 commit 再 push（保留历史、无需 force）。整改前基线 `e80f8788`，整改 commit `e9ee6da9`（`git revert e9ee6da9`）。本次 commit 触发的是 `pages build and deployment`（**仅 Pages 部署 success**）；抓数流水线 `update.yml` 是 `schedule + workflow_dispatch`，push 不会实测它。**已于 2026-11-05 串行补测手动 dispatch 实测通过**（run 41990418511，产物 commit `0b18f069`，0 删除、5 项资产完好），见 F 节。

**下次改代码前的三行自检**（沿用前文铁律）：
1. 这个文件是源码还是产物？产物只能靠重跑生成，不能手改。
2. 改动会不会破坏「数据资产 / 口径 / 阈值 / 单位 / cron / 构建顺序」？会就停手。
3. 改完要跑什么验证、要同步 README 哪几节？写进 commit body。

### F. 补测实测记录（2026-11-05，含 pandas 3.x 兼容性二次修复）

整改 commit 上线后，用户要求对 4 个「`push` 不触发、只在 `schedule` / `workflow_dispatch` 跑」的核心抓数流水线做**串行手动触发补测**：一个跑完、核验通过，再触发下一个，避免并发写 `main` 冲突。

**第一次补测在 `rotation-monitor` 失败**，日志关键行：

```
ValueError: 'M' is no longer supported for offsets. Please use 'ME' instead.
  File ".github/workflows/generate_page.py", line 130, in ...
    monthly = bd.set_index('date')['close_cyb'].resample('M').last()
```

根因：pandas 3.1.1 于 2026-11-04 发布，移除了 `resample('M')` 别名，并默认开启 Copy-on-Write、改变字符串 dtype。**整改前依赖本无上界**；本轮整改把上界写成 `<4` 过宽，且 `daily_update.yml` 的 `pip install` 行仍是完全无上界 —— 这是策略失误，已按下面「双保险」纠正。

**双保险修复（3 仓 6 文件）**：

1. **代码**：`rotation-monitor/.github/workflows/generate_page.py` 的 `resample('M')` → `resample('ME')`（pandas 2.3.3 与 3.0.0 下语义一致，均为月末重采样，本地实测两种版本输出一致）。
2. **依赖**：所有 pandas 约束收紧为 `<3`，且 **`requirements.txt` 与 workflow 的 `pip install` 行两处同步** —— 线上实际执行的是 workflow 里的 pip install，不是 requirements.txt，只改一处等于没改。
3. **二次 commit**：`rotation-monitor` `ee80a439`、`earl-etf-dashboard` `af8b5237`、`national-team-etf-flow` `b0ef1c6c`。

**修复后重跑，4/4 全部通过**：

| 仓库 / workflow | run id | 结论 | 产物 commit（前 → 后） | 删除 | 关键资产 |
|---|---|---|---|---|---|
| `rotation-monitor` / `daily_update.yml` | 41990306988 | success | `ee80a439` → `1c6dd808` | 0 | `public/index.html` 完好 |
| `us-world-economy-dashboard` / `update.yml` | 41990418511 | success | `e9ee6da9` → `0b18f069` | 0 | `cache/` · `index.html` · `llms.txt` · `snapshot.md` · `version.txt` 完好 |
| `earl-etf-dashboard` / `update.yml` | 41990472730 | success | `af8b5237` → `abdee20d` | 0 | `cache/` · `version.txt` · `llms.txt` · `latest.json` · `index.html` 完好 |
| `national-team-etf-flow` / `daily-refresh.yml` | 41990810766 | success | `b0ef1c6c` → `5110f0f1` | 0 | `_etf_shares_cache.json` · `echarts.min.js` · `index.html` 完好 |

> `a-stock-api`（Worker 部署 + 13 个冒烟端点）与 `etf-lsi`（daily report）由 `push` 触发，整改当时即 `success`，不在上表。

**写本附录时各仓 `main` 的线上实况**（均为短 SHA，位数不影响定位）：

| 仓库 | 整改 commit | pandas 二次修复 | 补测产物 / 当前 HEAD |
|---|---|---|---|
| `a-stock-api` | `daea02a` | — | `daea02a` |
| `us-world-economy-dashboard` | `e9ee6da` | — | `0b18f06` |
| `earl-etf-dashboard` | `75255bd` | `af8b523` | `abdee20` |
| `national-team-etf-flow` | `016a401` | `b0ef1c6` | `5110f0f` |
| `rotation-monitor` | `b5f01af` | `ee80a43` | `1c6dd80` |
| `etf-lsi` | `606958f` | — | `8e8f74f`（自动产物 commit 会继续前移，属正常） |

> **给 AI 的硬约束**：这 3 个仓的 pandas **必须锁 `<3`**，不要「简化」成 `<4` 或去掉上界；`resample('ME')` 不要改回 `'M'`。改依赖时**必须同时改 `requirements.txt` 和 workflow 的 `pip install` 行** —— 第一次补测就是这样崩的。另外这 6 仓**没有单元测试套件**，上述「实测」指真实 workflow 执行 + 产物核验，改完代码仍应手动 dispatch 一次确认。

### G. 后续策略调整 · 按体积自动清理（2026-11-05 同日）

> **本仓情况**：本仓有 `monthly-snapshot.yml`，已按本节改制；`KEY_FILE` 为 `fetch_data.py`，不要改错。
>
> **优先级说明**：A / B / D 节记录的是当天**第一版**整改状态，原文保留不改以便追溯决策过程；关于「每月清理」的部分自本节起**以本节为准**：
> - A 表里的「停用 `schedule`」= 停用**旧版「每月 1 号无条件 force 重写 main」**的 schedule；
> - D 节「绝对不要恢复 monthly-snapshot 自动 schedule」= 不要恢复**上面那个旧版**；
> - 本节新增的「按体积体检 schedule」是**有意保留的新机制，不要删、不要改回每月无条件执行**。

#### 为什么要调整

用户指出：当初设计每月清理，是为了防止「每日产物入库」让仓库长期运行后体积膨胀。第一版整改只从「安全 / 可回滚」角度停用了 schedule，**没有回应「空间封顶」这个原始诉求**，等于把自动能力关掉了。实测后确认这个担心成立：

| 实测项 | 数值 |
|---|---|
| 6 仓当时合计体积 | 约 67 MB |
| 最大单个文件 | 4.4 MB（GitHub 单文件硬限 100 MB） |
| 仓库年龄 | 2~6 天（全部建于 2026-10-31 ~ 11-04） |
| 稳定后估算增长 | 约 1~2 MB/天（前几天叠加了整改提交，偏高） |
| 放着不管碰线时间 | 大半年 ~ 2 年到 1 GB 建议线 |
| GitHub 官方口径 | 理想 < 1 GB、强烈建议 < 5 GB，**不是免费版封顶** |
| 6 仓可见性 | 全部 **public**，Actions 分钟数免费不限量 |

结论：不会立刻被封，但会变慢、可能收到 GitHub 提醒邮件，所以「自动封顶」确实需要保留——只是不能再用「每月无条件强推」这种不可回滚的方式。

#### 改成什么

`.github/workflows/monthly-snapshot.yml`：

- `on.schedule` 改为**每周一 UTC 03:00（北京 11:00）只做一次「体积体检」**：读一次仓库 `size`，**低于 500 MB 就直接结束，一个字节都不改、绝不碰 `main` 历史**。
- 仅当 `size >= 500 MB（512000 KB）` 时才执行剪断。按 67 MB 起步、1~2 MB/天估算，约 8 个月~1 年才第一次真正动刀；清完回到约 10 MB 再重新累积，永远远低于 1 GB。
- `workflow_dispatch` 保留，新增 `force` 布尔输入（**默认 false**）：手动触发默认「只体检、不改动」，勾选 `force` 才忽略阈值立即清理。
- 原有护栏**全部保留**：`README.md` / `KEY_FILE` 存在、`git ls-files >= 8`、JSON 合法性校验、root commit 用 Git Data API（`parents: []`）、不走 `git push --force`、不触发 push 工作流、旧 HEAD 记入 artifact `retention-days: 365`、回滚命令写进日志、`concurrency` 互斥。
- **针对「按体积触发」新增一道护栏**：所有被跟踪文件必须 < 50 MB。体积突然暴涨通常是误提交大文件，绝不能把这种异常树固化成「唯一的 root commit」。
- guard 的 JSON 校验从「只查根目录 `*.json`」扩展到「`git ls-files -z '*.json'` 的全部被跟踪 JSON」。
- 体积读取优先 `gh api repos/... --jq .size`，失败回落 `github.event.repository.size`；两者都取不到时**安全跳过、不清理**。

#### 给 AI 的维护边界（追加，不替代 D 节）

1. **不要**把 `on.schedule` 改回「每月 1 号无条件执行」，不要删掉体积判断或改掉 `THRESHOLD_KB`。
2. **不要**把 `force` 默认值改成 `true`，不要去掉手动入口「默认只体检」的语义。
3. **不要**删掉 50 MB 单文件护栏或全量 JSON 校验；它们是「按体积自动」特有的防误固化措施。
4. 想立刻清理：Actions 页手动 dispatch 并**勾选 force**；只想体检：直接 dispatch 不勾选。
5. 清理后 `main` 变成 root commit，**外部克隆 / fork 需要重新 clone**；回滚命令在 run 日志与 artifact 里，保留 365 天。
6. 阈值 500 MB 可调，但**不要调到 1 GB 以上**（失去提前封顶意义），也**不要调到 100 MB 以下**（频繁剪历史）。
7. 判断是否需要清理看的是仓库 `size`（`gh api repos/<owner>/<repo> --jq .size`，单位 KB），不是文件个数或提交数。
8. 线上写操作照旧：精确 `git add`、中文 commit、`git pull --rebase`、**绝不 force**。

#### 验证与回滚

- 验证：改完用 `yaml.safe_load` 校验；在 Actions 手动 dispatch（**不勾选 force**）应看到 `below threshold: nothing to do, main history untouched`，且 `main` HEAD 不变、工作区无改动。
- 回滚本策略：`git revert <本策略 commit>` 即可回到「仅手动入口」的第一版状态；数据资产与其它 workflow 均不受影响。

---

## ☕ 支持一下（打赏）

先说声谢谢。感谢你点进这个仓库、读到这里，也感谢每一位把看板放进收藏夹、每天顺手看一眼的朋友。

这几个仓库都是我个人利用业余时间一点点搭起来的：数据源对接、口径逐项核对、每天自动更新、出问题时连夜排查，再把踩过的坑一条条写回 README，只为了让它们**稳定、干净、少维护**地长期跑下去。所有内容**完全免费、无需注册、不设门槛**，打赏与否不会影响任何功能，也不会改变我维护它们的方式。

如果这些看板、接口或文档，曾帮你少翻几份报表、少绕一次弯路，或在某个盘前更快看清了状况 —— 那已经是我做这件事最想得到的回报了。

**如果它确实帮到了你，欢迎随手打赏一点，就当请我喝杯咖啡 ☕** —— 金额随意，多少都是心意；微信扫下面这张收款码就行：

<p align="center">
  <img src="assets/sponsor-wechat.png" alt="微信支付 · 收款码" width="260" />
</p>

不方便或不想打赏也**完全没关系**：点个 ⭐ Star、提个 issue、把链接转给可能用得上的人，都是很实在的支持。发现数据或文案有问题也欢迎直接指出，我会按 README 里的维护纪律逐条核对。

谢谢你的时间。愿数据常新，愿你我都不被行情牵着走。🙏
