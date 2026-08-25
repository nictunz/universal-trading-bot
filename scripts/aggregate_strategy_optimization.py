from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    files = sorted(Path(args.input_dir).glob("*.json"))
    if not files:
        raise SystemExit(f"no batch files in {args.input_dir}")

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    candidates = []
    covered: set[int] = set()
    for data in payloads:
        if data.get("symbol") != args.symbol or data.get("timeframe") != args.timeframe:
            raise SystemExit(f"unexpected market in batch: {data.get('symbol')} {data.get('timeframe')}")
        selection = data.get("trial_selection", {})
        covered.update(range(int(selection["start_trial"]), int(selection["end_trial"]) + 1))
        candidates.extend(data.get("top20", []))

    expected = set(range(1, args.trials + 1))
    missing = sorted(expected - covered)
    if missing:
        raise SystemExit(f"incomplete optimization batches; missing trials: {missing}")

    unique = {}
    for candidate in candidates:
        trial = int(candidate["trial"])
        current = unique.get(trial)
        if current is None or float(candidate["score"]) > float(current["score"]):
            unique[trial] = candidate
    ranked = sorted(unique.values(), key=lambda x: float(x["score"]), reverse=True)
    viable = [x for x in ranked if float(x["score"]) > -1e17]
    if not viable:
        raise SystemExit("no viable candidate across all batches")

    first = payloads[0]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "cache": first.get("cache"),
        "trials_requested": args.trials,
        "trials_executed": len(covered),
        "batches_merged": len(files),
        "covered_trials": [min(covered), max(covered)],
        "execution_assumptions": first["execution_assumptions"],
        "objective": first["objective"],
        "warning": "Research only. Results are not automatically applied to PAPER or LIVE.",
        "best": viable[0],
        "top20": ranked[:20],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["best"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
