"""オーケストレータ: 財務＋先行指標＋先見(実データ導出)＋自己改善を回し live/*.json を生成する.

  live/financials.json  … 実財務＋CAPITALスコア
  live/indicators.json  … 先行指標トラッカー
  live/foresight.json   … 実データ導出の先見6原理＋学習済み重み＋集中警告（自己改善の中核）
  live/analyst.json     … アナリスト読み筋
  live/learning_ledger.json … 遅延採点の台帳（内部用）
  live/history.json     … トレンド矢印用スナップショット
  live/meta.json        … 実行サマリ
"""
import os
import json
import datetime as dt

import yfinance as yf

from config import (LIVE_DIR, BENCHMARK_SYMBOL,
                    CONCENTRATION_TOP_N, CONCENTRATION_THRESHOLD)
import time

import fetch_financials
import fetch_indicators
import factors as fac
import learning
import universe
import discovery
import watch
import fetch_news
import fetch_edgar
import news_judge
import analyst


def _write(name, obj):
    with open(os.path.join(LIVE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load(name, default):
    path = os.path.join(LIVE_DIR, name)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _composite(pillars, weights):
    tot = sum(weights.values()) or 1
    return round(sum(pillars[p] * weights[p] for p in pillars) / tot, 1)


def _spy():
    try:
        h = yf.Ticker(BENCHMARK_SYMBOL).history(period="1y")
        price = float(h["Close"].dropna().iloc[-1]) if len(h) else None
        return price, h
    except Exception:
        return None, None


def _notify(title, msg):
    """通知: macOS通知センター（ローカル実行時）＋ntfy.shスマホプッシュ（NTFY_TOPIC設定時）."""
    try:
        import subprocess
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg}" with title "{title}"'],
                       timeout=10, capture_output=True)
    except Exception:
        pass
    topic = os.environ.get("NTFY_TOPIC", "")
    if topic:
        try:
            import requests
            requests.post("https://ntfy.sh/",
                          json={"topic": topic, "title": title, "message": msg,
                                "tags": ["zap"], "priority": 4},
                          timeout=10)
        except Exception:
            pass


def _earnings_days(tickers):
    """次回決算までの日数（触媒ウィンドウの表示用・スコアには不使用）."""
    out = {}
    for t in tickers:
        try:
            cal = yf.Ticker(t).calendar
            eds = (cal or {}).get("Earnings Date") or []
            if eds:
                days = (min(eds) - dt.date.today()).days
                if 0 <= days <= 45:
                    out[t] = days
        except Exception:
            pass
        time.sleep(0.2)
    return out


def _confirm_mom(tickers):
    """兆候の価格/出来高確認: 5日リターンと出来高サージ（ウォッチ対象のみ・軽量）."""
    out = {}
    for t in tickers:
        e = {}
        try:
            h = yf.Ticker(t).history(period="3mo")
            c = h["Close"].dropna()
            v = h["Volume"].dropna()
            if len(c) > 6:
                e["ret5"] = round(float(c.iloc[-1] / c.iloc[-6] - 1), 4)
            if len(v) > 30:
                base = float(v.iloc[-30:-5].mean()) or 1.0
                e["vol_surge"] = round(float(v.iloc[-5:].mean()) / base, 2)
        except Exception:
            pass
        out[t] = e
        time.sleep(0.3)
    return out


def _prices_for(symbols):
    """ユニバースを離脱した過去コホート銘柄の現在価格をバッチ取得（採点の生命線）."""
    out = {}
    symbols = [s for s in symbols if s]
    if not symbols:
        return out
    try:
        data = yf.download(symbols, period="5d", auto_adjust=True,
                           progress=False, threads=False)
        closes = data["Close"]
        if not hasattr(closes, "columns"):
            closes = closes.to_frame(name=symbols[0])
        for s in symbols:
            if s in closes.columns:
                ser = closes[s].dropna()
                if len(ser):
                    out[s] = float(ser.iloc[-1])
    except Exception as e:
        print(f"  [grade] 離脱銘柄の価格取得失敗: {repr(e)[:80]}")
    return out


