---
name: campaign
description: Plan and run a research campaign on the desk - a budgeted search around a paper, a dataset question or a surviving idea, with every try counted. Use when the user wants to search for signals, extend a replication ("extend c004"), or explore a dataset.
---

# Run a campaign

A campaign is a budget of tries spent on one question. The evaluator deflates every result by the number of tries, so the plan matters more than the speed.

## 1. Plan, then wait for approval

Write a plan in 6 lines and show it to the user. Do nothing else until they approve it:

- **question**: one sentence (a paper to extend, a dataset to question, a survivor to stress)
- **source of ideas**: paper claims, a dataset, the user's own hypothesis, or variants of a survivor. Free invention from memory is the weakest source and the desk discourages it
- **data**: what the `status` tool says is loaded
- **budget**: number of variants, default 30. Tell the user that more tries raise the bar for every result
- **horizon**: holding period in rows
- **stop rules**: stop when the budget is spent, when 3 rounds in a row add nothing, or when the user says so

## 2. Each round

1. Call `graveyard` and `status`.
2. Start 2 or 3 `generator` agents in parallel with the seed and an equal share of the round's budget. Give each a different brief (horizon, neutralization, liquidity, a second input) so their proposals differ.
3. Drop duplicates and anything already in the graveyard.
4. For each remaining card: give ONLY the formula to the `reconciler` agent and compare its reading with the card. Fix or drop cards that don't match.
5. Submit the survivors of that check through `submit`, one card per call.
6. After the round, report in 3 lines: tried, died where, survived.

## 3. Close

1. Delegate to the `reporter` agent.
2. If anything survived, run `alphadesk freeze --campaign <name>` and show the user the brief it writes. Remind them that the holdout is theirs to open, once, in their own terminal.

## Rules

- Never read the desk's data folder, `desk/trials/` or another campaign's reports to design variants. Verdicts from `submit` and the graveyard are the only feedback.
- Never resubmit the same idea with a tweak to get it past a check. If an idea died at 3, it is in the graveyard.
- The model (you) remembers markets up to its training cutoff. Keep company names, tickers and dates out of idea generation.
