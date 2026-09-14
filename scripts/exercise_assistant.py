"""Reproducible multi-turn bot audit with synthetic metrics and local output."""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "api"), str(ROOT / "api/tests")]
from app.support_knowledge import answer_for
from assistant_scenarios import conversation_scenarios


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for scenario, metrics, turns in conversation_scenarios():
        history = []
        for question, expected in turns:
            start = time.perf_counter()
            answer = answer_for(question, metrics=metrics, history=history[-12:])
            missing = [part for part in expected if part.casefold() not in answer["answer"].casefold()]
            results.append({"scenario": scenario, "question": question, **answer,
                            "missing": missing, "milliseconds": round((time.perf_counter()-start)*1000, 3)})
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer["answer"]}]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [row for row in results if row["missing"]]
    print(json.dumps({"turns": len(results), "failed": len(failed), "failures": [
        {"question": row["question"], "answer": row["answer"], "missing": row["missing"]} for row in failed
    ]}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(failed))


if __name__ == "__main__":
    main()
