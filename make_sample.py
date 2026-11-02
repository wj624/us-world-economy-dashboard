# -*- coding: utf-8 -*-
"""生成一份合成的样例 data.json（不联网），用于验证模板渲染链路。"""
import json, random, datetime as dt, math

random.seed(7)
N = 130  # 周频，约 2.5 年
today = dt.date(2026, 10, 30)
dates = [(today - dt.timedelta(days=7 * (N - 1 - i))).isoformat() for i in range(N)]


def walk(start, vol, drift=0.0, lo=None, hi=None):
    v = start; out = []
    for i in range(N):
        v += random.gauss(drift, vol)
        if lo is not None: v = max(lo, v)
        if hi is not None: v = min(hi, v)
        out.append(round(v, 2))
    return out


def line(pid, title, sub, vals, unit="", dec=2, refs=None, note="", pct=None):
    return {"id": pid, "title": title, "subtitle": sub, "type": "line", "unit": unit,
            "decimals": dec, "dates": dates,
            "series": [{"name": title, "values": vals}],
            "current": vals[-1], "pct": pct if pct is not None else random.randint(20, 95),
            "refs": refs or [], "note": note, "available": True, "updated": dates[-1]}


def rebase_multi(base_names, phases):
    series = []
    for name, ph in zip(base_names, phases):
        vals = [round(100 + 18 * math.sin(i / 22 + ph) + i * 0.25, 1) for i in range(N)]
        series.append({"name": name, "values": vals})
    return {"id": "M7", "title": "", "subtitle": "", "type": "rebase", "unit": "基准=100",
            "decimals": 1, "dates": dates, "series": series, "current": None, "pct": None,
            "refs": [], "note": "", "available": True, "updated": dates[-1]}


groups = []
# 估值
groups.append({"name": "估值", "panels": [
    line("M1", "巴菲特指标（市值 / GDP，近似）", "Wilshire5000 / 年化GDP",
         walk(195, 2.2, 0.15, 120, 235), "%", 1,
         [{"value": 100, "label": "合理上沿(100%)", "color": "#e67e22"},
          {"value": 130, "label": "危险(>130%)", "color": "#c0392b"}],
         ">100% 偏贵；>130% 危险区。", 88),
    line("M2", "S&P500 偏离五年均线", "价格相对 5 年均线",
         walk(8, 3.0, 0.05, -30, 35), "%", 1,
         [{"value": 10, "label": "偏贵(>+10%)", "color": "#c0392b"},
          {"value": -20, "label": "底部(<-20%)", "color": "#27ae60"}],
         ">+10% 偏贵；<-20% 底部。", 72),
    line("M3", "实际利率（10Y 美债 − CPI 同比）", "真实资金成本",
         walk(1.2, 0.15, -0.005, -1.5, 3.2), "%", 2,
         [{"value": 0, "label": "零实际利率", "color": "#7f8c8d"},
          {"value": 2, "label": "偏紧(>2%)", "color": "#c0392b"}],
         "实际利率走高=收紧。", 61),
    line("M1b", "席勒 CAPE（周期调整市盈率）", "十年平均盈利口径",
         walk(31, 0.4, 0.02, 22, 40), "倍", 1,
         [{"value": 30, "label": "高估(>30)", "color": "#c0392b"},
          {"value": 15, "label": "偏低(<15)", "color": "#27ae60"}],
         ">30 高估。", 91),
]})
# 情绪/风险
groups.append({"name": "情绪 / 风险", "panels": [
    line("M4", "VIX 恐慌指数", "标普500 隐含波动率",
         walk(19, 3.5, 0, 11, 45), "", 1,
         [{"value": 30, "label": "恐慌(>30)", "color": "#c0392b"},
          {"value": 20, "label": "警戒(20)", "color": "#e67e22"},
          {"value": 15, "label": "自满(<15)", "color": "#27ae60"}],
         ">30 恐慌；<15 自满。", 42),
    line("M5", "信用利差（BAA − 10Y 美债）", "信用紧张度",
         walk(2.0, 0.18, 0.004, 1.3, 4.2), "%", 2,
         [{"value": 3, "label": "紧张(>3%)", "color": "#c0392b"},
          {"value": 2, "label": "正常(<2%)", "color": "#27ae60"}],
         "走阔=信用收缩。", 38),
    line("M6", "收益率曲线倒挂（10Y − 2Y）", "衰退领先指标",
         walk(0.3, 0.12, -0.002, -1.1, 2.4), "%", 2,
         [{"value": 0, "label": "倒挂线(0)", "color": "#c0392b"}],
         "转负=倒挂。", 35),
]})
# 全球
gm = rebase_multi(["SPY 美股大盘", "QQQ 美股科技", "VXUS 发达(美外)",
                   "EEM 新兴市场", "EFA 发达国际"], [0, 1.1, 2.0, 3.2, 2.6])
