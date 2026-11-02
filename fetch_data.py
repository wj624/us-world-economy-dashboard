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
TRIES = 2
HTTP_TIMEOUT = 15          # 单请求上限；FRED 串行、价格并发，整体耗时有界
RAW = {}                   # 预取缓存：('fred',id)/('price',name)/('multpl',ep) -> 列表
FRED_IDS = ["NASDAQCOM", "SP500", "DGS10", "CPIAUCSL", "VIXCLS",
            "BAA10Y", "T10Y2Y", "DTWEXBGS", "UNRATE", "USREC",
            "VXVCLS", "T10Y3M", "ICSA", "PCEPILFE", "T5YIE",
            "A191RL1Q225SBEA", "UMCSENT", "DFF", "NCBEILQ027S", "GDP"]
PRICE_NAMES = ["SPY 美股大盘", "QQQ 美股科技", "VXUS 发达(美外)", "EEM 新兴市场",
               "EFA 发达国际", "GLD 黄金", "TLT 长债", "DBC 商品"]

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


# ---- 当日 TTL + 增量缓存 ----
_TTL_FILE = os.path.join(CACHE, "_ttl.json")
_TTL = {}
_TTL_LOADED = False


def _today():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _force_refresh():
    return os.environ.get("FORCE_REFRESH", "").lower() in ("1", "true", "yes")


def _load_ttl():
    global _TTL, _TTL_LOADED
    if _TTL_LOADED:
        return
    try:
        if os.path.exists(_TTL_FILE):
            with open(_TTL_FILE, encoding="utf-8") as f:
                _TTL = json.load(f) or {}
    except Exception:
        _TTL = {}
    _TTL_LOADED = True


def _save_ttl():
    try:
        with open(_TTL_FILE, "w", encoding="utf-8") as f:
            json.dump(_TTL, f)
    except Exception:
        pass


def _ttl_hit(key):
    """今天已抓过、且非强制刷新 -> 命中，可跳过网络。"""
    _load_ttl()
    return (not _force_refresh()) and _TTL.get(key) == _today()


def _ttl_mark(key):
    _load_ttl()
    _TTL[key] = _today()
    _save_ttl()


def _read_pairs(cache_name):
    """读 'date,value' 缓存 -> [(date, float)]。"""
    txt = load_cache(cache_name)
    if not txt:
        return []
    out = []
    for line in txt.splitlines():
        p = line.split(",")
        if len(p) < 2:
            continue
        try:
            out.append((p[0].strip(), float(p[1])))
        except ValueError:
            continue
    return out


def _dumps_pairs(pairs):
    return "\n".join(f"{d},{v}" for d, v in pairs)


def _merge_pairs(old, new):
    """按日期合并（new 覆盖 old），返回升序列表。"""
    m = {d: v for d, v in old}
    for d, v in new:
        m[d] = v
    return sorted(m.items())


def _minus_days(date_str, n):
    try:
        return (dt.datetime.strptime(date_str, "%Y-%m-%d") - dt.timedelta(days=n)).strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_fred_api(raw):
    j = json.loads(raw)
    out = []
    for ob in (j.get("observations") or []):
        d, v = ob.get("date"), ob.get("value")
        if d and v not in (None, ".", ""):
            try:
                out.append((d, float(v)))
            except (ValueError, TypeError):
                pass
    return out


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
    """FRED: 官方 API(有 key)为主，fredgraph 兜底；带『当日 TTL』+『增量抓取』。
    - TTL：今天已抓过且缓存存在 -> 直接用缓存，不再请求（省调用/防限流）。
    - 增量：有缓存 -> 只从『缓存最后日期 − 10 天』开始取，再合并（留重叠吸收修订）。
    - 失败：用缓存兜底。设 FORCE_REFRESH=1 可强制全量重抓。
    """
    if ("fred", series_id) in RAW:
        return RAW[("fred", series_id)]
    cache_name = f"fred_{series_id}.csv"
    ttl_key = f"fred:{series_id}"
    cached = _read_pairs(cache_name)

    if cached and _ttl_hit(ttl_key):
        return cached

    start = _minus_days(cached[-1][0], 10) if (cached and not _force_refresh()) else None

    if FRED_API_KEY:
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json")
            if start:
                url += f"&observation_start={start}"
            out = _parse_fred_api(http_text(url))
            if out:
                merged = _merge_pairs(cached, out)
                save_cache(cache_name, _dumps_pairs(merged))
                _ttl_mark(ttl_key)
                return merged
            if cached:                       # 增量无新数据（如月度序列）
                _ttl_mark(ttl_key)
                return cached
        except Exception as e:
            log(f"    FRED API {series_id} 失败({e})")
            if cached:                       # 有缓存就不再空等被墙的 fredgraph
                log(f"    FRED {series_id} 用缓存兜底")
                return cached

    if not cached:                           # 仅首次（无缓存）才尝试 fredgraph 全量
        try:
            raw = http_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=1990-01-01")
            out = _parse_fred_csv(raw)
            if out:
                save_cache(cache_name, _dumps_pairs(out))
                _ttl_mark(ttl_key)
                return out
        except Exception as e:
            log(f"    FRED {series_id} 失败({e})")

    return cached


