"""Run operational DQ checks without triggering any source synchronization.

By default this command is a pure read-only check. Add --record-run only when a
compact audit SystemEvent should be appended; it never edits business rows.
"""
import argparse
import json

from app.data_quality import evaluate_data_quality
from app.database import SessionLocal


def main():
    parser=argparse.ArgumentParser(description="Read-only Al-Ahsa platform data-quality validation")
    parser.add_argument("--scope",choices=("fast","full","weekly"),default="full")
    parser.add_argument("--record-run",action="store_true",help="Append the run summary as a SystemEvent")
    args=parser.parse_args()
    with SessionLocal() as db:
        result=evaluate_data_quality(db,scope=args.scope,trigger="local_cli",persist=args.record_run)
        if args.record_run: db.commit()
        print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
        return 1 if result["counts"]["fail"] else 0


if __name__=="__main__":
    raise SystemExit(main())
