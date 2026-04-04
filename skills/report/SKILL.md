---
name: report
description: Synthesize research and valuation into a final investment report
---

Generate a comprehensive investment report for ticker symbol **$ARGUMENTS** by synthesizing qualitative research, quantitative valuation, and assumption metadata into an opinionated verdict.

This skill does NOT perform web searches or API calls — it synthesizes existing files only.

## Python Environment
When running Python code, set `PYTHONPATH` so `stock_analyzer` is importable:
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "from stock_analyzer import ..."
```

## Output Template

The report MUST follow this structure:

```
# {Company} ({TICKER}) — Investment Report
**Date:** YYYY-MM-DD

## Verdict
**RECOMMENDATION** | Fair value: $XXX (range: $XXX-$XXX) | Current: $XXX | Upside: X.X%
Confidence: High/Medium/Low | Signals: Growth X (Y), Moat X/Y, Margin X, Capital X

## The Investment Case
[one paragraph]

## Alignment Check
[signal vs assumption, key risks vs valuation structure, key debate vs assumptions]

## What You're Paying For
[reverse DCF context + manual overrides as specific bets]

## Key Assumption Vulnerability
[the one or two assumptions that flip the recommendation]

## What Would Change This
[specific triggers with timeframes]

## Prior Analysis (if available)
[omit if no prior analysis exists]
```

## Steps:

### 1. Load and Validate Inputs
- Load the most recent `research_*.md` from `data/$ARGUMENTS/`
- Load the most recent `valuation_*.md` from `data/$ARGUMENTS/`
- Load `assumptions.json` from `data/$ARGUMENTS/` including `_manual_overrides` via `StockManager.load_manual_overrides()`. If assumptions.json doesn't exist or has no `_manual_overrides`: note "No calibration metadata available" and base the "What You're Paying For" section on valuation output only.
- **If research is missing:** Tell the user to run `/research $ARGUMENTS` first, then stop
- **If valuation is missing:** Tell the user to run `/value $ARGUMENTS` first, then stop
- **Freshness validation:** Compare dates of research and valuation files. If they differ by more than 1 day, warn: "Research is from {date1}, valuation from {date2} — they may reflect different data. Consider re-running the older one." Do not stop.
- Check for prior `analysis_*.md` files for the Prior Analysis section
- Display: "Based on research_{date}.md, valuation_{date}.md, assumptions.json"

### 2. Analyze
Before writing, think through the analytical questions:
- Extract research signals: Growth signal, Confidence, Moat, Direction, Margin signal, Capital intensity
- Extract valuation results: fair value, sensitivity range, reverse DCF implied growth, highest-impact assumption, sanity check warnings, confidence-adjusted recommendation
- Extract assumption metadata: manual overrides, key assumption values (revenue growth, target margin, S/C ratio)
- **Alignment check:**
  - For each research signal, compare to the corresponding assumption. Flag disconnects — if aligned, a brief note is sufficient. Spend detail on mismatches.
  - Check if valuation structure is vulnerable to research Key Risks (e.g., high terminal value concentration + long-term uncertainty flagged in research)
  - Identify where the user is betting on the bull or bear side of the Key Debate
- **Identify the user's specific bet:** Where do assumptions (especially manual overrides) diverge from market-implied growth or research signals? This is the core of "What You're Paying For."
- **Determine verdict:** Start with the confidence-adjusted recommendation from valuation. Qualify if alignment check reveals consistent bullish or bearish lean against research signals. E.g., "BUY, but all three core assumptions lean bullish relative to Medium confidence research — this is a compounding bet."

### 3. Write the Report
Write the report using the output template.

**## Verdict**
- Recommendation (qualified by alignment findings if needed)
- Fair value as range from sensitivity bounds
- Current price and upside/downside
- Confidence level from research
- One-line signal summary

**## The Investment Case**
- One paragraph. The single clearest argument for or against investing.
- "You're betting that..." — weave in the user's specific assumptions, the research context, and the valuation math.
- Reference the Key Debate from research if relevant.
- This is not a summary of everything — it's the thesis distilled to its essence.

**## Alignment Check**
- **Signal vs assumption alignment:** Flag disconnects between research signals and DCF assumptions. If aligned, brief note. If mismatched, explain the tension.
- **Key Risks vs valuation structure:** Does the valuation's structure make it vulnerable to the risks research identified?
- **Key Debate vs assumptions:** Is the user betting on the bull or bear side of the market's central question?

**## What You're Paying For**
- Market-implied growth (from reverse DCF in valuation) vs assumed growth
- Manual overrides as the user's deliberate views: what specifically they believe that the market doesn't
- Frame the gap as a specific thesis, not just a number difference

**## Key Assumption Vulnerability**
Two dimensions — cover both:
- **Highest impact:** Which assumption swings fair value the most? (from sensitivity analysis). State the specific threshold: "If margin comes in at 40% instead of 44%, fair value drops to $304 — flipping from HOLD to SELL." Connect to the research Key Risk that could trigger this.
- **Most probable:** Which assumption is most likely to be wrong? (from manual overrides vs data, or Low/Medium confidence signals). This may be a different assumption than highest-impact. E.g., "S/C staying at 0.55 instead of 0.70 is more probable than a margin collapse — it would erode ~$25-30 of fair value without any dramatic trigger."
- When both dimensions point to the same assumption, combine them. When they differ, discuss both — the user needs to know what would hurt most AND what's most likely to happen.

**## What Would Change This**
- 2-4 specific, actionable triggers with timeframes
- Include both downside triggers (what would worsen the outlook) and upside triggers (what would improve it)
- Include a re-evaluation trigger: "Re-evaluate after [next earnings date]"

**## Prior Analysis (if available)**
- If older `analysis_*.md` exists: previous recommendation vs current, fair value change, biggest assumption that moved
- If no prior analysis, omit this section entirely

**Writing quality:** Be concise and opinionated. Every sentence should either support the verdict, flag a risk, or provide actionable context. No filler.

### 4. Self-Review
Re-read the report and check:
- **Is the verdict justified?** Does the analysis below support the recommendation, or does the alignment check undermine it? If the alignment check found 3 disconnects but the verdict is an unqualified BUY, something is wrong.
- **Standalone test:** Would a reader with only this document have enough context to understand AND challenge the recommendation?
- **Specificity check:** Are the "What Would Change This" triggers concrete enough to act on? "If growth slows" fails. "If Q3 Azure growth < 33%" passes.
- **Evidence check:** Are there any claims not supported by the research or valuation files? If so, cite the basis or cut it.
- If issues found, revise before saving.

### 5. Save Report
- Save to `data/<SYMBOL>/analysis_YYYY-MM-DD.md`
- Use `StockManager.save_analysis(symbol, content)` (default filename)
- The saved file should include all sections from the template plus a note of source files used at the bottom

### 6. Display Summary
Show a concise summary:
- Verdict line (recommendation, fair value range, upside)
- Signal summary
- Number of alignment disconnects found
- Key assumption vulnerability one-liner
- Prior analysis delta if available (e.g., "vs previous: was BUY at $450, now HOLD at $386")
- Location of saved file
