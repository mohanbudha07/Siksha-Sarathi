"""Guarded local model training and explicit artifact promotion CLI."""

from __future__ import annotations

import argparse
import json

from ai.ml.production.model_training import promote_candidate, run_training_from_connection
from ai.ml.production.training_readiness import _connect_runtime


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate and optionally stage a locally approved Siksha Sarathi model candidate."
    )
    parser.add_argument("--subject", help="Optional subject filter for real MySQL evidence.")
    parser.add_argument("--output-dir", help="Explicit staging directory for an approved candidate bundle.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate readiness and candidates without fitting a final model or writing files.")
    parser.add_argument("--promote-from", help="Explicitly promote a validated staged candidate directory.")
    parser.add_argument("--replace-active", action="store_true", help="Allow replacing an existing active artifact while retaining a backup.")
    args = parser.parse_args(argv)
    if args.dry_run and args.output_dir:
        parser.error("--dry-run cannot be combined with --output-dir")
    if args.promote_from and (args.output_dir or args.subject or args.dry_run):
        parser.error("--promote-from cannot be combined with training options")
    if args.replace_active and not args.promote_from:
        parser.error("--replace-active requires --promote-from")
    return args


def main(argv=None):
    args = _parse_args(argv)
    if args.promote_from:
        result = promote_candidate(
            args.promote_from,
            replace_existing=args.replace_active,
        )
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0

    connection = None
    try:
        connection = _connect_runtime()
        result = run_training_from_connection(
            connection,
            subject=args.subject,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
    except Exception:
        result = {
            "status": "training_refused",
            "reason": "readiness_evaluation_failed",
            "blockers": ["readiness_evaluation_failed"],
            "files_created": False,
            "estimator_fit_called": False,
        }
    finally:
        if connection is not None:
            connection.close()

    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())