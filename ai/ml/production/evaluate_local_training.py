"""Read-only local training-readiness evaluation for Siksha Sarathi Phase 7."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai.ml.production.training_readiness import build_training_readiness_report, _connect_runtime


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Assess local Siksha Sarathi readiness for training and holdout evaluation without creating artifacts."
    )
    parser.add_argument("--subject", help="Optional subject filter.")
    parser.add_argument("--json", help="Optional JSON output path for the privacy-safe readiness report.")
    return parser.parse_args()


def main():
    args = _parse_args()
    connection = _connect_runtime()
    try:
        report = build_training_readiness_report(connection, subject=args.subject)
        payload = {
            "TRAINING_READINESS_VERSION": report.get("TRAINING_READINESS_VERSION"),
            "FEATURE_CONTRACT_VERSION": report.get("FEATURE_CONTRACT_VERSION"),
            "subject": report.get("subject"),
            "training_ready": report.get("training_ready"),
            "evaluation_ready": report.get("evaluation_ready"),
            "deployment_ready": report.get("deployment_ready"),
            "readiness_state": report.get("readiness_state"),
            "state": report.get("state"),
            "blockers": report.get("blockers", []),
            "privacy_safe_summary": report.get("privacy_safe_summary", {}),
            "eligible_training_snapshots": report.get("eligible_training_snapshots"),
            "unique_students": report.get("unique_students"),
            "unique_target_dates": report.get("unique_target_dates"),
            "subjects_represented": report.get("subjects_represented"),
            "classes_represented": report.get("classes_represented"),
            "secondary_student_group_robustness": report.get("secondary_student_group_robustness", {}),
            "baseline_evaluation": report.get("baseline_evaluation", {}),
        }
        print(json.dumps(payload, sort_keys=True, default=str))
        if args.json:
            out_path = Path(args.json)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
            print(f"Wrote readiness report to {args.json}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