def fetch_yahoo(symbol, rng="5y"):
    """Yahoo v8 chart API -> [(date, close)]。query1/query2 容错；带当日 TTL。"""
    sym = symbol.replace("^", "%5E")
    cache_name = f"yahoo_{symbol.replace('^','idx')}.csv"
    ttl_key = f"yahoo:{symbol}"
    cached = _read_pairs(cache_name)
    if cached and _ttl_hit(ttl_key):
        return cached
    for host in ("query1", "query2"):
        try:
            url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?range={rng}&interval=1d")
            j = json.loads(http_text(url, tries=1, timeout=8))
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
                save_cache(cache_name, _dumps_pairs(out))
                _ttl_mark(ttl_key)
                return out
        except Exception as e:
            log(f"    Yahoo {symbol}@{host} 失败({e})")
    if cached:
        log(f"    Yahoo {symbol} 用缓存兜底")
        return cached
    return []


def _parse_stooq_text(raw):
    out = []
    for line in raw.strip().splitlines()[1:]:
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
    return out


def fetch_stooq(symbol):
    cache_name = f"stooq_{symbol.replace('%5E','idx')}.csv"
    ttl_key = f"stooq:{symbol}"
    cached_txt = load_cache(cache_name)
    if cached_txt and _ttl_hit(ttl_key):
        return _parse_stooq_text(cached_txt)
    try:
        raw = http_text(f"https://stooq.com/q/d/l/?s={symbol}&i=d", tries=1, timeout=8)
        if "<html" in raw[:200].lower():
            raise RuntimeError("challenge page")
        out = _parse_stooq_text(raw)
        if out:
            save_cache(cache_name, raw)
            _ttl_mark(ttl_key)
            return out
    except Exception as e:
        log(f"    Stooq {symbol} 失败({e})")
    if cached_txt:
        log(f"    Stooq {symbol} 用缓存兜底")
        return _parse_stooq_text(cached_txt)
    return []


def fetch_price(name):
    if ("price", name) in RAW:
        return RAW[("price", name)]
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
    """美股长期估值偏离：纳指综指(NASDAQCOM, 1980 起) 剔除通胀后的实际价格，
    相对 10 年均线(2500 交易日)的偏离。S&P/DJIA 在 FRED 受授权限制仅 2016 起，
    故用长历史的纳指做「长期估值温度计」，分位可追溯至 1990。"""
    idx = fetch_fred("NASDAQCOM")
    cpi = fetch_fred("CPIAUCSL")
    if len(idx) < 2600 or not cpi:
        return None
    cpi_sorted = sorted(cpi)
    j = 0; cur_cpi = None; real = []
    for d, v in idx:
        while j < len(cpi_sorted) and cpi_sorted[j][0] <= d:
            cur_cpi = cpi_sorted[j][1]; j += 1
        if cur_cpi:
            real.append((d, v / cur_cpi))
    if len(real) < 2600:
        return None
    vals = [v for _, v in real]
    win = 2500
    dev = []; cum = 0.0
    for i, (d, v) in enumerate(real):
        cum += v
        if i >= win:
            cum -= vals[i - win]
        if i >= win - 1 and cum:
            ma = cum / win
            dev.append((d, (v / ma - 1) * 100))
    return panel_line("M1", "美股长期估值偏离（纳指·10年·实际价格）",
                      "剔除通胀后的纳指相对 10 年均线偏离，长期贵贱",
                      dev, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                      refs=[{"value": 20, "label": "偏贵(>+20%)", "color": "#c0392b"},
                            {"value": -20, "label": "偏低(<-20%)", "color": "#27ae60"}],
                      note=">+20% 长期偏贵、<-20% 长期低位；实际价格已剔除通胀，跨年代可比（长历史用纳指代理）。")


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


