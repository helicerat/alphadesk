"""Command line: ``alphadesk demo``, ``alphadesk selftest``, ``alphadesk evaluate``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

G, R, Y, D, B, X = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def _utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def cmd_selftest(args):
    from .selftest import Exam
    t0 = time.time()
    print(f"{B}alphadesk selftest{X}  {D}inputs with a known answer{X}\n")
    ex = Exam(fast=not args.full)

    def show(r):
        mark = f"{G}PASS{X}" if r["ok"] else f"{R}FAIL{X}"
        print(f"  {mark}  {r['exam']:<24}{D}{r['what']}{X}")
        print(f"        {' ' * 24}{r['detail']}")

    res = ex.run(show)
    ok = sum(r["ok"] for r in res)
    color = G if ok == len(res) else R
    print(f"\n{color}{B}{ok}/{len(res)} passed{X}  {D}{time.time() - t0:.0f}s{X}")
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0 if ok == len(res) else 1


def cmd_demo(args):
    from . import synth
    from .evaluator import Desk
    from .selftest import card
    from .triallog import TrialLog

    t0 = time.time()
    out = Path(args.out)
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"{out} already has a trial log. Use --force to start a fresh one.")
        return 1
    if args.force and out.exists():
        import shutil
        shutil.rmtree(out)
    n, T = (300, 1500) if args.fast else (500, 2520)
    p = synth.make_market(n_assets=n, n_days=T, n_noise=args.noise, seed=args.seed)
    print(f"{B}synthetic market{X}   {n:,} assets · {T:,} days · planted daily IC "
          + " / ".join(f"{v:.2f}" for v in synth.PLANTED.values()))
    desk = Desk(p, TrialLog(out), library=synth.KNOWN_FACTORS, seed=args.seed)
    cards = [card(k, f"cs_rank({k})", k) for k in synth.PLANTED]
    cards += [card(f, f"cs_rank({f})", f) for f in p.fields if f.startswith("noise_")]
    cards.append(card("trend_follow", "cs_rank(log(delay(close, 21)) - log(delay(close, 252)))",
                      hold=60, ref="delta(log(close), 231)"))
    print(f"{B}campaign{X}           {len(cards)} hypotheses · trial log {out}\n")
    verdicts = []
    for c in cards:
        v = desk.submit(c, campaign="demo")
        verdicts.append(v)
        if c["id"] in synth.PLANTED or c["id"] == "trend_follow" or v["survived"]:
            ic = v.get("ic_dev", {})
            tag = f"{G}found{X}" if v["survived"] else f"{Y}{v['summary']}{X}"
            mark = f"{G}✓{X}" if v["survived"] else f"{Y}~{X}" if c["id"] in synth.PLANTED else f"{R}✕{X}"
            line = f"  {mark} {c['id']:<14}"
            if ic:
                line += f"IC {ic.get('mean', float('nan')):.3f}  t {ic.get('t', float('nan')):>4.1f}  "
            if "dsr" in v:
                line += f"DSR {v['dsr']['dsr']:.2f}  "
            print(line + tag)
    noise = [v for v in verdicts if (v["card"] or "").startswith("noise_")]
    died = {}
    for v in noise:
        died[v["died_at"]] = died.get(v["died_at"], 0) + 1
    surv = sum(v["survived"] for v in noise)
    where = ", ".join(f"{n} at check {k}" for k, n in sorted(died.items(), key=lambda x: (x[0] is None, x[0])) if k is not None)
    print(f"  {R}✕{X} {len(noise)} noise      {surv} survive · {where}")
    (out / "verdicts.json").write_text(json.dumps(verdicts, indent=2, default=float), encoding="utf-8")
    print(f"\n{D}verdicts {out / 'verdicts.json'} · {time.time() - t0:.0f}s{X}")
    return 0


def cmd_evaluate(args):
    from . import synth
    from .evaluator import Desk
    from .triallog import TrialLog
    c = json.loads(Path(args.card).read_text(encoding="utf-8"))
    p = synth.make_market(seed=args.seed)
    desk = Desk(p, TrialLog(args.out), library=synth.KNOWN_FACTORS, seed=args.seed)
    v = desk.submit(c, campaign=args.campaign)
    if args.verdict_only:
        print(json.dumps({"survived": v["survived"], "died_at": v["died_at"], "summary": v["summary"]}))
    else:
        print(json.dumps(v, indent=2, default=float))
    return 0


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(prog="alphadesk", description="A quant research desk for Claude Code.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest", help="run the exam: inputs with a known answer")
    s.add_argument("--full", action="store_true", help="full-size market (slower)")
    s.add_argument("--json", help="write results to this file")
    s.set_defaults(fn=cmd_selftest)

    d = sub.add_parser("demo", help="a campaign on a synthetic market with planted signals")
    d.add_argument("--out", default="desk/demo")
    d.add_argument("--noise", type=int, default=40)
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--fast", action="store_true")
    d.add_argument("--force", action="store_true")
    d.set_defaults(fn=cmd_demo)

    e = sub.add_parser("evaluate", help="run one hypothesis card through the checks")
    e.add_argument("card")
    e.add_argument("--out", default="desk/trials")
    e.add_argument("--campaign", default="c001")
    e.add_argument("--seed", type=int, default=7)
    e.add_argument("--verdict-only", action="store_true", help="print only the verdict, as an agent sees it")
    e.set_defaults(fn=cmd_evaluate)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
