# Contributing

Thanks for improving Running Coach Skill.

Keep contributions focused on the skill itself:

- Update `SKILL.md` only for core workflow changes.
- Put detailed coaching rules in `references/`.
- Put deterministic reusable logic in `scripts/`.
- Use synthetic data in examples and tests.
- Do not include real health exports, COROS tokens, OAuth callback URLs, passwords, or private activity files.
- Scripts must run on Python >= 3.8 with the standard library only (`fitdecode` is allowed only in the FIT binary path of `analyze_fit.py`); keep `from __future__ import annotations` in every script.
- Runner-local state lives under `~/.running-coach/` (monthly data archive + athlete profile), always outside this repository; never commit archive or profile files, and never point tests at real paths.

Before opening a pull request, run:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json > /tmp/athlete-context.json
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json --profile examples/athlete-profile.json > /tmp/athlete-context-profile.json
python3 scripts/validate_prescription.py --input examples/prescription-safe.json --context /tmp/athlete-context.json
python3 scripts/archive_snapshot.py --input examples/athlete-bundle.json --context /tmp/athlete-context.json --archive-dir /tmp/rc-archive
python3 -m unittest discover -s tests -p 'test_*.py'
```