def build_buffett_m1b():
    """M1b 巴菲特指标 ≈ 股权总市值 / GDP（FRED 资金流量表，季度·4季平滑）。
    官方市值为季度、滞后约一季度；再按标普 500 自该季至今的涨幅外推一个『当前估算(nowcast)』。"""
    cap = fetch_fred("NCBEILQ027S")
    gdp = sorted(fetch_fred("GDP"))
    if not cap or not gdp:
        return None
    pairs = []; j = 0; cur = None
    for d, v in cap:
        while j < len(gdp) and gdp[j][0] <= d:
            cur = gdp[j][1]; j += 1
        if cur:
            pairs.append((d, (v / 1000.0) / cur * 100))
    if len(pairs) < 40:
        return None
    sm = [(pairs[i][0], sum(p[1] for p in pairs[i - 3:i + 1]) / 4) for i in range(3, len(pairs))]
    p = panel_line("M1b", "巴菲特指标（股权市值 / GDP）",
                   "整体估值水平，美联储资金流量表口径（季度·4季平滑）",
                   sm, since="2005-01-01", unit="%", pct_baseline="1990-01-01",
                   refs=[{"value": 200, "label": "偏高(>200%)", "color": "#c0392b"},
                         {"value": 120, "label": "长期均值(~120%)", "color": "#7f8c8d"}],
                   note="股权总市值/GDP；越高越贵。口径比常见 Buffett 略宽，重在趋势与分位。")

    # nowcast：最新官方市值 × 标普涨幅，÷ 最新 GDP
    sp = fetch_fred("SP500")
    base_date, base_cap = cap[-1][0], cap[-1][1]
    base_sp = None
    for d, v in sp:
        if d <= base_date:
            base_sp = v
        else:
            break
    if p and base_sp and sp:
        factor = sp[-1][1] / base_sp
        now_val = sm[-1][1] * factor          # 对图上最后一个平滑值按标普涨幅外推，图和数字一致
        p["nowcast"] = {"value": round(now_val, 1), "asof": sp[-1][0],
                        "base": base_date, "factor": round(factor, 3)}
        p["current"] = round(now_val, 1)
        p["pct"] = pct_of(now_val, sm, "1990-01-01")
        p["updated"] = sp[-1][0]
        p["dates"].append(sp[-1][0])
        p["series"][0]["values"].append(round(now_val, 2))
        p["note"] = p["note"] + f"　末点为按标普涨幅外推的估算（官方市值截至 {base_date[:7]}）。"
    return p


def _parse_multpl_text(raw):
    try:
        j = json.loads(raw)
    except Exception:
        return []
    if not isinstance(j, list):
        return []
    out = []
    for row in j:
        d = _parse_any_date(row.get("date"))
        vs = row.get("value")
        if d and vs not in (None, ""):
            try:
                out.append((d, float(str(vs).replace(",", ""))))
            except ValueError:
                pass
    return out


def fetch_multpl(endpoint):
    if ("multpl", endpoint) in RAW:
        return RAW[("multpl", endpoint)]
    cache_name = f"multpl_{endpoint.replace('/', '_')}.json"
    ttl_key = f"multpl:{endpoint}"
    cached_txt = load_cache(cache_name)
    if cached_txt and _ttl_hit(ttl_key):
        return _parse_multpl_text(cached_txt)
    try:
        raw = http_text(f"https://www.multpl.com/{endpoint}/table?extra=1&f=json", tries=2)
        out = _parse_multpl_text(raw)
        if out:
            save_cache(cache_name, raw)
            _ttl_mark(ttl_key)
            return out
    except Exception as e:
        log(f"    multpl {endpoint} 失败({e})")
    if cached_txt:
        return _parse_multpl_text(cached_txt)
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


