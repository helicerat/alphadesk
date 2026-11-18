"""HTML evidence packs and the campaign page. Static files, no scripts, no
network: every chart is inline SVG drawn from the evaluator's numbers."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
from pathlib import Path

from . import __version__
from .evaluator import CHECK_NAMES

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">'

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#000;--panel:#070707;--line:#1d2026;--grid:#141619;--fg:#eef1f4;--soft:#dfe4ea;--mute:#a3abb5;--dim:#6b737d;
--blue:#79c0ff;--green:#3fe06e;--red:#ff7b72;--amber:#e3b341;--violet:#d2a8ff}
body{background:var(--bg);color:var(--fg);font:14px/1.45 Inter,"Segoe UI",system-ui,sans-serif;padding:24px}
.mono,table,.chk,.kpi .v{font-family:"JetBrains Mono",ui-monospace,Consolas,monospace}
a{color:var(--blue);text-decoration:none}
.wrap{max-width:1180px;margin:0 auto}
.id{font:600 11px "JetBrains Mono",monospace;color:var(--mute);letter-spacing:.08em;text-transform:uppercase}
h1{font-size:26px;font-weight:800;letter-spacing:-.02em;margin:2px 0 6px}
h1 small{font:500 12.5px "JetBrains Mono",monospace;color:var(--mute);margin-left:10px;letter-spacing:0}
h2{font-size:13px;color:var(--mute);text-transform:uppercase;letter-spacing:.1em;margin:26px 0 10px}
.hdr{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:12px}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{font-size:11.5px;border:1px solid var(--line);border-radius:999px;padding:1px 9px;color:var(--soft)}
.badge{display:inline-block;font-weight:800;font-size:14px;padding:6px 13px;border-radius:6px;letter-spacing:.06em}
.badge.ok{background:#0f2a18;border:1px solid #2ea043;color:var(--green)}.badge.no{background:#2a0f0f;border:1px solid #da3633;color:var(--red)}
.badge+div{font:500 11px "JetBrains Mono",monospace;color:var(--mute);margin-top:5px;text-align:right}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:6px;margin:10px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:6px 10px}
.kpi .k{font-size:10.5px;color:var(--mute)}.kpi .v{font-size:17px;font-weight:700}.kpi .v small{display:block;font-size:10px;color:var(--mute);font-weight:500}
.grid{display:grid;gap:8px;margin-bottom:8px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.ph{font-size:10.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px}
.ph span{text-transform:none;letter-spacing:0;font-weight:500}
svg{display:block;width:100%;height:auto}
table{width:100%;border-collapse:collapse;font-size:11.5px}
td,th{padding:3px 4px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th{color:var(--mute);font-weight:500;font-size:10.5px}td:first-child,th:first-child{text-align:left;color:var(--soft)}
.chk{font-size:11px;line-height:1.75}.chk div{display:flex;justify-content:space-between;gap:10px}.chk .n{color:var(--dim);display:inline-block;width:20px}
.chk div>span:first-child{white-space:nowrap;flex:none}.chk div>span:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;min-width:0}
.g{color:var(--green)}.r{color:var(--red)}.a{color:var(--amber)}.m{color:var(--mute)}.b{color:var(--blue)}
.note{font-size:11px;color:var(--amber);margin-top:6px}
.foot{margin-top:22px;font:500 11px "JetBrains Mono",monospace;color:var(--dim)}
.warn{border:1px solid #9e6a03;background:#231a05;color:var(--amber);border-radius:6px;padding:8px 12px;font-size:12px;margin:8px 0}
.funnel .row{display:grid;grid-template-columns:220px 1fr 50px;gap:10px;align-items:center;margin:3px 0;font-size:12px}
.funnel .bar{height:12px;background:#111;border-radius:2px;position:relative}.funnel .bar i{position:absolute;inset:0 auto 0 0;background:var(--blue);border-radius:2px}
@media(max-width:820px){.grid{grid-template-columns:1fr!important}body{padding:14px}}
"""

