---
name: replicate
description: Rebuild a published trading signal from a paper (PDF, arXiv, SSRN or URL), run it through the desk's 13 checks, and report what is left of it today. Use when the user gives a paper, a factor name from the literature, or asks "does this anomaly still work".
---

# Replicate a paper

The desk's most reliable source of ideas is published research: every paper is dated, so what happened after publication can be measured directly, and nothing has to be invented.

## Steps

1. **Campaign name.** Use `rep_<short_paper_name>` unless the user gave one. Call the `status` MCP tool to make sure the desk is up and to see which data it has loaded.

2. **Scout.** Delegate to the `scout` agent with the paper. It writes `research/<campaign>/claims.json` and `claims.md`. Show the user the main claim, its verbatim quote and the published numbers in 3 lines. If the scout says the claim is not testable on the loaded data, stop here and say why.

3. **Replicator.** Delegate to the `replicator` agent. It writes one card and submits it once.

4. **Reconciler, before trusting the verdict.** Give the `reconciler` agent the card's `formula` ONLY. Compare its plain-language reading with the card's reason and the paper's construction. If they disagree, tell the user what differs; the replicator fixes the card and that resubmission is a counted try.

5. **Report.** Delegate to the `reporter` agent, then tell the user:
   - what the paper reported vs what the desk found
   - where it died, if it died, in one sentence
   - the path to `desk/reports/<campaign>/index.html`

## Rules

- One honest replication first. Variants come later, through `/alphadesk:campaign extend`, and each counts against the campaign.
- Never read files under the desk's data folder or `desk/trials/`. The plugin blocks it; the MCP tools are the only way in.
- Do not call a survivor "alpha". It is a research candidate until the user opens the holdout.