# EWMA平滑（客観：前回の正規化値から緩やかに更新。事前分布は使わない）
EWMA = 0.5


def _ewma_blend(tid, factors_norm, prev):
    out = {}
    for f, v in factors_norm.items():
        p = (prev.get(tid) or {}).get("factors", {}).get(f) if prev else None
        out[f] = round(v if p is None else p * (1 - EWMA) + v * EWMA, 1)
    return out


def main():
    os.makedirs(LIVE_DIR, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    print(f"=== NextGenSeeker refresh @ {ts} ===")

    # ── 客観ユニバース構築（固定リスト＝主観を全廃） ──
    print("[1/5] 客観ユニバース構築 (Yahooスクリーナー和集合)...")
    try:
        uni_syms = universe.build()
    except Exception as e:
        print(f"  [uni] 構築失敗: {repr(e)[:80]}")
        uni_syms = []
    if not uni_syms:
        # スクリーナー全滅時は前回のユニバースを再利用（パイプラインを止めない）
        prev = _load("foresight.json", {"data": {}}).get("data", {})
        uni_syms = list(prev.keys())
        print(f"  [uni] フォールバック: 前回ユニバース {len(uni_syms)}銘柄を再利用")
    symmap = {s: s for s in uni_syms}      # 内部ID＝シンボル（人手の別名なし）
    discovered = list(uni_syms)

    print("[2/5] 財務データ取得 (yfinance)...")
    financials = {}
    for s in uni_syms:
        try:
            d = fetch_financials.fetch_one(s)
            d["ok"] = d.get("capital_score") is not None
            financials[s] = d
        except Exception as e:
            financials[s] = {"symbol": s, "ok": False, "error": repr(e)[:120]}

    print("[3/5] 先行指標取得 (GitHub / market)...")
    try:
        indicators = fetch_indicators.fetch_all()
    except Exception as e:
        # 参考パネル用データの失敗で本体を殺さない。前回値を再利用。
        print(f"  [ind] 取得失敗（前回値を再利用）: {repr(e)[:80]}")
        indicators = _load("indicators.json", {}).get("data") or {
            "moat_erosion": {"repos": [], "scale": None, "total_stars": 0,
                             "total_commits_30d": 0, "heat": 0},
            "market": {k: {"items": [], "heat": None}
                       for k in ("tsmc_demand", "optical", "power", "hbm")},
        }

    # ── 客観ファクターを財務諸表・株価から機械的に計算（主観・キーワードなし） ──
    print("[4/5] 客観ファクター計算＋自己改善...")
    bench_now, spy_hist = _spy()
    prev_fore = _load("foresight.json", {"data": {}}).get("data", {})
    led = learning.load_ledger()
    lr = learning.compute_learning(led)
    weights = lr["weights"]

    raw = fac.compute_raw(symmap, spy_hist)
    norm = fac.percentile_normalize(raw)

    fore_data = {}
    for tid, fin in financials.items():
        if not fin.get("ok") or tid not in norm:
            continue
        factors_final = _ewma_blend(tid, norm[tid], prev_fore)
        fore_data[tid] = {
            "factors": factors_final,
            "raw": {f: (round(raw[tid][f], 3) if isinstance(raw[tid].get(f), float) else raw[tid].get(f))
                    for f in fac.FACTORS},
            "diag": raw[tid].get("_diag"),
            "composite": _composite(factors_final, weights),
            "sector": fin.get("sector"),
            "price": fin.get("price"),
            "discovered": bool(fin.get("discovered")),
        }

    # ── 遅延採点: 今日のコホートを記録 → 満期分を市場超過で採点 ──
    picks = {t: {"composite": d["composite"], "pillars": d["factors"], "price": d["price"]}
             for t, d in fore_data.items() if d.get("price")}
    recorded = learning.record_cohort(led, ts, picks, bench_now)
    price_now = {t: d.get("price") for t, d in fore_data.items() if d.get("price")}
    # ユニバース入替で離脱した過去コホート銘柄も、価格を補完して必ず採点する
    # （これが無いと採点が静かに失敗し、自己改善は永遠に作動しない）
    dropped = learning.pending_tickers(led) - set(price_now)
    if dropped:
        fetched = _prices_for(sorted(dropped))
        price_now.update(fetched)
        print(f"  [grade] ユニバース離脱 {len(dropped)}銘柄中 {len(fetched)}銘柄の現値を補完")
    graded = learning.grade(led, price_now, bench_now)
    learning.save_ledger(led)
    lr = learning.compute_learning(led)
    weights = lr["weights"]
    for t, d in fore_data.items():
        d["composite"] = _composite(d["factors"], weights)

    # ── 集中(ガラパゴス)ガード: 上位の先見スコアがセクター偏重でないか ──
    ranked = sorted(fore_data.items(), key=lambda kv: kv[1]["composite"], reverse=True)
    conc = discovery.concentration_guard(
        [(t, d["sector"]) for t, d in ranked], CONCENTRATION_TOP_N, CONCENTRATION_THRESHOLD)

    # ── ウォッチ＆兆候レーダー（継続選出→触媒ニュース→価格確認） ──
    print("[5/6] ウォッチ＆兆候レーダー...")
    today = ts[:10]
    wst = watch.load_state()
    ranked_ids = [t for t, _ in ranked]
    watch.update_appearances(wst, today, ranked_ids)
    today_ranks = {t: i + 1 for i, t in enumerate(ranked_ids)}
    wl = watch.select_watchlist(wst, today, today_ranks)
    print(f"  [watch] 対象 {len(wl)}銘柄 "
          f"(確定{sum(1 for w in wl if w['tier']=='確定')}/仮{sum(1 for w in wl if w['tier']=='仮')})")

    watch_ids = [w["ticker"] for w in wl]
    name_map = {t: (financials.get(t) or {}).get("name") or t for t in today_ranks}
    news_by_t = fetch_news.fetch_for(watch_ids)
    judged, judge_source = news_judge.judge_all(news_by_t, name_map)

    # SEC EDGAR 8-K（一次情報）を同じ集約器に合流。Item番号の機械判定・2倍重み。
    edgar_by_t = fetch_edgar.fetch_8k(watch_ids)
    for t in watch_ids:
        ev = fetch_edgar.to_judged_items(edgar_by_t.get(t, []))
        if not ev:
            continue
        entry = judged.setdefault(t, {"score": 50.0, "items": [], "n": 0})
        entry["items"] = ev + entry["items"]          # 一次情報を先頭に
        entry["score"] = news_judge.aggregate_score(entry["items"])
        entry["n"] = len(entry["items"])

    mom = _confirm_mom(watch_ids)
    earn = _earnings_days(watch_ids)
    comp_learn = watch.learn_composition(wst)   # 構成比のIC学習（サンプル不足なら基準30/40/30）
    comp = comp_learn["composition"]
    signals = []
    for w in wl:
        t = w["ticker"]
        persist = watch.persistence_score(w)
        news_score = judged.get(t, {}).get("score", 50.0)
        confirm = watch.confirmation_score(mom.get(t))
        sig = watch.composite_signal(persist, news_score, confirm, comp)
        signals.append({
            **w, "name": name_map.get(t, t),
            "sector": (fore_data.get(t) or {}).get("sector"),
            "persist": round(persist, 1), "news": news_score,
            "confirm": round(confirm, 1), "signal": sig,
            "mom": mom.get(t), "earn_days": earn.get(t),
            "headlines": (judged.get(t, {}).get("items") or [])[:5],
        })
    signals.sort(key=lambda s: -s["signal"])

    n_alerts = watch.record_alerts(wst, today, signals, price_now, bench_now)
    watch.record_watch_cohort(wst, today, signals, price_now, bench_now)
    # 採点: アラート＋ウォッチコホートの離脱銘柄の価格も補完してから採点
    a_missing = (watch.pending_alert_tickers(wst)
                 | watch.pending_watch_tickers(wst)) - set(price_now)
    if a_missing:
        price_now.update(_prices_for(sorted(a_missing)))
    alert_summary = watch.grade_alerts(wst, price_now, bench_now)
    n_wgraded = watch.grade_watch_cohorts(wst, price_now, bench_now)
    comp_learn = watch.learn_composition(wst)   # 採点後に再学習
    watch.save_state(wst)
    if n_wgraded:
        print(f"  [watch] コホート採点 {n_wgraded}件 / 構成比学習 "
              f"{'作動' if comp_learn['active'] else '不動'}({comp_learn['graded_samples']}samples)")
    print(f"  [watch] 新規アラート{n_alerts}件 / 採点済みサマリ {alert_summary or '（満期待ち）'}")
    if n_alerts:
        hot = [s for s in signals if s["signal"] >= watch.ALERT_THRESHOLD][:3]
        _notify("NGS ⚡ 上昇兆候アラート",
                " / ".join(f"{s['ticker']} {s['signal']}" for s in hot)
                + " — 継続選出×触媒×価格確認が揃いました")

    _write("watch.json", {
        "updated": ts, "judge_source": judge_source, "signals": signals,
        "alert_summary": alert_summary,
        "alerts_recent": sorted(wst["alerts"], key=lambda a: a["date"], reverse=True)[:20],
        "composition": comp_learn,
        "criteria": {"streak_days": watch.WATCH_STREAK_DAYS, "threshold": watch.ALERT_THRESHOLD},
    })

    print("[6/6] アナリスト合成...")
    commentary = analyst.synthesize(financials, indicators)
    print(f"  analyst source = {commentary['source']} / graded={graded} / active={lr['active']}")

    _write("financials.json", {"updated": ts, "data": financials})
    _write("indicators.json", {"updated": ts, "data": indicators})
    _write("foresight.json", {"updated": ts, "weights": weights, "data": fore_data,
                              "concentration": conc, "discovered": discovered})
    _write("learning.json", {"updated": ts, **lr, "concentration": conc,
                             "recorded_today": recorded, "graded_events": graded})
    _write("analyst.json", {"updated": ts, **commentary})

    # ── 履歴（トレンド矢印用） ──
    history = _load("history.json", {"points": []})
    history["points"].append({
        "t": ts,
        "capital": {t: d.get("capital_score") for t, d in financials.items() if d.get("capital_score")},
        "foresight": {t: d["composite"] for t, d in fore_data.items()},
        "moat_heat": indicators["moat_erosion"]["heat"],
        "moat_commits30d": indicators["moat_erosion"]["total_commits_30d"],
        "moat_stars": indicators["moat_erosion"]["total_stars"],
        "tsmc_heat": indicators["market"]["tsmc_demand"]["heat"],
        "optical_heat": indicators["market"]["optical"]["heat"],
        "power_heat": indicators["market"]["power"]["heat"],
        "hbm_heat": indicators["market"]["hbm"]["heat"],
    })
    history["points"] = history["points"][-180:]
    _write("history.json", history)

    ok = sum(1 for d in financials.values() if d.get("ok"))
    _write("meta.json", {
        "updated": ts, "financials_ok": ok, "financials_total": len(financials),
        "discovered": discovered, "analyst_source": commentary["source"],
        "history_points": len(history["points"]),
        "learning_active": lr["active"], "graded_samples": lr["graded_samples"],
        "cohorts_tracked": lr["cohorts_tracked"],
    })
    print(f"=== done: {ok}/{len(financials)} fin, {len(discovered)} discovered, "
          f"learning_active={lr['active']} ({lr['graded_samples']} graded) ===")


if __name__ == "__main__":
    main()
