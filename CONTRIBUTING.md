# Contributing

Thanks for improving Running Coach Skill.

Keep contributions focused on the skill itself:

- Update `SKILL.md` only for core workflow changes.
- Put detailed coaching rules in `references/`.
- Put deterministic reusable logic in `scripts/`.
- Use synthetic data in examples and tests.
- Do not include real health exports, COROS tokens, OAuth callback URLs, passwords, or private activity files.

Before opening a pull request, run:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
```

