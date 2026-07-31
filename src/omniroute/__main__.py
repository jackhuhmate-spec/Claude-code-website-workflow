"""
Omniroute CLI — python -m omniroute

Usage:
    python -m omniroute status          Pipeline snapshot
    python -m omniroute leads list      List leads
    python -m omniroute outreach        Run outreach cycle
    python -m omniroute replies         Check and handle replies
"""

import sys


def main() -> int:
    from omniroute.cli.main import main as cli_main

    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
