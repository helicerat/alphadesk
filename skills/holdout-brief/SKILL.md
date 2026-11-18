---
name: holdout-brief
description: Freeze a campaign's survivors and hand the user the one command that opens the sealed holdout. Use when a campaign is finished and the user wants the final test.
---

# Holdout brief

The holdout is the last window of data, after the model's training cutoff. It is opened once, by the user, after the list of candidates is frozen. Claude never opens it: a plugin hook blocks the command and the command needs a real terminal.

1. Run `alphadesk freeze --campaign <name>`. It hashes the survivor list into the trial log and writes `desk/holdout_brief.md`.
2. Show the user the brief: the frozen list, its hash, and the command

       alphadesk holdout <name>

3. Tell them what to expect: a candidate "holds" if the holdout IC has the same sign and keeps at least half of the development IC. Every extra opening is recorded and shown in later reports.
4. Do not run the command, suggest workarounds, or read the holdout results file. If the user pastes the output back, explain it.
