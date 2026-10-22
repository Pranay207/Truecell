"""Extract and later score a source-bound held-out benchmark pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.benchmark import ManifestError, extract_manifest, score_saved, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Run without access to truth.")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--inputs", type=Path, required=True)
    extract.add_argument("--outputs", type=Path, required=True)
    scoring = commands.add_parser("score", help="Score saved audits without re-extraction.")
    scoring.add_argument("--manifest", type=Path, required=True)
    scoring.add_argument("--outputs", type=Path, required=True)
    scoring.add_argument("--truth", type=Path, required=True)
    scoring.add_argument(
        "--run-sha256",
        required=True,
        help="Evaluator-recorded SHA-256 of run.json from the extraction stage.",
    )
    args = parser.parse_args()
    try:
        if args.command == "extract":
            run = extract_manifest(args.manifest, args.inputs, args.outputs)
            print(f"Extracted {len(run['cases'])} held-out cases without truth access.")
            print(f"run.json SHA-256: {sha256(args.outputs / 'run.json')}")
            print(
                "The evaluator must retain this digest outside the output directory before scoring."
            )
            return 0
        metrics = score_saved(
            args.manifest,
            args.outputs,
            args.truth,
            args.run_sha256,
        )
        passed = sum(item["pass"] for item in metrics)
        print(f"Exact passes: {passed}/{len(metrics)}. See {args.outputs / 'RESULTS.md'}")
        return 0 if metrics and passed == len(metrics) else 1
    except ManifestError as exc:
        print(f"Benchmark error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
