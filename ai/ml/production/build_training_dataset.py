"""Read-only training-dataset builder for the production feature contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from ai.ml.production.feature_builder import build_training_dataset, generate_diagnostics


def repository_root():
    return Path(__file__).resolve().parents[3]


def _connect_runtime():
    import MySQLdb
    from MySQLdb.cursors import DictCursor

    load_dotenv(repository_root() / ".env")
    connection = MySQLdb.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "siksha_user"),
        passwd=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DB", "siksha_sarathi"),
        cursorclass=DictCursor,
    )
    return connection


def main():
    parser = argparse.ArgumentParser(description="Build the production next-paper feature dataset.")
    parser.add_argument("--subject", help="Optional subject filter.")
    parser.add_argument("--csv", help="Optional CSV export path.")
    parser.add_argument("--include-ineligible", action="store_true", help="Include rows with insufficient evidence.")
    args = parser.parse_args()

    connection = _connect_runtime()
    try:
        dataset = build_training_dataset(
            connection,
            subject=args.subject,
            include_ineligible=args.include_ineligible,
        )
        print(generate_diagnostics(connection, subject=args.subject))
        if args.csv:
            dataset.to_csv(args.csv, index=False)
            print(f"Saved dataset to {args.csv}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