gm["title"] = "全球股市地图（归一化）"; gm["subtitle"] = "近 5 年重置为 100"
gm["note"] = "谁在上方=资本更青睐；EEM 落后常对应美元强。"
groups.append({"name": "全球 / 世界经济", "panels": [
    gm,
    line("M8", "美元指数（广义贸易加权）", "美元强弱",
         walk(118, 1.4, 0.05, 95, 132), "", 1,
         [{"value": 128, "label": "强美元(>128)", "color": "#c0392b"},
          {"value": 100, "label": "弱美元(<100)", "color": "#27ae60"}],
         "强美元压制新兴市场。", 55),
]})
cm = rebase_multi(["GLD 黄金", "TLT 长债", "DBC 商品"], [0, 1.5, 3.0])
cm["id"] = "M9"; cm["title"] = "避险资产温度计（黄金/长债/商品）"
cm["subtitle"] = "近 5 年重置为 100"; cm["note"] = "黄金上行=避险；商品上行=通胀交易。"
groups[2]["panels"].append(cm)
# 宏观
groups.append({"name": "宏观景气", "panels": [
    line("M10", "失业率 + Sahm 规则", "失业率与衰退信号",
         walk(4.1, 0.1, 0.01, 3.4, 6.5), "%", 1,
         [{"value": 4, "label": "自然失业率(~4%)", "color": "#7f8c8d"},
          {"value": 6, "label": "偏高(>6%)", "color": "#c0392b"}],
         "Sahm 偏离 +0.12pt。", 30),
    line("M11", "通胀（CPI 同比）", "对标 2% 目标",
         walk(3.5, 0.25, -0.01, 1.0, 9.0), "%", 1,
         [{"value": 2, "label": "目标(2%)", "color": "#27ae60"},
          {"value": 5, "label": "过热(>5%)", "color": "#c0392b"}],
         "向 2% 回落=软着陆。", 48),
    {"id": "M12", "title": "衰退信号汇总", "subtitle": "官方 + 曲线 + Sahm",
     "type": "status", "unit": "", "decimals": 2, "dates": [], "series": [],
     "current": None, "pct": None, "refs": [], "available": True, "updated": dates[-1],
     "verdict": "部分预警", "verdict_color": "#e67e22",
     "fields": [{"name": "官方衰退(USREC)", "on": False, "detail": "当前=0"},
                {"name": "收益率曲线倒挂", "on": True, "detail": "10Y-2Y=-0.12%"},
                {"name": "Sahm 规则", "on": False, "detail": "偏离 +0.12pt"}],
     "note": "≥2 项触发视为衰退预警共振。"},
    {**line("M13", "跨资产相关性（风险偏好切换）", "股债/股金 60 日滚动相关",
            walk(-0.1, 0.06, 0, -0.7, 0.45), "", 3,
            [{"value": 0, "label": "零相关(0)", "color": "#7f8c8d"}],
            "SPY-TLT 转正=避险失效。"),
     "pct": None},
]})

bands = [[(today - dt.timedelta(days=7 * 90)).isoformat(),
          (today - dt.timedelta(days=7 * 78)).isoformat()]]

out = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
       "latest": dates[-1], "asof": {p["id"]: dates[-1] for g in groups for p in g["panels"]},
       "groups": groups, "bands": bands,
       "meta": {"title": "美股 / 世界经济温度计（样例）",
                "subtitle": "13 个面板 · 估值 / 情绪 / 全球 / 宏观",
                "sources": ["FRED", "Yahoo Finance", "Stooq", "multpl(可选)"]}}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print("样例 data.json 已生成：", sum(len(g["panels"]) for g in groups), "个面板")