# ---------------------------------------------------------------- 新增面板(第二批·全 FRED)
def build_vix_term():
    """VIX 期限结构 = VIX / VIX3M。>1 说明短端恐慌、曲线倒挂。"""
    vix = fetch_fred("VIXCLS"); vix3 = fetch_fred("VXVCLS")
    if not vix or not vix3:
        return None
    m3 = dict(vix3)
    pairs = [(d, v / m3[d]) for d, v in vix if d in m3 and m3[d]]
    if len(pairs) < 100:
        return None
    return panel_line("M14", "VIX 期限结构（VIX / VIX3M）",
                      "比值>1=短端恐慌、期限倒挂", pairs, since="2010-01-01", unit="倍",
                      pct_baseline="2010-01-01", decimals=3,
                      refs=[{"value": 1.0, "label": "倒挂线(1.0)", "color": "#c0392b"}],
                      note=">1 短端恐慌(期限倒挂)，常伴急跌；<0.85 过度自满。")


def build_curve3m():
    """10Y − 3M 利差，Fed 官方更看重的倒挂口径。"""
    raw = fetch_fred("T10Y3M")
    if not raw:
        return None
    return panel_line("M15", "收益率曲线（10Y − 3M）",
                      "Fed 更看重的倒挂口径", raw, since="2005-01-01", unit="%",
                      pct_baseline="2000-01-01", decimals=2,
                      refs=[{"value": 0, "label": "倒挂线(0)", "color": "#c0392b"}],
                      note="<0 倒挂=衰退预警；Fed 常用 10Y-3M 而非 10Y-2Y。")


def build_claims():
    """初请失业金 4 周均（周频，劳动力市场领先指标）。"""
    raw = fetch_fred("ICSA")
    if len(raw) < 60:
        return None
    vals = [v for _, v in raw]
    ma4 = [(raw[i][0], sum(vals[i - 3:i + 1]) / 4.0) for i in range(3, len(raw))]
    ic_yoy = None
    if len(ma4) >= 53 and ma4[-53][1]:
        ic_yoy = (ma4[-1][1] / ma4[-53][1] - 1) * 100
    p = panel_line("M16", "初请失业金（4周均）", "周频劳动力市场领先指标",
                   ma4, since="2005-01-01", unit="人", pct_baseline="2000-01-01", decimals=0,
                   refs=[{"value": 300000, "label": "30万", "color": "#7f8c8d"}],
                   note="4 周均持续抬升=劳动力走弱；同比>+15% 需警惕。")
    if p:
        p["ic_yoy"] = round(ic_yoy, 1) if ic_yoy is not None else None
    return p


def build_core_pce():
    """核心 PCE 同比（Fed 通胀目标口径）。"""
    raw = fetch_fred("PCEPILFE")
    if len(raw) < 13:
        return None
    return panel_line("M17", "核心 PCE 同比", "剔除食品能源，Fed 通胀目标口径",
                      yoy(raw), since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                      refs=[{"value": 2, "label": "目标(2%)", "color": "#27ae60"},
                            {"value": 3, "label": "偏高(>3)", "color": "#c0392b"}],
                      note="Fed 2% 目标的官方口径；>3% 通胀顽固。")


def build_breakeven():
    """5 年通胀预期（国债盈亏平衡）。"""
    raw = fetch_fred("T5YIE")
    if not raw:
        return None
    return panel_line("M18", "5年通胀预期（盈亏平衡）", "债市定价的未来 5 年通胀",
                      raw, since="2005-01-01", unit="%", pct_baseline="2003-01-01",
                      refs=[{"value": 2, "label": "目标(2%)", "color": "#27ae60"},
                            {"value": 2.5, "label": "升温(>2.5)", "color": "#e67e22"}],
                      note="市场定价的通胀预期，领先 CPI；>2.5% 预期升温。")


def build_gdp():
    """实际 GDP 增速（季调环比折年）。"""
    raw = fetch_fred("A191RL1Q225SBEA")
    if not raw:
        return None
    return panel_line("M19", "实际 GDP 增速（季调环比折年）", "美国经济基本面",
                      raw, since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                      refs=[{"value": 0, "label": "零增长", "color": "#c0392b"},
                            {"value": 2, "label": "趋势(2%)", "color": "#7f8c8d"}],
                      note="<0 收缩；持续<1 增长乏力。")


def build_sentiment():
    """密歇根消费者信心。"""
    raw = fetch_fred("UMCSENT")
    if not raw:
        return None
    return panel_line("M20", "密歇根消费者信心", "需求端景气", raw, since="2005-01-01",
                      unit="", pct_baseline="2000-01-01", decimals=1,
                      refs=[{"value": 80, "label": "中性(80)", "color": "#7f8c8d"},
                            {"value": 70, "label": "低迷(<70)", "color": "#c0392b"}],
                      note="<70 信心低迷，预示消费走弱。")


