# Method

Every check the evaluator runs, the rule it applies, and where the rule comes from. Thresholds marked *proposal* are not published anywhere; they are this project's choice and can be changed in `alphadesk.evaluator.Config`.

The evaluator is plain Python. It owns the data windows, writes every attempt to the trial log and returns a verdict. No language model computes any number on this page.

## Data windows

| Window | Who sees it | What it is for |
|---|---|---|
| Development | the evaluator computes everything here; agents see the verdict | checks 1 to 10 |
| Validation | the evaluator, answering through Thresholdout | check 8 |
| Post-cutoff | the evaluator; agents see pass, weak or fail only | check 11 |
| Holdout | nobody until `alphadesk freeze`, then the user, once | check 12 |

The model cutoff comes from the desk config (`model_cutoff`). A language model has seen the market up to that date, so only data after it can tell a learned pattern from a remembered one.

## The checks

### 0. Reason gate
The card must say who is on the other side of the trade, which kind of edge it is (risk premium, structural, behavioral, informational, analytical) and what should make it fade, before any data is touched. No reason, no test.

### 1. Idea and code
Every card carries a behavioral contract (`expect`): signed relations a correct implementation must have, such as "higher with past 5-day return: negative". The evaluator measures each relation on the development window. A flipped sign or a wrong field breaks the contract and kills the card. The `reconciler` agent adds a second, independent check: it reads only the formula and says what it does, and the caller compares that with the card. Window lengths are only caught by the reconciler.

### 2. Point in time
Two independent layers:
- the formula language tracks, for every sub-expression, when its value becomes known. Anything that would read data from after row t does not compile
- the shift test recomputes every field and the signal on data cut at row t and compares everything before t with the full run. Any difference means a loader or operator reads ahead, even if it claims not to. The selftest plants such a loader (a feature with an information coefficient of 1.00) and requires the desk to kill it here, before any statistics

### 3. Rank IC
Spearman correlation between the signal at t and the return from t to t + hold, across assets, every date. The t-statistic uses non-overlapping observations (every `hold` rows).
Rule: t ≥ 3 and mean IC ≥ 0.02. An IC above 0.10 is flagged for a leak audit.
Source: Harvey, Liu, Zhu (2016), "...and the Cross-Section of Expected Returns", *Review of Financial Studies*, for t ≥ 3 after hundreds of published factors.

### 4. Decay against the holding period
IC at horizons 1, 5, 10, 20 and 60 rows. Rule (*proposal*): the IC at the card's holding period keeps at least half of the peak.

### 5. Costs
Decile long-short, equal weight, rebalanced every `hold` rows, charged `cost_bps` per side on traded weight (15 bps by default). Rule: net Sharpe above zero. The breakeven cost is reported.
Source: Novy-Marx & Velikov (2016), "A Taxonomy of Anomalies and Their Trading Costs", *RFS*; Chen & Velikov (2023), *JFQA*.

### 6. Microcaps
The IC is recomputed without the smallest 30% of assets by size. Rule: same sign and t ≥ 2.
Source: Hou, Xue, Zhang (2020), "Replicating Anomalies", *RFS*.

### 7. Novelty
Three ways to be old:
- the signal ranks assets like a factor in the library (mean cross-sectional rank correlation ≥ 0.7, *proposal*)
- its returns move with a library factor (correlation ≥ 0.7)
- its returns are explained by the library or by published factors (regression α t < 2)
Published factors: Ken French daily factors for daily data; 212 long-short series from Open Source Asset Pricing for monthly comparisons.
Sources: McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?", *Journal of Finance*; Chen & Zimmermann (2022), "Open Source Cross-Sectional Asset Pricing", *Critical Finance Review*; Jensen, Kelly, Pedersen (2023), *Journal of Finance*.

### 8. Subperiods and validation
The development window is cut in four. Rule: the same sign in all four, and t ≥ 2 with the best quarter removed. Then the validation window is asked through Thresholdout; its answer must keep at least half of the development IC (*proposal*).
Thresholdout: Dwork, Feldman, Hardt, Pitassi, Reingold, Roth (2015), "The reusable holdout: Preserving validity in adaptive data analysis", *Science* 349(6248):636-638. When validation agrees with development, the agent gets the development value back and learns nothing new; only a disagreement beyond a noisy threshold returns a noisy validation value. Every query is logged.

### 9. Deflated Sharpe
The net Sharpe of the candidate is compared with the expected best Sharpe of N_eff strategies with no edge, where N_eff is the effective number of independent tries in the campaign (participation ratio of the eigenvalues of the trials' return correlations). Rule: DSR ≥ 0.95. The minimum backtest length is reported.
The benchmark uses the null variance of a Sharpe estimate, not the spread of the trials' own Sharpes: the latter punishes a real signal for sharing a campaign with another real signal.
Reports deflate again at the campaign's final number of tries and warn if a candidate found early no longer clears 0.95.
Sources: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio", *Journal of Portfolio Management*; Bailey, Borwein, López de Prado, Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism", *Notices of the AMS*.

### 10. Probability of backtest overfitting
Combinatorially symmetric cross-validation over the variants of one family (16 blocks, all 12,870 splits). Needs 4 or more variants. Rule (*proposal*): PBO < 0.5.
Source: Bailey, Borwein, López de Prado, Zhu (2017), "The Probability of Backtest Overfitting", *Journal of Computational Finance*.

### 11. After the model cutoff
Rule: the IC keeps its sign after the cutoff. If there are fewer rows than the minimum track record length needed to prove the development Sharpe, the result is "weak": the sign is confirmed, the size is not.

### 12. Holdout
Opened by the user, once, after `alphadesk freeze` hashes the survivor list into the trial log. A candidate holds if the holdout IC has the same sign and keeps at least half of the development IC (*proposal*). Every opening is recorded.

## What the selftest proves

`alphadesk selftest` runs the desk on inputs with a known answer. CI runs it on every commit.

| Exam | Known answer |
|---|---|
| 1,000 random strategies, 1 year | the best one looks like Sharpe ≈ 3; none survive deflation |
| noise characteristics through all checks | none survive |
| planted signals, daily IC 0.03 and 0.02 | both found |
| the same signal on 60 assets, 2 years | rejected: not enough data to prove it |
| a loader that reads tomorrow's return | killed at check 2 |
| every operator, data cut at t | bit-identical before t |
| a rolling mean with a centered window | caught by the shift test |
| sign flip, wrong field, negative lag | all three caught |
| 12-1 momentum renamed | flagged as known |
| a library factor copied verbatim | flagged as known |
| no reason on the card; ranking by price level | rejected |
| 20 noise variants tuned on the same data | high probability of overfitting |
| the same card on two fresh desks | identical verdicts |

## Known limits

- Free US equity data has no historical list of delisted names. Equity reports carry a survivorship warning.
- The window after a model's cutoff is short. For slow signals it confirms the sign, not the size, and the report says so.
- The contract in check 1 catches wrong signs, wrong fields and lags. A wrong window length is only caught by the reconciler agent.
- Thresholds marked *proposal* are judgment calls, stated so they can be argued with.
