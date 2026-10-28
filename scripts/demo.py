"""Run the installed CLI on synthetic data and verify its trusted receipt."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(arguments, expected=0):
    result = subprocess.run(
        [sys.executable, "-m", "guardrail_agent", *arguments],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(result.stdout, end="")
    if result.returncode != expected:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"unexpected exit code: {result.returncode}; expected {expected}")


def main():
    print("Synthetic demonstration: proposer → rules → simulated execution → receipt")
    with tempfile.TemporaryDirectory(prefix="guardrail-demo-") as directory:
        root = Path(directory)
        audit, receipt, report = (
            root / name for name in ("audit.json", "receipt.json", "report.html")
        )
        run(
            [
                "--days",
                "30",
                "--seed",
                "7",
                "--agent",
                "chaotic",
                "--json",
                str(audit),
                "--receipt-out",
                str(receipt),
                "--html",
                str(report),
            ]
        )
        print("Verify with the independently held, original receipt:")
        run(["--verify", str(audit), "--receipt", str(receipt)])
        document = json.loads(audit.read_text())
        if not document["records"]:
            raise SystemExit("fixture unexpectedly produced no audit records")
        document["records"].pop()
        audit.write_text(json.dumps(document))
        print("Remove a record; the original receipt must reject the altered document:")
        run(["--verify", str(audit), "--receipt", str(receipt)], expected=1)
    print("Demo completed. No real orders, model calls, or network requests.")


if __name__ == "__main__":
    main()
