---
name: evidence
description: Build and explain the evidence pack for a campaign or one candidate - the HTML report with every check, chart and warning. Use when the user asks to see results, "show me the report", or "/alphadesk:evidence c004 26".
---

# Evidence

1. Run `alphadesk report --campaign <name>` (the desk's default campaign if none is given). It writes `desk/reports/<name>/index.html` (where every idea died) and one `<card>.html` per survivor.
2. Give the user the path to open. For a single candidate, read its `<card>.json` next to the HTML and explain it in this order, one line each:
   - the reason on the card
   - rank IC and t on the development window, IC by horizon and where it peaks
   - net Sharpe at the configured cost, and the cost at which it goes to zero
   - deflated Sharpe at the campaign's final number of tries (if the pack warns that it no longer clears 0.95, say that first)
   - what the post-cutoff window shows, and whether it is long enough to prove the size or only the sign
   - every warning in the pack, verbatim
3. Never restate a number differently from the JSON. Never describe a candidate as profitable.
