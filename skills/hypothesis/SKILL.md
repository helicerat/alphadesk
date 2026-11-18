---
name: hypothesis
description: Turn the user's own trading idea into a hypothesis card the desk will accept - reason first, then code, then a contract - and submit it once. Use when the user describes an idea in words ("stocks that X tend to Y").
---

# Your own hypothesis

## 1. The reason, before any data

Ask the user, or fill in from what they said, three things. Do not continue until all three are in plain words:

- **who is on the other side** of the trade and why they keep losing
- **edge type**: risk_premium, structural, behavioral, informational or analytical
- **what should make it fade**: crowding, a rule change, a data source becoming common

An idea with no counterparty dies at check 0. That is on purpose.

## 2. The code

Delegate to the `coder` agent with the idea and the reason. It returns a card with a formula, a hold and a behavioral contract (`expect`).

## 3. The check of idea against code

Give ONLY the formula to the `reconciler` agent. Read its description back to the user next to their own words. If the user says "that's not what I meant", go back to step 2. This happens before submission, so it costs no try.

## 4. Submit once

Call `submit` with the card. Show the user the verdict:

- survived: say which checks it passed and that `alphadesk report` builds its evidence pack
- died: name the check and the reason in one sentence, and what (if anything) would be a fair next test. A fair next test changes the idea, not the parameters.
