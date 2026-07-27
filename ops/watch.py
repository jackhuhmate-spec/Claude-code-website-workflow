#!/usr/bin/env python3
"""
watch.py — the hourly reply agent. Runs continuously, checks the inbox every hour.

    ./ops/env.sh python3 ops/watch.py                 # draft only (safe)
    ./ops/env.sh python3 ops/watch.py --auto          # actually send replies
    ./ops/env.sh python3 ops/watch.py --interval 1800 # every 30 min

Runs in the foreground. To keep it alive on a server:
    nohup ./ops/env.sh python3 ops/watch.py --auto >> logs/watch.log 2>&1 &

Stops cleanly on Ctrl-C. Honours the PAUSED kill switch between cycles.
A crash in one cycle never kills the loop — it logs and waits for the next hour.
"""
import argparse, signal, subprocess, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RUNNER = [sys.executable, str(HERE / "ops" / "run_cycle.py")]
PAUSED = HERE / "PAUSED"

_stop = False


def _sig(sig, frm):
    global _stop
    _stop = True
    print("\n[watch] stop signal received, finishing current cycle…", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=3600, help="Seconds between checks (default 3600).")
    ap.add_argument("--auto", action="store_true", help="Send replies instead of drafting.")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--once", action="store_true", help="Run a single cycle and exit.")
    a = ap.parse_args()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    mode = "AUTO-SEND" if a.auto else "DRAFT-ONLY"
    print(f"[watch] started {datetime.now():%Y-%m-%d %H:%M} | mode={mode} | every {a.interval}s", flush=True)

    n = 0
    while not _stop:
        n += 1
        ts = f"{datetime.now():%Y-%m-%d %H:%M}"
        if PAUSED.exists():
            print(f"[watch] {ts} cycle {n}: PAUSED — skipping", flush=True)
        else:
            cmd = RUNNER + ["replies", "--days", str(a.days)] + (["--auto"] if a.auto else [])
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                print(r.stdout, flush=True)
                if r.returncode != 0:
                    print(f"[watch] cycle {n} exited {r.returncode}: {r.stderr[:400]}", flush=True)
            except subprocess.TimeoutExpired:
                print(f"[watch] {ts} cycle {n}: TIMEOUT after 15min — will retry next interval", flush=True)
            except Exception as e:
                print(f"[watch] {ts} cycle {n}: ERROR {type(e).__name__}: {e}", flush=True)

        if a.once or _stop:
            break
        # sleep in 5s slices so Ctrl-C responds fast
        waited = 0
        while waited < a.interval and not _stop:
            time.sleep(min(5, a.interval - waited))
            waited += 5

    print(f"[watch] stopped after {n} cycle(s).", flush=True)


if __name__ == "__main__":
    main()
