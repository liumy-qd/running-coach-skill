# Running Coach Skill

Running Coach is an open Codex skill for COROS-based running analysis. It helps an agent review recovery, training load, sleep, HRV, resting heart rate, running fitness, lap data, weather impact, fueling, injury risk, and goal-specific plans for 5K, 10K, half marathon, and marathon training.

The skill is designed as a self-contained coaching workflow:

- COROS MCP first, `coros-mcp` CLI fallback.
- Data quality and confidence checks before conclusions.
- Personal 7/28/56 day baselines.
- Readiness gating before intensity decisions.
- Lap, segment, interval, marathon-pace, and long-run analysis.
- Weather, heat stress, fueling, fatigue, and injury-risk adjustments.
- Plan-execute-review feedback loops.

## Installation

Copy this folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R running-coach-skill ~/.codex/skills/running-coach
```

Then invoke it in Codex:

```text
Use $running-coach to analyze my recent COROS running data and give today's training recommendation.
```

## Optional COROS MCP

The skill expects a COROS MCP server when available. If direct MCP access is not available, it can use the local `coros-mcp` CLI fallback described in `references/coros-tools.md`.

Never commit access tokens, OAuth callback parameters, passwords, or exported private health files to this repository.

## Scripts

```bash
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
```

`examples/context-summary.json` can be regenerated from the text sample:

```bash
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt > examples/context-summary.json
```

## Repository Layout

- `SKILL.md` - main skill entrypoint.
- `agents/openai.yaml` - UI metadata and COROS MCP dependency metadata.
- `references/` - detailed coaching rules loaded as needed.
- `scripts/` - deterministic helpers for lap analysis and context evaluation.
- `examples/` - synthetic, non-private sample inputs.

## Validation

```bash
python3 -m py_compile scripts/*.py
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
```

If you have Codex's `skill-creator` validation script available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## License

MIT

