---
name: analyze
description: Perform comprehensive stock analysis with DCF valuation
---

Perform a comprehensive stock analysis for ticker symbol **$ARGUMENTS** by orchestrating the sub-skills in sequence.

## Orchestration Steps:

### 1. Fetch Data
- Display: **"Step 1/5: Fetching data..."**
- Invoke `/fetch {ticker}` to fetch all sources with fresh data (including current quote price)

### 2. Research
- Display: **"Step 2/5: Researching..."**
- Invoke `/research {ticker}`

### 3. Calibrate Assumptions
- Display: **"Step 3/5: Calibrating assumptions..."**
- Invoke `/calibrate {ticker}` — walks through each assumption with research context and data-driven recommendations

### 4. Valuation
- Display: **"Step 4/5: Running valuation..."**
- Invoke `/value {ticker}`

### 5. Report
- Display: **"Step 5/5: Generating report..."**
- Invoke `/report {ticker}`

## Important Notes:
- Each sub-skill handles its own data loading, saving, and display
- This skill is a thin orchestrator — all logic lives in the sub-skills
- If any sub-skill fails, stop and report the error rather than continuing
- Pipeline: fetch → research → calibrate → value → report. Each step depends on the prior step's output.
