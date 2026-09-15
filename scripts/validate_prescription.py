#!/usr/bin/env python3
"""Validate a TrainingPrescription against deterministic safety gates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


QUALITY_TYPES = {"workout", "interval", "threshold", "tempo", "race_pace", "race"}
LONG_TYPES = {"long_run", "long"}
HARD_INTENSITIES = {"threshold", "interval", "hard", "tempo", "race", "race_pace", "high"}
DECISIONS = {"as_planned", "downshift", "rest_or_recovery", "ask"}
RECOVERY_SESSIONS = {"rest", "rest_or_recovery", "walk", "recovery"}


def conservative(reason: str, readiness: str = "red") -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "valid": False,
        "decision": "rest_or_recovery" if readiness == "red" else "downshift",
        "readiness": readiness,
        "errors": [reason],
        "safe_fallback": {
            "type": "rest_or_recovery" if readiness == "red" else "easy_run",
            "duration_min": 20 if readiness == "red" else 30,
            "intensity": "low",
            "stop_rules": ["疼痛影响步态、头晕胸痛、异常气短或热湿不适时立即停止。"],
        },
    }


def validate(prescription: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    errors: list[str] = []
    readiness = str(prescription.get("readiness") or context.get("readiness", {}).get("level") or "yellow").lower()
    decision = str(prescription.get("decision") or "ask")
    session = prescription.get("session") if isinstance(prescription.get("session"), dict) else {}
    session_type = str(session.get("type") or "")
    required = [
        "decision", "readiness", "confidence", "session", "evidence_window",
        "stop_rules", "downshift_option", "missing_data", "feedback_questions", "next_checkpoint",
    ]
    errors.extend(f"missing:{key}" for key in required if key not in prescription)
    confidence = prescription.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append("confidence must be between 0 and 1")
    if readiness not in {"green", "yellow", "red"}:
        errors.append("readiness must be green, yellow, or red")
    if prescription.get("decision") not in DECISIONS:
        errors.append("decision must be one of as_planned, downshift, rest_or_recovery, ask")
    if readiness == "red" and session_type not in RECOVERY_SESSIONS:
        errors.append("red_readiness_allows_recovery_only")
    if readiness == "yellow" and session_type in QUALITY_TYPES | LONG_TYPES:
        errors.append("yellow_readiness_disallows_quality_or_long_session")
    intensity = str(session.get("intensity") or "").lower()
    if readiness == "red" and intensity and intensity not in {"low", "recovery", "easy"}:
        errors.append("red_readiness_disallows_hard_intensity")
    if readiness == "yellow" and intensity in HARD_INTENSITIES:
        errors.append("yellow_readiness_disallows_hard_intensity")
    if session_type in QUALITY_TYPES | LONG_TYPES and isinstance(confidence, (int, float)) and float(confidence) < 0.65:
        errors.append("quality_or_long_session_requires_higher_confidence")
    if session_type in QUALITY_TYPES | LONG_TYPES and not prescription.get("evidence"):
        errors.append("quality_or_long_session_requires_evidence")
    if not isinstance(prescription.get("stop_rules"), list) or not prescription.get("stop_rules"):
        errors.append("stop_rules_required")
    if not isinstance(prescription.get("downshift_option"), str) or not prescription.get("downshift_option").strip():
        errors.append("downshift_option_required")
    if not isinstance(prescription.get("feedback_questions"), list) or not prescription.get("feedback_questions"):
        errors.append("feedback_questions_required")
    if not isinstance(prescription.get("next_checkpoint"), str) or not prescription.get("next_checkpoint").strip():
        errors.append("next_checkpoint_required")
    flags = context.get("risk_flags") or []
    if any(isinstance(flag, dict) and flag.get("code") in {"medical_red_flag", "gait_altering_pain"} for flag in flags):
        if session_type not in RECOVERY_SESSIONS:
            errors.append("medical_or_gait_risk_requires_recovery")
    if errors:
        return conservative(";".join(errors), readiness if readiness in {"red", "yellow"} else "red")
    return {"schema_version": "2.0", "valid": True, "errors": [], "prescription": prescription}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a running-coach TrainingPrescription.")
    parser.add_argument("--input", required=True, help="Prescription JSON path.")
    parser.add_argument("--context", help="Optional AthleteContext JSON path.")
    args = parser.parse_args()
    prescription = json.loads(Path(args.input).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8")) if args.context else {}
    print(json.dumps(validate(prescription, context), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
