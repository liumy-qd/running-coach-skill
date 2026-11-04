# Contributing

Thanks for improving Running Coach Skill.

The repository rules are maintained once in [AGENTS.md](AGENTS.md) — layering discipline (core workflow in `SKILL.md`, coaching rules in `references/`, deterministic logic in `scripts/`), numeric thresholds only in `references/metrics.md`, Python >= 3.8 with the standard library only (`fitdecode` allowed solely in `analyze_fit.py`'s FIT binary path), synthetic data only, runner-local state outside the repository, and privacy red lines. Privacy posture lives in [PRIVACY.md](PRIVACY.md). Read both before your first contribution; they are short.

Before opening a pull request, run the same checks CI runs (see `.github/workflows/ci.yml`). Export `PYTHONPYCACHEPREFIX=/tmp/rc-pycache` first to keep `__pycache__` out of the workspace (CI's junk check is a physical `find`):

```bash
export PYTHONPYCACHEPREFIX=/tmp/rc-pycache

python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/gating_mcp.py --selfcheck

# Synthetic example round-trips, identical to the CI "Run synthetic examples" step
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json > /tmp/athlete-context.json
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json --profile examples/athlete-profile.json > /tmp/athlete-context-profile.json
grep -q "standing_constraints" /tmp/athlete-context-profile.json
python3 scripts/evaluate_context.py --input /tmp/athlete-context.json --markdown
python3 scripts/validate_prescription.py --input examples/prescription-safe.json --context /tmp/athlete-context.json
python3 scripts/archive_snapshot.py --input examples/athlete-bundle.json --context /tmp/athlete-context.json --prescription examples/prescription-safe.json --archive-dir /tmp/rc-archive
python3 scripts/archive_snapshot.py --stats --days 36500 --archive-dir /tmp/rc-archive
python3 scripts/garmin_to_bundle.py --input tests/fixtures/garmin_raw.json --output /tmp/garmin-bundle.json
grep -q '"source_device": "garmin"' /tmp/garmin-bundle.json
python3 scripts/build_athlete_context.py --input /tmp/garmin-bundle.json | grep -q '"name": "garmin"'
```

If you add, rename, or remove a key file, update the required-files list in `ci.yml` in the same PR.