F = "JetBrains Mono, Consolas, monospace"


def _fmt(x, d=2, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    return f"{x * 100:.{d}f}%" if pct else f"{x:.{d}f}"


def _txt(x, y, t, c="#6b737d", a="middle", s=10):
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{c}" font-size="{s}" text-anchor="{a}" font-family="{F}">{html.escape(str(t))}</text>'


def _scale(vals, lo_pad=0.05):
    v = [x for x in vals if x is not None and math.isfinite(x)]
    if not v:
        return 0.0, 1.0
    lo, hi = min(v), max(v)
    if hi == lo:
        hi = lo + 1e-9
    pad = (hi - lo) * lo_pad
    return lo - pad, hi + pad


def line_chart(series, W=720, H=300, dates=None, mark=None, dd=None, pct=True):
    """series: list of (values, color, width)."""
    L, T, R, B = 46, 8, 8, 64 if dd is not None else 24
    allv = [x for s in series for x in s[0]]
    lo, hi = _scale(allv)
    n = max(len(s[0]) for s in series)
    X = lambda i: L + (W - L - R) * i / max(n - 1, 1)
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    o = [f'<svg viewBox="0 0 {W} {H}">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#141619"/>')
        o.append(_txt(L - 6, Y(v) + 3, f"{v * 100:.0f}%" if pct else f"{v:.3f}", a="end"))
    if mark:
        for idx, color, label in mark:
            if 0 < idx < n:
                o.append(f'<rect x="{X(idx):.1f}" y="{T}" width="{X(n - 1) - X(idx):.1f}" height="{H - T - B}" fill="{color}" opacity=".12"/>' if label.startswith("model") else "")
                o.append(f'<line x1="{X(idx):.1f}" x2="{X(idx):.1f}" y1="{T}" y2="{H - B + (40 if dd is not None else 0)}" stroke="{color}" stroke-dasharray="3 3"/>')
                o.append(_txt(X(idx) - 5, T + 12, label, color, "end", 10))
    for vals, color, wd in series:
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals) if v is not None and math.isfinite(v))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{wd}"/>')
    if dd is not None and len(dd):
        base = H - 42
        dmin = min(dd) or -1e-9
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{base}" y2="{base}" stroke="#25282d"/>')
        pts = " ".join(f"{X(i):.1f},{base + 30 * (v / dmin):.1f}" for i, v in enumerate(dd))
        o.append(f'<polygon points="{X(0):.1f},{base} {pts} {X(len(dd) - 1):.1f},{base}" fill="#f8514940" stroke="#ff7b72" stroke-width=".8"/>')
        o.append(_txt(L - 6, base + 8, "DD", "#ff7b72", "end") + _txt(L - 6, base + 30, f"{dmin * 100:.0f}%", a="end"))
    if dates:
        step = max(1, n // 6)
        for i in range(0, n - step // 2, step):
            o.append(_txt(X(i), H - 4, dates[i][:7]))
    o.append("</svg>")
    return "".join(o)


def bar_chart(labels, vals, W=380, H=240, hi_idx=None, fmt="{:.1f}", signed=True, colors=None):
    L, R, T, B = 10, 10, 18, 26
    v = [x if x is not None and math.isfinite(x) else 0 for x in vals]
    vmax = max(max(v), 0) or 1e-9
    vmin = min(min(v), 0)
    span = vmax - vmin or 1e-9
    base = T + (H - T - B) * vmax / span
    bw = (W - L - R) / len(v)
    o = [f'<svg viewBox="0 0 {W} {H}">', f'<line x1="{L}" x2="{W - R}" y1="{base:.1f}" y2="{base:.1f}" stroke="#25282d"/>']
    for i, x in enumerate(v):
        h = (H - T - B) * abs(x) / span
        y = base - h if x >= 0 else base
        if colors:
            c = colors[i]
        else:
            c = "#3fe06e" if (hi_idx == i) else ("#1f7a3e" if x >= 0 else "#8a2a26")
        o.append(f'<rect x="{L + i * bw + bw * .18:.1f}" y="{y:.1f}" width="{bw * .64:.1f}" height="{max(h, .5):.1f}" rx="2" fill="{c}"/>')
        o.append(_txt(L + i * bw + bw / 2, (y - 4) if x >= 0 else (y + h + 11), fmt.format(x), "#dfe4ea"))
        o.append(_txt(L + i * bw + bw / 2, H - 6, labels[i]))
    o.append("</svg>")
    return "".join(o)


def cost_chart(cc, W=300, H=180):
    L, R, T, B = 32, 8, 10, 22
    xs, ys = cc["bps"], cc["sharpe"]
    lo, hi = _scale(ys + [0])
    X = lambda b: L + (W - L - R) * b / max(xs)
    Y = lambda s: T + (H - T - B) * (1 - (s - lo) / (hi - lo))
    o = [f'<svg viewBox="0 0 {W} {H}">']
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#141619"/>' + _txt(L - 4, Y(v) + 3, f"{v:.1f}", a="end"))
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#3a414c"/>')
    o.append('<polyline points="' + " ".join(f"{X(b):.1f},{Y(s):.1f}" for b, s in zip(xs, ys)) + '" fill="none" stroke="#79c0ff" stroke-width="1.8"/>')
    yb = cc["yours"]
    ys_y = ys[0] + (ys[-1] - ys[0]) * yb / max(xs)
    o.append(f'<circle cx="{X(yb):.1f}" cy="{Y(ys_y):.1f}" r="3" fill="#3fe06e"/>' + _txt(X(yb) + 5, Y(ys_y) - 6, f"yours: {yb:g} bps → {ys_y:.2f}", "#3fe06e", "start"))
    be = cc.get("breakeven")
    if be and math.isfinite(be) and be <= max(xs):
        o.append(f'<circle cx="{X(be):.1f}" cy="{Y(0):.1f}" r="3" fill="#ff7b72"/>' + _txt(X(be) - 5, Y(0) + 13, f"0 at {be:.0f}", "#ff7b72", "end"))
    for b in (0, 20, 40, 60):
        o.append(_txt(X(b), H - 4, b))
    o.append("</svg>")
    return "".join(o)


def _checks_html(checks):
    out = []
    for c in checks:
        cls = {"pass": "g", "fail": "r", "weak": "a", "warn": "a", "na": "m", "sealed": "m"}.get(c["status"], "m")
        mark = {"pass": "✓", "fail": "✕", "weak": "~", "warn": "!", "na": "·", "sealed": "·"}.get(c["status"], "·")
        out.append(f'<div><span><span class="n">{c["n"]}</span>{html.escape(c["name"])}</span>'
                   f'<span class="{cls}">{mark} {html.escape(str(c["detail"]))[:70]}</span></div>')
    return "".join(out)


def evidence_html(ev: dict, campaign: str, n_trials: int) -> str:
    v = ev["verdict"]
    ok = v["survived"]
    dsr = v.get("dsr", {})
    ic = v.get("ic_dev", {})
    costs = v.get("costs", {})
    tr = ev["tradable"]
    nov = v.get("novelty", {})
    sc = nov.get("signal_corr") or {}
    top = max(sc, key=lambda k: abs(sc[k])) if sc else None
    kpis = [
        ("rank IC · t", _fmt(ic.get("mean"), 3), f"t {_fmt(ic.get('t'), 1)}"),
        ("IC IR · > 0", _fmt(ic.get("ir"), 2), _fmt(ic.get("pos"), 0, pct=True)),
        ("Sharpe, net", _fmt(costs.get("sharpe_net")), f"gross {_fmt(costs.get('sharpe_gross'))}"),
        ("deflated Sharpe", _fmt(ev["final_deflation"]["dsr"]), f"at final N_eff {_fmt(ev['final_deflation']['n_eff'], 0)}"),
        ("PBO", _fmt((v.get("pbo") or {}).get("pbo")), "CSCV 16" if v.get("pbo") else "family < 4"),
        ("breakeven", _fmt(costs.get("breakeven_bps"), 0), "bps / side"),
        ("turnover", _fmt(tr.get("turnover_per_rebalance"), 0, pct=True), f"per rebalance, hold {ev['hold']}"),
        ("max ρ known", _fmt(sc.get(top), 2) if top else "–", top or "no library"),
        ("max drawdown", _fmt(tr.get("max_drawdown"), 0, pct=True), "cumulative"),
        ("MinBTL", _fmt(ev["final_deflation"]["minbtl_years"], 1), "years of data needed"),
    ]
    k_html = "".join(f'<div class="kpi"><div class="k">{k}</div><div class="v">{a}<small>{b}</small></div></div>' for k, a, b in kpis)
    marks = [(ev["valid_index"], "#a3abb5", "validation →"), (ev["cutoff_index"], "#e3b341", "model cutoff →")]
    series = [(ev["equity"], "#79c0ff", 1.9)]
    if ev.get("nearest_equity"):
        series.insert(0, (ev["nearest_equity"], "#6b737d", 1.2))
    eq = line_chart(series, dates=ev["dates"], mark=marks, dd=ev["drawdown"])
    dec = bar_chart([f"D{i + 1}" for i in range(10)], [x * 100 for x in ev["deciles"]], hi_idx=9,
                    colors=["#ff7b72"] + [("#1f7a3e" if x >= 0 else "#8a2a26") for x in ev["deciles"][1:9]] + ["#3fe06e"])
    hz = ev["ic_by_horizon"]
    ich = bar_chart([f"{h}d" for h in hz], [hz[h] for h in hz], W=300, H=180, fmt="{:.3f}",
                    colors=["#79c0ff" if int(h) == ev["hold"] else "#28507f" for h in hz]) if hz else ""
    ric = line_chart([(ev["rolling_ic"], "#d2a8ff", 1.5)], W=300, H=180, pct=False,
                     mark=[(ev["cutoff_index"], "#e3b341", "cutoff")])
    cc = cost_chart(ev["cost_curve"])
    ft = "".join(f'<tr><td>{html.escape(r["factor"])}</td><td>{r["beta"]:.3g}</td>'
                 f'<td class="{"g" if r["factor"].startswith("alpha") and r["t"] >= 2 else ""}">{r["t"]:.1f}</td></tr>' for r in ev["factors"])
    pub = ev.get("published")
    pub_html = (f'<div class="note m">published factors ({pub["frequency"]}, {pub["periods"]} periods): '
                f'max ρ {pub["top_corr"]:.2f} with {html.escape(pub["top"])}, α t {pub["t_alpha"]:.1f}</div>'
                if pub and "top" in pub else "")
    sub = ev["subperiods"]
    bounds = ["Q1", "Q2", "Q3", "Q4"]
    st = "".join(f'<tr><td>dev {bounds[i]}</td><td>{s["mean"]:.3f}</td><td>{s["t"]:.1f}</td><td>{s["pos"]:.0%}</td></tr>' for i, s in enumerate(sub))
    wpre, wpost = ev["windows"]["pre"], ev["windows"]["post"]
    need = wpost.get("rows_needed")
    cut_note = (f'{wpost["rows"]} rows after the cutoff prove the sign, not the size. Needed: {need:.0f}.'
                if need and math.isfinite(need) and wpost["rows"] < need else "enough rows after the cutoff to judge the size")
    trad = "".join(f"<tr><td>{k}</td><td>{val}</td></tr>" for k, val in [
        ("names per leg", tr["names_per_leg"]),
        ("turnover / rebalance", _fmt(tr["turnover_per_rebalance"], 0, pct=True)),
        ("long leg alone, t", _fmt(tr["long_leg_t"], 1)), ("short leg alone, t", _fmt(tr["short_leg_t"], 1)),
        ("median daily $ volume", f"${tr['median_adv']:,.0f}" if tr.get("median_adv") else "–"),
        ("capacity at 1% ADV", f"${tr['capacity_1pct_adv']:,.0f}" if tr.get("capacity_1pct_adv") else "–")])
    fd = ev["final_deflation"]
    if not fd["still_passes"]:
        warn_final = (f'<div class="warn">Found early in the campaign. At the final count of {fd["n_raw"]} tries '
                      f'(N_eff {fd["n_eff"]:.1f}) its deflated Sharpe is {fd["dsr"]:.2f}: it no longer clears 0.95.</div>')
    else:
        warn_final = ""
    warn = warn_final + ('<div class="warn">This data has no historical list of delisted names. Results can be flattered by '
            'survivors. Treat them as an upper bound.</div>') if ev["meta"]["survivorship_warning"] else ""
    badge = (f'<div class="badge ok">✓ SURVIVOR · {sum(c["status"] in ("pass", "weak", "warn") for c in v["checks"])} checks</div><div>holdout sealed · opens once, by you</div>'
             if ok else f'<div class="badge no">✕ DIED AT {v["died_at"]} · {html.escape(CHECK_NAMES[v["died_at"]])}</div><div>{html.escape(v["summary"])[:90]}</div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(ev['card'].get('id', 'candidate'))} · evidence</title>{FONTS}<style>{CSS}</style></head><body><div class="wrap">
<div class="hdr"><div><div class="id">campaign {html.escape(campaign)} · candidate {html.escape(str(ev['card'].get('id')))} · evidence pack</div>
<h1>{html.escape(ev['card'].get('title') or ev['card'].get('id'))}<small>{html.escape(ev['formula'])}</small></h1>
<div class="chips"><span class="chip">{html.escape(str(ev['meta']['source']))} · {ev['meta']['assets']:,} assets</span>
<span class="chip">hold {ev['hold']} · decile long-short</span><span class="chip">{html.escape(ev['card'].get('reason', {}).get('edge_type', ''))}: {html.escape(ev['card'].get('reason', {}).get('counterparty', ''))}</span>
<span class="chip">trial N {ev['final_deflation']['n_raw']} · N_eff {_fmt(ev['final_deflation']['n_eff'], 1)}</span><span class="chip">data {ev['meta']['data']}</span></div></div>
<div>{badge}</div></div>{warn}
<div class="kpis">{k_html}</div>
<div class="grid" style="grid-template-columns:1.6fr 1fr">
<div class="panel"><div class="ph">Long-short, net of costs <span><span class="b">━ candidate</span> {'<span class="m">━ ' + html.escape(ev['nearest']) + ' (nearest known)</span>' if ev.get('nearest') else ''}</span></div>{eq}</div>
<div class="panel"><div class="ph">Decile returns, annualized % <span>development window</span></div>{dec}</div></div>
<div class="grid" style="grid-template-columns:1fr 1fr 1fr 1.15fr">
<div class="panel"><div class="ph">IC by horizon <span>hold {ev['hold']}</span></div>{ich}</div>
<div class="panel"><div class="ph">Rolling 1-year IC</div>{ric}</div>
<div class="panel"><div class="ph">Sharpe vs cost <span>bps per side</span></div>{cc}</div>
<div class="panel"><div class="ph">Explained by known factors</div><table><tr><th>factor</th><th>β</th><th>t</th></tr>{ft}</table>{pub_html}</div></div>
<div class="grid" style="grid-template-columns:1.25fr 1fr 1fr 1fr">
<div class="panel"><div class="ph">Checks <span>cheapest killers first</span></div><div class="chk">{_checks_html(v['checks'])}</div></div>
<div class="panel"><div class="ph">Subperiods</div><table><tr><th>window</th><th>IC</th><th>t</th><th>&gt; 0</th></tr>{st}</table></div>
<div class="panel"><div class="ph">Before vs after model cutoff</div><table>
<tr><th></th><th>{wpre['from'][:7]} → {wpre['to'][:7]}</th><th>after</th></tr>
<tr><td>rows</td><td>{wpre['n']}</td><td>{wpost['rows']}</td></tr>
<tr><td>rank IC</td><td>{_fmt(wpre['ic'], 3)}</td><td class="g">{_fmt(wpost['ic'], 3)}</td></tr>
<tr><td>Sharpe, net</td><td>{_fmt(wpre['sharpe'])}</td><td class="g">{_fmt(wpost['sharpe'])}</td></tr>
<tr><td>hit rate</td><td>{_fmt(wpre['hit'], 0, pct=True)}</td><td>{_fmt(wpost['hit'], 0, pct=True)}</td></tr>
<tr><td>model saw it</td><td class="r">yes</td><td class="g">no</td></tr></table><div class="note">{cut_note}</div></div>
<div class="panel"><div class="ph">Can you trade it</div><table>{trad}</table></div></div>
<div class="foot">alphadesk {__version__} · every number above comes from the evaluator; the holdout window is not shown · generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div></body></html>"""


def campaign_html(campaign: str, verdicts: list, survivors: dict, counts: dict) -> str:
    total = len(verdicts)
    stage = [0] * 14
    for v in verdicts:
        reached = 13 if v["survived"] else (v["died_at"] or 0)
        for k in range(reached):
            stage[k] += 1
    rows = []
    for k in range(13):
        alive = stage[k] if k else total
        rows.append(f'<div class="row"><span>{k} {html.escape(CHECK_NAMES[k])}</span><span class="bar"><i style="width:{100 * alive / max(total, 1):.1f}%"></i></span><span class="mono">{alive}</span></div>')
    surv = "".join(f'<tr><td><a href="{html.escape(cid)}.html">{html.escape(cid)}</a></td><td class="mono">{html.escape(f)}</td><td class="g">survived</td></tr>'
                   for cid, f in survivors.items())
    grave = "".join(f'<tr><td>{html.escape(str(v["card"]))}</td><td class="mono">{html.escape(str(v["formula"]))[:60]}</td>'
                    f'<td class="r">✕ {v["died_at"]} {html.escape(CHECK_NAMES.get(v["died_at"], ""))}</td></tr>'
                    for v in verdicts if not v["survived"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>campaign {html.escape(campaign)}</title>{FONTS}<style>{CSS}</style></head><body><div class="wrap">
<div class="id">alphadesk · campaign</div><h1>{html.escape(campaign)}<small>{total} hypotheses · {len(survivors)} survived</small></h1>
<div class="chips"><span class="chip">trials logged {counts.get('trials')}</span><span class="chip">validation queries {counts.get('validation_queries')}</span>
<span class="chip">holdout opened {counts.get('holdout_opened')}×</span></div>
<h2>Where ideas died</h2><div class="panel funnel">{''.join(rows)}</div>
<h2>Survivors</h2><div class="panel"><table><tr><th>card</th><th>formula</th><th></th></tr>{surv or '<tr><td>none</td><td></td><td></td></tr>'}</table></div>
<h2>Graveyard</h2><div class="panel"><table><tr><th>card</th><th>formula</th><th>died at</th></tr>{grave}</table></div>
<div class="foot">alphadesk {__version__} · generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}</div></div></body></html>"""


def write_campaign(desk, campaign: str, verdicts: list, cards: dict, out: Path) -> Path:
    from . import evidence
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    counts = desk.log.count(campaign)
    survivors = {}
    for v in verdicts:
        if v["survived"]:
            cid = v["card"]
            ev = evidence.build(desk, cards[cid], v)
            (out / f"{cid}.html").write_text(evidence_html(ev, campaign, counts["trials"]), encoding="utf-8")
            (out / f"{cid}.json").write_text(json.dumps(ev, default=float), encoding="utf-8")
            survivors[cid] = v["formula"]
    (out / "index.html").write_text(campaign_html(campaign, verdicts, survivors, counts), encoding="utf-8")
    return out / "index.html"
