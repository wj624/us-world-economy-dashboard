# -*- coding: utf-8 -*-
"""
US / World Economy Dashboard · 指标自动计算引擎
多源抓取(免费/免key) -> 本地缓存(失败回退) -> 计算 13 个面板 -> 输出 data.json

数据源（按"服务器端可靠性"排序）：
  FRED        : 政府经济数据库，无 bot 墙，GitHub Actions 最稳。宏观/估值主力。
                - fredgraph.csv 免 key 通道(默认) + 官方 API(若设 FRED_API_KEY 则优先，提速率)
  Yahoo Finance: 美股/全球 ETF 与指数日线(v8 chart API，无 key)。价格主力。
  Stooq       : 价格兜底(CSV，无 key)。Yahoo 被墙时使用。
  multpl.com  : 席勒 CAPE(可选增强，失败即跳过)。

架构沿用 earl-etf-dashboard：本脚本只产出 data.json，
build.py 把 template.html + echarts + data.json 打包成自包含 index.html。
"""
import os, io, sys, json, time, math, datetime as dt, tempfile, threading
import urllib.request, urllib.parse, ssl

try:
    import numpy as np
except ImportError:
    np = None

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache")
os.makedirs(CACHE, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
TRIES = 3
HTTP_TIMEOUT = 25

# 逻辑名 -> (Yahoo 代码, Stooq 代码)
PRICE = {
    "SPY 美股大盘": ("SPY", "spy.us"),
    "QQQ 美股科技": ("QQQ", "qqq.us"),
    "VXUS 发达(美外)": ("VXUS", "vxus.us"),
    "EEM 新兴市场": ("EEM", "eem.us"),
    "EFA 发达国际": ("EFA", "efa.us"),
    "GLD 黄金": ("GLD", "gld.us"),
    "TLT 长债": ("TLT", "tlt.us"),
    "DBC 商品": ("DBC", "dbc.us"),
    "UUP 美元": ("UUP", "uup.us"),
    "S&P500": ("^GSPC", "%5Egspc"),
    "纳指": ("^IXIC", "%5Eixic"),
    "道指": ("^DJI", "%5Edji"),
}


# ---------------------------------------------------------------- 抓取底层(线程级硬超时)
def _fetch_raw(url, timeout=HTTP_TIMEOUT):
    box = {}
    def worker():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                box["data"] = r.read().decode("utf-8", "replace")
                box["code"] = r.status
        except Exception as e:
            box["err"] = f"{type(e).__name__}:{str(e)[:60]}"
    t = threading.Thread(target=worker, daemon=True)
    t.start(); t.join(timeout + 4)
    if t.is_alive():
        raise TimeoutError(f"HANG>{timeout + 4}s")
    if "err" in box:
        raise RuntimeError(box["err"])
    return box["data"], box["code"]


def http_text(url, tries=TRIES, timeout=HTTP_TIMEOUT):
    last = None
    for i in range(tries):
        try:
            txt, code = _fetch_raw(url, timeout=timeout)
            if code == 200 and txt:
                return txt
            last = f"HTTP {code}"
        except Exception as e:
            last = str(e)[:80]
        time.sleep(1.2 * (i + 1))
    raise RuntimeError(last or "empty")


# ---------------------------------------------------------------- 缓存
def _cpath(name):
    return os.path.join(CACHE, name)


def load_cache(name):
    p = _cpath(name)
    try:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return None


def save_cache(name, text):
    try:
        with open(_cpath(name), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _parse_fred_csv(raw):
    out = []
    for line in raw.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v in (".", "", "NaN"):
            continue
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def fetch_fred(series_id):
    """FRED: 有 key 走 API(快)，否则 fredgraph.csv 免 key；失败回退缓存。"""
    cache_name = f"fred_{series_id}.csv"
    if FRED_API_KEY:
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json")
            j = json.loads(http_text(url))
            out = []
            for ob in (j.get("observations") or []):
                d, v = ob.get("date"), ob.get("value")
                if d and v not in (None, ".", ""):
                    try:
                        out.append((d, float(v)))
                    except (ValueError, TypeError):
                        pass
            if out:
                save_cache(cache_name, "\n".join(f"{d},{v}" for d, v in out))
                return out
        except Exception as e:
            log(f"    FRED API {series_id} 失败({e})，转免 key 通道")
    try:
        raw = http_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
        out = _parse_fred_csv(raw)
        if out:
            save_cache(cache_name, "\n".join(f"{d},{v}" for d, v in out))
            return out
    except Exception as e:
        log(f"    FRED {series_id} 失败({e})")
    cached = load_cache(cache_name)
    if cached:
        log(f"    FRED {series_id} 用缓存兜底")
        return [(d, float(v)) for d, v in (l.split(",") for l in cached.splitlines() if l)]
    return []


def fetch_yahoo(symbol, rng="5y"):
    """Yahoo v8 chart API -> [(date, close)]。query1/query2 容错。"""
    sym = symbol.replace("^", "%5E")
    cache_name = f"yahoo_{symbol.replace('^','idx')}.csv"
    for host in ("query1", "query2"):
        try:
            url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?range={rng}&interval=1d")
            j = json.loads(http_text(url, tries=2, timeout=20))
            res = ((j.get("chart") or {}).get("result") or [])
            if not res:
                continue
            r0 = res[0]
            ts = r0.get("timestamp") or []
            closes = (((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
            out = []
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
                out.append((d, float(c)))
            if out:
                save_cache(cache_name, "\n".join(f"{d},{v}" for d, v in out))
                return out
        except Exception as e:
            log(f"    Yahoo {symbol}@{host} 失败({e})")
    cached = load_cache(cache_name)
    if cached:
        log(f"    Yahoo {symbol} 用缓存兜底")
        return [(l.split(",")[0], float(l.split(",")[1])) for l in cached.splitlines() if l]
    return []


def fetch_stooq(symbol):
    cache_name = f"stooq_{symbol.replace('%5E','idx')}.csv"
    try:
        raw = http_text(f"https://stooq.com/q/d/l/?s={symbol}&i=d")
        rows = raw.strip().splitlines()
        if rows and not rows[0].lower().startswith("date"):
            # 挑战页/空页
            if "<html" in raw[:200].lower():
                raise RuntimeError("challenge page")
        out = []
        for line in rows[1:]:
            p = line.split(",")
            if len(p) < 5:
                continue
            try:
                c = float(p[4])
            except ValueError:
                continue
            if c != c:
                continue
            out.append((p[0].strip(), c))
        if out:
            save_cache(cache_name, raw)
            return out
    except Exception as e:
        log(f"    Stooq {symbol} 失败({e})")
    cached = load_cache(cache_name)
    if cached:
        log(f"    Stooq {symbol} 用缓存兜底")
        return [(r.split(",")[0], float(r.split(",")[4])) for r in cached.strip().splitlines()[1:]
                if len(r.split(",")) >= 5]
    return []


def fetch_price(name):
    ys, ss = PRICE[name]
    d = fetch_yahoo(ys)
    if d:
        return d
    d = fetch_stooq(ss)
    return d or []


# ---------------------------------------------------------------- 工具
def log(m):
    try:
        print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)
    except Exception:
        print(m, flush=True)


def pct_of(value, pairs, since=None):
    vals = [v for d, v in pairs if (since is None or d >= since) and v == v]
    if not vals or value != value:
        return None
    if np is not None:
        arr = np.array(vals)
        return round(float(np.sum(arr <= value)) / len(arr) * 100, 1)
    return round(sum(1 for v in vals if v <= value) / len(vals) * 100, 1)


def trim(pairs, since):
    return [(d, v) for d, v in pairs if d >= since]


def last(pairs):
    return pairs[-1] if pairs else (None, None)


def rebase(series, since, base=100.0):
    names = list(series.keys())
    if not names:
        return {}
    cand = set(d for d, _ in series[names[0]] if d >= since)
    for n in names[1:]:
        cand &= set(d for d, _ in series[n] if d >= since)
    if not cand:
        return {}
    base_date = min(cand)
    out = {}
    for n in names:
        smap = dict(series[n])
        bv = smap.get(base_date)
        if not bv:
            continue
        out[n] = [(d, round(v / bv * base, 2)) for d, v in series[n] if d >= base_date]
    return out


def daily_returns(pairs):
    out = []
    for i in range(1, len(pairs)):
        _, c0 = pairs[i - 1]
        d1, c1 = pairs[i]
        if c0 and c0 == c0:
            out.append((d1, (c1 - c0) / c0))
    return out


def rolling_corr(a, b, window=60):
    da, db = dict(a), dict(b)
    common = sorted(set(da) & set(db))
    if len(common) < window + 1 or np is None:
        return []
    ca = [da[d] for d in common]
    cb = [db[d] for d in common]
    out = []
    for i in range(window, len(common)):
        wa = ca[i - window:i]; wb = cb[i - window:i]
        if np.std(wa) == 0 or np.std(wb) == 0:
            out.append((common[i], 0.0)); continue
        out.append((common[i], round(float(np.corrcoef(wa, wb)[0, 1]), 3)))
    return out


def yoy(monthly):
    """月度序列 -> 同比 % [(date, yoy)]。"""
    out = []
    for i in range(12, len(monthly)):
        d, v = monthly[i]
        v12 = monthly[i - 12][1]
        if v12:
            out.append((d, (v / v12 - 1) * 100))
    return out


def recession_bands(usrec):
    bands = []; start = None
    for d, v in usrec:
        on = v >= 0.5
        if on and start is None:
            start = d
        elif not on and start is not None:
            bands.append([start, d]); start = None
    if start is not None and usrec:
        bands.append([start, usrec[-1][0]])
    return bands


def panel_line(pid, title, subtitle, pairs, since, unit="", refs=None,
               pct_baseline=None, note="", decimals=2, ctype="line"):
    if not pairs:
        return None
    cur = pairs[-1][1]
    disp = trim(pairs, since)
    if not disp:
        return None
    pct = pct_of(cur, pairs, pct_baseline) if pct_baseline else pct_of(cur, pairs)
    return {
        "id": pid, "title": title, "subtitle": subtitle, "type": ctype,
        "unit": unit, "decimals": decimals, "dates": [d for d, _ in disp],
        "series": [{"name": title, "values": [round(float(v), decimals) for _, v in disp]}],
        "current": round(float(cur), decimals), "pct": pct,
        "refs": refs or [], "note": note, "available": True, "updated": pairs[-1][0],
    }


# ---------------------------------------------------------------- 估值(全 FRED)
def build_buffett():
    """巴菲特指标 ≈ Wilshire5000 总市值指数 / 年化GDP。"""
    w = fetch_fred("WILL5000INDFC")
    g = fetch_fred("GDP")            # 季度，$B 年化
    if not w or not g:
        return None
    g.sort()
    pairs = []
    j = 0; cur_g = None
    for d, v in w:
        while j < len(g) and g[j][0] <= d:
            cur_g = g[j][1]; j += 1
        if cur_g:
            pairs.append((d, v / cur_g * 100))
    return panel_line("M1", "巴菲特指标（市值 / GDP，近似）",
                      "Wilshire5000 总市值指数 / 年化 GDP，整体估值温度计",
                      pairs, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                      refs=[{"value": 100, "label": "合理上沿(100%)", "color": "#e67e22"},
                            {"value": 130, "label": "危险(>130%)", "color": "#c0392b"}],
                      note=">100% 偏贵；>130% 危险区；<75% 低估。（Wilshire5000/GDP 近似，绝对值略高于市值口径）")


def build_sp_anchor():
    """S&P500 相对五年均线(1250 交易日)偏离度。"""
    raw = fetch_fred("SP500")
    if len(raw) < 1300:
        return None
    vals = [v for _, v in raw]
    dev = []; cum = 0.0
    win = 1250
    for i, (d, v) in enumerate(raw):
        cum += v
        if i >= win:
            cum -= vals[i - win]
        if i >= win - 1:
            ma = cum / win
            if ma:
                dev.append((d, (v / ma - 1) * 100))
    return panel_line("M2", "S&P500 偏离五年均线",
                      "价格相对 5 年均线的贵贱，类『五年之锚』",
                      dev, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                      refs=[{"value": 10, "label": "偏贵(>+10%)", "color": "#c0392b"},
                            {"value": -20, "label": "底部(<-20%)", "color": "#27ae60"}],
                      note=">+10% 偏贵；<-20% 历史底部区。偏离度越高越贵。")


def build_real_rate():
    """实际利率 = 10Y 美债 − CPI 同比。"""
    dgs = fetch_fred("DGS10")
    cpi = fetch_fred("CPIAUCSL")
    if not dgs or len(cpi) < 13:
        return None
    cy = yoy(cpi)
    dmap = dict(dgs)
    pairs = [(d, dmap[d] - y) for d, y in cy if d in dmap]
    if len(pairs) < 30:
        return None
    return panel_line("M3", "实际利率（10Y 美债 − CPI 同比）",
                      "剔除通胀后的真实资金成本，越高股市越受压",
                      pairs, since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                      refs=[{"value": 0, "label": "零实际利率", "color": "#7f8c8d"},
                            {"value": 2, "label": "偏紧(>2%)", "color": "#c0392b"}],
                      note="实际利率转正且走高=金融环境收紧，压制估值；负值=宽松利好股市。")


def build_cape():
    """席勒 CAPE（multpl，可选增强）。"""
    raw = fetch_multpl("shiller-pe")
    if not raw:
        return None
    return panel_line("M1b", "席勒 CAPE（周期调整市盈率）",
                      "经通胀调整的十年平均盈利口径，美股长期贵贱",
                      raw, since="2005-01-01", unit="倍", pct_baseline="1990-01-01",
                      refs=[{"value": 30, "label": "高估(>30)", "color": "#c0392b"},
                            {"value": 15, "label": "偏低(<15)", "color": "#27ae60"}],
                      note=">30 高估(2000年达44)；<15 历史极低。")


def fetch_multpl(endpoint):
    cache_name = f"multpl_{endpoint.replace('/', '_')}.json"
    try:
        raw = http_text(f"https://www.multpl.com/{endpoint}/table?extra=1&f=json", tries=2)
        j = json.loads(raw)
        if isinstance(j, list):
            out = []
            for row in j:
                ds, vs = row.get("date"), row.get("value")
                d = _parse_any_date(ds)
                if d and vs not in (None, ""):
                    try:
                        out.append((d, float(str(vs).replace(",", ""))))
                    except ValueError:
                        pass
            if out:
                save_cache(cache_name, raw)
                return out
    except Exception as e:
        log(f"    multpl {endpoint} 失败({e})")
    cached = load_cache(cache_name)
    if cached:
        try:
            j = json.loads(cached)
            out = []
            for row in j:
                d = _parse_any_date(row.get("date"))
                if d:
                    out.append((d, float(str(row.get("value")).replace(",", ""))))
            return out
        except Exception:
            return []
    return []


def _parse_any_date(ds):
    if not ds:
        return None
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(ds, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- 情绪/风险(FRED)
def build_vix():
    raw = fetch_fred("VIXCLS")
    if not raw:
        return None
    return panel_line("M4", "VIX 恐慌指数", "标普500 30 天隐含波动率",
                      raw, since="2005-01-01", unit="", pct_baseline="1990-01-01",
                      refs=[{"value": 30, "label": "恐慌(>30)", "color": "#c0392b"},
                            {"value": 20, "label": "警戒(20)", "color": "#e67e22"},
                            {"value": 15, "label": "自满(<15)", "color": "#27ae60"}],
                      note=">30 市场恐慌；15-20 正常；<15 过度自满，风险积累。")


def build_credit():
    raw = fetch_fred("BAA10Y")
    if not raw:
        return None
    return panel_line("M5", "信用利差（BAA − 10Y 美债）",
                      "高收益债相对国债的溢价，衡量信用紧张度",
                      raw, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                      refs=[{"value": 3, "label": "紧张(>3%)", "color": "#c0392b"},
                            {"value": 2, "label": "正常(<2%)", "color": "#27ae60"}],
                      note="利差走阔=信用收缩、避险升温；>4% 多为危机边缘。")


def build_curve():
    raw = fetch_fred("T10Y2Y")
    if not raw:
        return None
    return panel_line("M6", "收益率曲线倒挂（10Y − 2Y）",
                      "长短端利差，经典衰退领先指标",
                      raw, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                      refs=[{"value": 0, "label": "倒挂线(0)", "color": "#c0392b"}],
                      note="转负=曲线倒挂，历次衰退前都出现，领先 6-18 个月。")


# ---------------------------------------------------------------- 全球(价格)
def build_global_map():
    names = ["SPY 美股大盘", "QQQ 美股科技", "VXUS 发达(美外)", "EEM 新兴市场", "EFA 发达国际"]
    series = {}
    for n in names:
        d = fetch_price(n)
        if d:
            series[n] = d
    if len(series) < 2:
        return None
    since = (dt.date.today() - dt.timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    rb = rebase(series, since)
    if not rb:
        return None
    dates = [d for d, _ in next(iter(rb.values()))]
    return {
        "id": "M7", "title": "全球股市地图（归一化）",
        "subtitle": "近 5 年各自重置为 100，看资金全球偏好切换",
        "type": "rebase", "unit": "基准=100", "decimals": 1,
        "dates": dates,
        "series": [{"name": n, "values": [v for _, v in rb[n]]} for n in rb],
        "current": None, "pct": None, "refs": [],
        "note": "谁在上方=资本更青睐；EEM 落后常对应美元强/避险。",
        "available": True, "updated": dates[-1] if dates else None,
    }


def build_dollar():
    raw = fetch_fred("DTWEXBGS")
    if not raw:
        return None
    return panel_line("M8", "美元指数（广义贸易加权）",
                      "美元对一篮子主要贸易伙伴货币的强弱",
                      raw, since="2005-01-01", unit="", pct_baseline="2000-01-01",
                      refs=[{"value": 128, "label": "强美元(>128)", "color": "#c0392b"},
                            {"value": 100, "label": "弱美元(<100)", "color": "#27ae60"}],
                      note="强美元压制新兴市场与大宗；弱美元利好全球风险资产。")


def build_commodities():
    names = ["GLD 黄金", "TLT 长债", "DBC 商品"]
    series = {}
    for n in names:
        d = fetch_price(n)
        if d:
            series[n] = d
    if len(series) < 2:
        return None
    since = (dt.date.today() - dt.timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    rb = rebase(series, since)
    if not rb:
        return None
    dates = [d for d, _ in next(iter(rb.values()))]
    return {
        "id": "M9", "title": "避险资产温度计（黄金/长债/商品）",
        "subtitle": "近 5 年各自重置为 100，看避险 vs 通胀交易",
        "type": "rebase", "unit": "基准=100", "decimals": 1,
        "dates": dates,
        "series": [{"name": n, "values": [v for _, v in rb[n]]} for n in rb],
        "current": None, "pct": None, "refs": [],
        "note": "黄金上行=避险/实际利率下行；商品上行=通胀交易。",
        "available": True, "updated": dates[-1] if dates else None,
    }


# ---------------------------------------------------------------- 宏观(FRED)
def _sahm(unrate):
    vals = [(dt.datetime.strptime(d, "%Y-%m-%d"), v) for d, v in unrate]
    vals.sort()
    rates = [v for _, v in vals]
    if len(rates) < 4:
        return None
    cur3 = sum(rates[-3:]) / 3
    win = rates[:-3][-12:] if len(rates) > 3 else rates
    if not win:
        return None
    low = min(sum(win[i:i + 3]) / 3 for i in range(max(1, len(win) - 2)))
    return cur3 - low


def build_unemployment():
    raw = fetch_fred("UNRATE")
    if not raw:
        return None
    p = panel_line("M10", "失业率 + Sahm 规则", "失业率与经典衰退先行信号",
                   raw, since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                   refs=[{"value": 4, "label": "自然失业率(~4%)", "color": "#7f8c8d"},
                         {"value": 6, "label": "偏高(>6%)", "color": "#c0392b"}],
                   note="Sahm 规则：3 月均失业比前 12 月低点抬升 >0.5pt 即触发衰退信号。")
    s = _sahm(raw)
    if p and s is not None:
        p["note"] = f"Sahm 偏离 {s:+.2f}pt（>0.5 触发衰退信号）；" + p["note"]
    return p


def build_inflation():
    raw = fetch_fred("CPIAUCSL")
    if len(raw) < 13:
        return None
    return panel_line("M11", "通胀（CPI 同比）", "居民消费价格同比，对标美联储 2% 目标",
                      yoy(raw), since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                      refs=[{"value": 2, "label": "目标(2%)", "color": "#27ae60"},
                            {"value": 5, "label": "过热(>5%)", "color": "#c0392b"}],
                      note=">5% 通胀过热；向 2% 回落=软着陆路径。")


def build_recession():
    usrec = fetch_fred("USREC")
    curve = fetch_fred("T10Y2Y")
    unrate = fetch_fred("UNRATE")
    sig = []
    if usrec:
        cur = usrec[-1][1]
        sig.append(("官方衰退(USREC)", cur >= 0.5, f"当前={cur:g}"))
    if curve:
        cur = curve[-1][1]
        sig.append(("收益率曲线倒挂", cur < 0, f"10Y-2Y={cur:+.2f}%"))
    s = _sahm(unrate) if unrate else None
    if s is not None:
        sig.append(("Sahm 规则", s > 0.5, f"偏离 {s:+.2f}pt"))
    if not sig:
        return None
    trig = sum(1 for _, on, _ in sig if on)
    verdict = "衰退信号活跃" if trig >= 2 else ("部分预警" if trig == 1 else "暂无衰退信号")
    color = "#c0392b" if trig >= 2 else ("#e67e22" if trig == 1 else "#27ae60")
    upd = (usrec or curve or unrate)[-1][0]
    return {
        "id": "M12", "title": "衰退信号汇总", "subtitle": "官方判定 + 收益率曲线 + Sahm 三源共振",
        "type": "status", "unit": "", "decimals": 2, "dates": [], "series": [],
        "current": None, "pct": None, "refs": [], "available": True, "updated": upd,
        "verdict": verdict, "verdict_color": color,
        "fields": [{"name": n, "on": on, "detail": d} for n, on, d in sig],
        "note": "≥2 项触发视为衰退预警共振；单一信号多为噪音。",
    }


def build_correlation():
    spy = fetch_price("SPY 美股大盘")
    tlt = fetch_price("TLT 长债")
    gld = fetch_price("GLD 黄金")
    if not spy or not tlt:
        return None
    rs = daily_returns(spy); rt = daily_returns(tlt)
    corr_st = rolling_corr(rs, rt, 60)
    if not corr_st:
        return None
    series = [{"name": "SPY↔TLT 60日相关", "values": [v for _, v in corr_st]}]
    dates = [d for d, _ in corr_st]
    if gld:
        corr_sg = rolling_corr(rs, daily_returns(gld), 60)
        if corr_sg:
            series.append({"name": "SPY↔GLD 60日相关", "values": [v for _, v in corr_sg]})
            dates = [d for d, _ in corr_sg]
    return {
        "id": "M13", "title": "跨资产相关性（风险偏好切换）",
        "subtitle": "股债/股金 60 日滚动相关，负值=正常对冲",
        "type": "line", "unit": "", "decimals": 3, "dates": dates, "series": series,
        "current": corr_st[-1][1], "pct": None,
        "refs": [{"value": 0, "label": "零相关(0)", "color": "#7f8c8d"}],
        "note": "SPY-TLT 转正=股债同跌(避险失效)；负值才是常态对冲。",
        "available": True, "updated": dates[-1] if dates else None,
    }


# ---------------------------------------------------------------- 主流程
def main():
    log("开始抓取并计算面板 …")
    groups = []; asof = {}; ok = 0

    plan = [
        ("估值", [build_buffett, build_sp_anchor, build_real_rate, build_cape]),
        ("情绪 / 风险", [build_vix, build_credit, build_curve]),
        ("全球 / 世界经济", [build_global_map, build_dollar, build_commodities]),
        ("宏观景气", [build_unemployment, build_inflation, build_recession, build_correlation]),
    ]
    for gname, builders in plan:
        panels = []
        for b in builders:
            if b is build_cape and not os.path.isdir(CACHE):
                continue
            try:
                p = b()
            except Exception as e:
                log(f"  [WARN] {b.__name__}: {e}"); p = None
            if p and p.get("available"):
                panels.append(p); asof[p["id"]] = p.get("updated"); ok += 1
                log(f"  ✓ {p['id']} {p['title']}")
            else:
                log(f"  ✗ {b.__name__} 无数据，跳过")
        if panels:
            groups.append({"name": gname, "panels": panels})

    # 衰退阴影带
    bands = []
    try:
        usrec = fetch_fred("USREC")
        if usrec:
            bands = recession_bands(usrec)
    except Exception as e:
        log(f"  衰退阴影带失败：{e}")

    if ok == 0:
        log("所有面板均失败，写空壳 data.json 并退出非零")
        shell = {"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "latest": "", "asof": {}, "groups": [], "bands": [], "error": "all_sources_failed"}
        _atomic_write("data.json", json.dumps(shell, ensure_ascii=False))
        sys.exit(1)

    latest = max([a for a in asof.values() if a] or [""])
    out = {
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "latest": latest, "asof": asof, "groups": groups, "bands": bands,
        "meta": {"title": "美股 / 世界经济温度计",
                 "subtitle": "13 个面板 · 估值 / 情绪 / 全球 / 宏观",
                 "sources": ["FRED", "Yahoo Finance", "Stooq", "multpl(可选)"]},
    }
    _atomic_write("data.json", json.dumps(out, ensure_ascii=False))
    log(f"完成：{ok} 个面板写入 data.json（最新行情日 {latest}，衰退带 {len(bands)} 段）")


def _atomic_write(path, text):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".atmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


if __name__ == "__main__":
    main()
