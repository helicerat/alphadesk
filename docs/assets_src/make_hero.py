"""Build docs/assets/hero.png from a real evidence pack and a real session.

    python docs/assets_src/make_hero.py <evidence.html> <session.json> docs/assets/hero.png

``session.json`` is a list of steps copied from a real Claude Code run:
[{"t": "12:15:02", "who": "Scout", "note": "...", "lines": ["...", "..."], "tone": "ok|warn|bad"}]
Needs playwright (only for building this image, not for using alphadesk).
"""

import html
import json
import sys
import tempfile
from pathlib import Path

TERM = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@800&family=JetBrains+Mono:wght@400;500;600&display=block" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box}
body{width:520px;height:__H__px;background:#000;color:#eef1f4;font:11px/1.5 "JetBrains Mono",Consolas,monospace;border:1px solid #262626;border-radius:10px;overflow:hidden;position:relative}
.tb{height:30px;background:#0a0a0a;border-bottom:1px solid #1c1c1c;display:flex;align-items:center;gap:7px;padding:0 12px}
.d{width:10px;height:10px;border-radius:50%}.p{padding:10px 14px}
.cc{font:800 15px Inter,sans-serif;color:#e8835a;display:flex;justify-content:space-between;align-items:baseline}
.cc span{font:500 10.5px "JetBrains Mono";color:#a3abb5}
.path{color:#8c949e;font-size:10.3px;border-bottom:1px solid #1d232c;padding:3px 0 6px;margin-bottom:6px}
.pr{color:#fff;margin-bottom:6px}.pr span{color:#8c949e}
.ln{display:flex;gap:8px;margin-top:4px}.ts{color:#6b737d}.h{font-weight:600}
.ok:before{content:"\\25CF  ";color:#3fe06e}.warn:before{content:"\\25CF  ";color:#e3b341}.bad:before{content:"\\25CF  ";color:#ff7b72}
.ind{padding-left:62px;color:#dfe4ea}.ind .m{color:#a3abb5}
.st{position:absolute;bottom:0;left:0;right:0;border-top:1px solid #1c1c1c;padding:6px 14px;color:#a3abb5;font-size:10.3px}
</style></head><body><div class="tb"><span class="d" style="background:#ff5f57"></span><span class="d" style="background:#febc2e"></span><span class="d" style="background:#28c840"></span></div>
<div class="p"><div class="cc">\\u273B Claude Code<span>__MODEL__ · alphadesk plugin</span></div><div class="path">__CWD__</div>
<div class="pr"><span>&gt;</span> __PROMPT__</div>__STEPS__</div><div class="st">__STATUS__</div></body></html>"""


def render_terminal(session: dict, height: int) -> str:
    steps = []
    for s in session["steps"]:
        tone = s.get("tone", "ok")
        note = f' <span class="m">{html.escape(s["note"])}</span>' if s.get("note") else ""
        steps.append(f'<div class="ln"><span class="ts">{html.escape(s["t"])}</span>'
                     f'<span class="h {tone}">{html.escape(s["who"])}</span>{note}</div>')
        if s.get("lines"):
            steps.append('<div class="ind">' + "<br>".join(html.escape(x) for x in s["lines"]) + "</div>")
    return (TERM.replace("__H__", str(height)).replace("__MODEL__", html.escape(session.get("model", "")))
            .replace("__CWD__", html.escape(session.get("cwd", "~/research")))
            .replace("__PROMPT__", html.escape(session["prompt"])).replace("__STEPS__", "".join(steps))
            .replace("__STATUS__", html.escape(session.get("status", ""))).replace("\\u273B", "&#10043;")
            .replace("\\\\25CF", "\\25CF"))


def main(evidence_html, session_json, out_png):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    session = json.loads(Path(session_json).read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp())
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1046, "height": 900}, device_scale_factor=2)
        pg.goto(Path(evidence_html).resolve().as_uri())
        pg.wait_for_load_state("networkidle")
        pg.add_style_tag(content="body{padding:12px!important}")
        pg.screenshot(path=str(tmp / "left.png"), full_page=True)
        lh = Image.open(tmp / "left.png").size[1] // 2
        (tmp / "term.html").write_text(render_terminal(session, lh), encoding="utf-8")
        pg2 = b.new_page(viewport={"width": 520, "height": lh}, device_scale_factor=2)
        pg2.goto((tmp / "term.html").as_uri())
        pg2.wait_for_load_state("networkidle")
        pg2.screenshot(path=str(tmp / "right.png"))
        b.close()
    L, R = Image.open(tmp / "left.png"), Image.open(tmp / "right.png")
    W = L.size[0] + R.size[0] + 3 * 24
    H = max(L.size[1], R.size[1]) + 2 * 24
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(L, (24, 24))
    canvas.paste(R, (24 + L.size[0] + 24, 24))
    canvas.save(out_png, optimize=True)
    print(out_png, canvas.size)


if __name__ == "__main__":
    main(*sys.argv[1:4])
