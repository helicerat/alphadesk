"""Everything an evidence pack shows, computed by the same code as the verdict.

The holdout window is never touched here. Charts stop at the holdout start.
"""

from __future__ import annotations

import math

import numpy as np

from . import dsl, portfolio, stats


def _stats_line(r, ppy):
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return {"sharpe": float("nan"), "ann_ret": float("nan"), "t": float("nan"), "n": int(len(r))}
    sr = stats.sharpe(r)
    return {"sharpe": sr * math.sqrt(ppy), "ann_ret": float(np.mean(r) * ppy), "t": sr * math.sqrt(len(r)), "n": int(len(r))}


def build(desk, card: dict, verdict: dict) -> dict:
    p, w, cfg = desk.panel, desk.w, desk.config
    ppy = cfg.periods_per_year
    sig = dsl.compile_signal(card["formula"], p)
    S = sig.evaluate(p)
    hold = int(card.get("hold", 1))
    ret = p.returns()
    upto = w.holdout_start

    def sl(x, a, b):
        y = np.full_like(x, np.nan)
        y[a:b] = x[a:b]
        return y

    ls = portfolio.long_short(sl(S, w.start, upto), ret, hold=hold, cost_bps=cfg.cost_bps, start=w.start)
    net, gross = ls["net"], ls["gross"]
    eq = np.nancumsum(np.nan_to_num(net[w.start:upto]))
    pk = np.maximum.accumulate(eq)
    dd = eq - pk
    dates = [str(d.date()) for d in p.dates[w.start:upto]]

    # nearest known factor, for the comparison line
    lib = desk.library_returns()
    nearest, near_curve = None, None
    nov = verdict.get("novelty", {})
    if nov.get("signal_corr"):
        nearest = max(nov["signal_corr"], key=lambda k: abs(nov["signal_corr"][k]))
        near_curve = np.nancumsum(np.nan_to_num(lib[nearest]["returns"][w.start:upto])).tolist()

    # deciles, IC by horizon, rolling IC
    deciles = portfolio.decile_returns(S, ret, start=w.start, end=w.valid_start, periods_per_year=ppy)
    by_h = verdict.get("ic_by_horizon", {})
    ic_full = desk._ic(S, hold, w.start, upto)
    roll = np.full_like(ic_full, np.nan)
    win = 252
    for t in range(w.start + win, upto):
        x = ic_full[t - win:t]
        x = x[np.isfinite(x)]
        if len(x) > 50:
            roll[t] = x.mean()

    # cost curve on the development window
    g = ls["gross"][w.start:w.valid_start]
    traded = np.nan_to_num(ls["turnover"][w.start:w.valid_start]) * 2
    costs = list(range(0, 61, 5))
    curve = []
    for c in costs:
        r = g - traded * c / 1e4
        curve.append(stats.sharpe(r) * math.sqrt(ppy))

    # explained by known factors
    table = []
    if lib:
        names = list(lib)
        y = sl(gross, w.start, w.valid_start)
        X = np.column_stack([lib[n]["returns"] for n in names])
        reg = stats.ols_alpha(y, X)
        for n, b, t in zip(names, reg["beta"], reg["t_beta"]):
            table.append({"factor": n, "beta": b, "t": t})
        table.append({"factor": "alpha / day", "beta": reg["alpha"], "t": reg["t_alpha"]})
    published = nov.get("published")

    # windows: before vs after the model cutoff
    pre = _stats_line(sl(net, w.start, w.cutoff), ppy)
    post = _stats_line(sl(net, w.cutoff, upto), ppy)
    ic_pre = float(np.nanmean(desk._ic(S, hold, w.start, w.cutoff)))
    ic_post = float(np.nanmean(desk._ic(S, hold, w.cutoff, upto)))
    hit_pre = float(np.nanmean(net[w.start:w.cutoff][np.isfinite(net[w.start:w.cutoff])] > 0))
    post_r = net[w.cutoff:upto]
    post_r = post_r[np.isfinite(post_r)]
    hit_post = float(np.mean(post_r > 0)) if len(post_r) else float("nan")

    # tradability
    k = max(1, int(np.median(np.isfinite(S[w.start:w.valid_start]).sum(axis=1))) // 10)
    tradable = {"names_per_leg": k,
                "turnover_per_rebalance": float(np.nanmean(ls["turnover"])),
                "long_leg_t": _stats_line(sl(ls["long"], w.start, w.valid_start), ppy)["t"],
                "short_leg_t": _stats_line(sl(ls["short"], w.start, w.valid_start), ppy)["t"],
                "max_drawdown": float(dd.min()) if len(dd) else float("nan")}
    adv = None
    if "close" in p.raw and ("volume" in p.raw or "quote_volume" in p.raw):
        dv = p.raw["close"] * p.raw["volume"] if "volume" in p.raw else p.raw["quote_volume"]
        adv = float(np.nanmedian(dv[w.start:w.valid_start]))
        tradable["median_adv"] = adv
        tradable["capacity_1pct_adv"] = adv * 0.01 * k * 2

    # deflate again at the campaign's final number of tries: a candidate found
    # early was judged against fewer tries than the campaign ended up making
    M = desk.log.returns_matrix(verdict.get("campaign"))
    n_eff_final = stats.effective_n(M) if M is not None else 1.0
    n_raw_final = M.shape[1] if M is not None else 1
    d_final = stats.deflated_sr(sl(net, w.start, w.valid_start), max(n_eff_final, 1.0))
    sr_ann = d_final["sr"] * math.sqrt(ppy)
    final = {"dsr": d_final["dsr"], "n_eff": n_eff_final, "n_raw": n_raw_final,
             "minbtl_years": stats.min_backtest_length_years(max(n_eff_final, 1.0), sr_ann) if sr_ann > 0 else float("inf"),
             "still_passes": bool(d_final["dsr"] >= cfg.dsr_min)}

    return {
        "final_deflation": final,
        "card": card, "formula": card["formula"], "canon": sig.canon, "hold": hold,
        "dates": dates, "cutoff_index": max(0, w.cutoff - w.start), "valid_index": max(0, w.valid_start - w.start),
        "equity": eq.tolist(), "drawdown": dd.tolist(), "nearest": nearest, "nearest_equity": near_curve,
        "deciles": deciles, "ic_by_horizon": by_h, "rolling_ic": roll[w.start:upto].tolist(),
        "cost_curve": {"bps": costs, "sharpe": curve, "breakeven": verdict.get("costs", {}).get("breakeven_bps"),
                       "yours": cfg.cost_bps},
        "factors": table, "published": published,
        "subperiods": verdict.get("subperiods", []),
        "windows": {"pre": {**pre, "ic": ic_pre, "hit": hit_pre, "from": str(p.dates[w.start].date()),
                            "to": str(p.dates[w.cutoff].date())},
                    "post": {**post, "ic": ic_post, "hit": hit_post, "rows": int(len(post_r)),
                             "rows_needed": verdict.get("post_cutoff", {}).get("rows_needed")}},
        "tradable": tradable, "verdict": verdict,
        "meta": {"source": p.meta.get("source"), "assets": p.N, "data": p.data_hash(),
                 "survivorship_warning": bool(p.meta.get("survivorship_warning"))},
    }