def build_fedfunds():
    """联邦基金有效利率（政策利率水平）。"""
    raw = fetch_fred("DFF")
    if not raw:
        return None
    return panel_line("M21", "联邦基金利率（有效）", "美联储政策利率水平",
                      raw, since="2005-01-01", unit="%", pct_baseline="2000-01-01",
                      refs=[{"value": 5, "label": "紧缩(>5)", "color": "#c0392b"},
                            {"value": 0, "label": "零利率", "color": "#27ae60"}],
                      note="政策利率；高位=紧缩、压制风险资产。")


# ---------------------------------------------------------------- 主流程
def prefetch_all():
    """价格并发（不同主机，互不影响）；FRED 串行（并发会触发 FRED 限流/超时）。
    单请求内部已有线程级硬超时，故整体不会无限挂起。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    total = len(PRICE_NAMES) + len(FRED_IDS)

    # 1) 价格：并发（Yahoo/Stooq 是不同主机，8 路并发实测 Actions 全通）
    log("并发预取价格序列 …")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_price, n): n for n in PRICE_NAMES}
        for fut in as_completed(futs):
            n = futs[fut]
            try:
                RAW[("price", n)] = fut.result() or []
            except Exception as e:
                RAW[("price", n)] = []
                log(f"  价格失败 {n}: {e}")

    # 2) FRED：串行（关键修复——并发会把 FRED 打到超时）
    log("串行预取 FRED 序列 …")
    for sid in FRED_IDS:
        try:
            RAW[("fred", sid)] = fetch_fred(sid) or []
        except Exception as e:
            RAW[("fred", sid)] = []
            log(f"  FRED 失败 {sid}: {e}")

    okc = sum(1 for v in RAW.values() if v)
    log(f"预取完成：{okc}/{total} 有数据")


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def build_clock():
    """美林投资时钟：由「增长方向 × 通胀方向」定四象限（方向=动量，非水平）。"""
    g_sig, g_votes = [], []
    gdp = fetch_fred("A191RL1Q225SBEA")
    if len(gdp) >= 4:
        a = _mean([v for _, v in gdp[-2:]]); b = _mean([v for _, v in gdp[-4:-2]])
        if a is not None and b is not None:
            dv = a - b
            g_sig.append(("GDP增速", "↑" if dv >= 0 else "↓", f"近2季 {a:.1f} vs 前2季 {b:.1f}"))
            g_votes.append(1 if dv >= 0 else -1)
    un = fetch_fred("UNRATE")
    if len(un) >= 4:
        dv = un[-1][1] - un[-4][1]
        g_sig.append(("失业率", "↑" if dv > 0 else "↓", f"3月 {dv:+.1f}pt"))
        g_votes.append(-1 if dv > 0 else 1)
    ic = fetch_fred("ICSA")
    if len(ic) >= 60:
        vals = [v for _, v in ic]
        ma = [sum(vals[i - 3:i + 1]) / 4 for i in range(3, len(vals))]
        if len(ma) >= 53 and ma[-53]:
            dv = (ma[-1] / ma[-53] - 1) * 100
            g_sig.append(("初请失业金", "↑" if dv > 0 else "↓", f"4周均同比 {dv:+.0f}%"))
            g_votes.append(-1 if dv > 0 else 1)
    se = fetch_fred("UMCSENT")
    if len(se) >= 4:
        dv = se[-1][1] - se[-4][1]
        g_sig.append(("消费者信心", "↑" if dv >= 0 else "↓", f"3月 {dv:+.1f}"))
        g_votes.append(1 if dv >= 0 else -1)
    growth = round(sum(g_votes) / len(g_votes), 2) if g_votes else 0.0

    i_sig, i_votes = [], []
    cpi_y = yoy(fetch_fred("CPIAUCSL"))
    if len(cpi_y) >= 4:
        dv = cpi_y[-1][1] - cpi_y[-4][1]
        i_sig.append(("CPI同比", "↑" if dv >= 0 else "↓", f"3月 {dv:+.2f}pt"))
        i_votes.append(1 if dv >= 0 else -1)
    pce_y = yoy(fetch_fred("PCEPILFE"))
    if len(pce_y) >= 4:
        dv = pce_y[-1][1] - pce_y[-4][1]
        i_sig.append(("核心PCE", "↑" if dv >= 0 else "↓", f"3月 {dv:+.2f}pt"))
        i_votes.append(1 if dv >= 0 else -1)
    be = fetch_fred("T5YIE")
    if len(be) >= 22:
        dv = be[-1][1] - be[-22][1]
        i_sig.append(("5年通胀预期", "↑" if dv >= 0 else "↓", f"1月 {dv:+.2f}pt"))
        i_votes.append(1 if dv >= 0 else -1)
    infl = round(sum(i_votes) / len(i_votes), 2) if i_votes else 0.0

    if growth >= 0 and infl < 0:
        phase, en, color, asset = "复苏", "Recovery", "#27ae60", "股票"
    elif growth >= 0 and infl >= 0:
        phase, en, color, asset = "过热", "Overheat", "#c0392b", "大宗商品"
    elif growth < 0 and infl >= 0:
        phase, en, color, asset = "滞胀", "Stagflation", "#e67e22", "现金 / 短债"
    else:
        phase, en, color, asset = "衰退", "Recession", "#2980b9", "债券"

    note = f"增长{'↑' if growth >= 0 else '↓'}、通胀{'↑' if infl >= 0 else '↓'} → {phase}期，{asset}占优"
    conf = round((abs(growth) + abs(infl)) / 2, 2)
    sig = [{"name": n, "arrow": a, "detail": d} for n, a, d in (g_sig + i_sig)]
    return {"phase": phase, "en": en, "color": color, "asset": asset,
            "growth": growth, "inflation": infl, "confidence": conf,
            "note": note, "signals": sig,
            "updated": cpi_y[-1][0] if cpi_y else None}


def _al(level, text):
    return {"on": level in ("high", "mid"), "level": level, "text": text}


def _num(p, key="current"):
    v = p.get(key)
    return v if isinstance(v, (int, float)) else None


# 超标判定：返回 _al(...) 或 None。阈值参考各面板 refs。
ALERT_RULES = {
    "M1": lambda p: _al("high", f"纳指长期估值偏贵 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 20
        else (_al("mid", f"纳指估值偏高 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 10 else None),
    "M1b": lambda p: _al("high", f"巴菲特指标 {_num(p):.0f}%（高于200%）") if _num(p) is not None and _num(p) > 200 else None,
    "M2": lambda p: _al("high", f"S&P 偏离5年线 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 15
        else (_al("mid", f"S&P 高于5年线 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 10 else None),
    "M3": lambda p: _al("mid", f"实际利率偏紧 {_num(p):.2f}%") if _num(p) is not None and _num(p) > 2 else None,
    "M4": lambda p: _al("high", f"VIX 恐慌 {_num(p):.1f}") if _num(p) is not None and _num(p) > 30
        else (_al("mid", f"VIX 自满 {_num(p):.1f}") if _num(p) is not None and _num(p) < 15 else None),
    "M5": lambda p: _al("high", f"信用利差紧张 {_num(p):.2f}%") if _num(p) is not None and _num(p) > 3 else None,
    "M6": lambda p: _al("high", f"收益率曲线倒挂 {_num(p):.2f}%") if _num(p) is not None and _num(p) < 0 else None,
    "M8": lambda p: _al("mid", f"强美元 {_num(p):.1f}") if _num(p) is not None and _num(p) > 128 else None,
    "M10": lambda p: _al("high", "失业率触发 Sahm 衰退信号") if (p.get("sahm") or 0) > 0.5
        else (_al("mid", f"失业率偏高 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 5 else None),
    "M11": lambda p: _al("high", f"CPI 过热 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 5
        else (_al("mid", f"CPI 偏高 {_num(p):.1f}%") if _num(p) is not None and _num(p) > 3 else None),
    "M13": lambda p: _al("mid", "股债同跌，避险失效") if _num(p) is not None and _num(p) > 0.3 else None,
    "M14": lambda p: _al("high", "VIX 期限倒挂（短端恐慌）") if _num(p) is not None and _num(p) > 1.0 else None,
    "M15": lambda p: _al("high", "10Y-3M 倒挂（衰退预警）") if _num(p) is not None and _num(p) < 0 else None,
    "M16": lambda p: _al("mid", f"初请失业金同比 {p.get('ic_yoy'):+.0f}%，劳动力走弱")
        if p.get("ic_yoy") is not None and p.get("ic_yoy") > 15 else None,
    "M17": lambda p: _al("high", f"核心PCE {_num(p):.1f}%（高于3%）") if _num(p) is not None and _num(p) > 3 else None,
    "M18": lambda p: _al("mid", f"通胀预期升温 {_num(p):.2f}%") if _num(p) is not None and _num(p) > 2.5 else None,
    "M19": lambda p: _al("high", f"GDP 收缩 {_num(p):.1f}%") if _num(p) is not None and _num(p) < 0
        else (_al("mid", f"GDP 增速低 {_num(p):.1f}%") if _num(p) is not None and _num(p) < 1 else None),
    "M20": lambda p: _al("mid", f"消费者信心低迷 {_num(p):.0f}") if _num(p) is not None and _num(p) < 70 else None,
    "M21": lambda p: _al("mid", f"政策利率偏高 {_num(p):.2f}%") if _num(p) is not None and _num(p) > 5 else None,
}


def _alert_for(p):
    pid = p["id"]
    if pid == "M12":
        v = p.get("verdict") or ""
        if "活跃" in v:
            return _al("high", "衰退信号共振")
        if "预警" in v:
            return _al("mid", "部分衰退预警")
        return {"on": False, "level": "", "text": ""}
    rule = ALERT_RULES.get(pid)
    if rule:
        try:
            r = rule(p)
            if r:
                return r
        except Exception:
            pass
    return {"on": False, "level": "", "text": ""}


def _compute_summary(groups):
    """顶部总览：综合温度 0-100（估值/情绪/信用/通胀分位合成）+ 超标清单。"""
    panels = {p["id"]: p for g in groups for p in g["panels"]}

    sev = {"high": 0, "mid": 1}
    alerts = [{"id": p["id"], "title": p["title"], "level": p["alert"]["level"],
               "text": p["alert"]["text"]}
              for p in panels.values() if (p.get("alert") or {}).get("on")]
    alerts.sort(key=lambda x: sev.get(x["level"], 2))

    def pct(i):
        p = panels.get(i)
        return p.get("pct") if p else None

    comps = []
    def add(name, vals, w):
        vs = [v for v in vals if isinstance(v, (int, float))]
        if vs:
            comps.append({"name": name, "score": round(sum(vs) / len(vs)), "w": w})
    add("估值", [pct("M1"), pct("M2"), pct("M1b")], 0.35)
    add("情绪", [pct("M4")], 0.25)
    add("信用", [pct("M5")], 0.20)
    add("通胀", [pct("M11")], 0.20)

    tw = sum(c["w"] for c in comps) or 1
    score = round(sum(c["score"] * c["w"] for c in comps) / tw) if comps else None
    if score is None:
        label, color = "—", "#888"
    elif score < 20:
        label, color = "冰冷", "#2980b9"
    elif score < 40:
        label, color = "偏冷", "#27ae60"
    elif score < 60:
        label, color = "中性", "#7f8c8d"
    elif score < 80:
        label, color = "偏热", "#e67e22"
    else:
        label, color = "过热", "#c0392b"

    headline = (f"{len(alerts)} 项指标超标" if alerts else "暂无指标超标")
    return {"score": score, "label": label, "color": color, "components": comps,
            "alerts": alerts, "headline": headline}


def main():
    log("开始抓取并计算面板 …")
    prefetch_all()
    groups = []; asof = {}; ok = 0

    plan = [
        ("估值", [build_buffett, build_sp_anchor, build_real_rate, build_buffett_m1b]),
        ("情绪 / 风险", [build_vix, build_credit, build_curve, build_correlation,
                        build_vix_term, build_curve3m]),
        ("全球 / 世界经济", [build_global_map, build_dollar, build_commodities]),
        ("宏观景气", [build_unemployment, build_recession, build_claims,
                     build_gdp, build_sentiment]),
        ("通胀 / 利率", [build_inflation, build_core_pce, build_breakeven, build_fedfunds]),
    ]
    for gname, builders in plan:
        panels = []
        for b in builders:
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

    # 超标提醒 + 顶部总览
    for g in groups:
        for p in g["panels"]:
            p["alert"] = _alert_for(p)
    summary = _compute_summary(groups)
    clock = build_clock()

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
        "summary": summary, "clock": clock,
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
