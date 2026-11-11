#!/usr/bin/env python3
"""Run the existing engine in a persistent desktop execution session.

Uses the same JSON-RPC protocol, data store, approvals and account setup pages as
the registered plugin. It does not register tools or authorize accounts itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from server import main as serve


def main():
    previous = None
    # Interactive execution sessions otherwise echo the athlete's request JSON.
    if sys.stdin.isatty():
        import termios
        previous = termios.tcgetattr(sys.stdin.fileno())
        settings = termios.tcgetattr(sys.stdin.fileno())
        settings[3] &= ~(termios.ECHO | termios.ICANON)
        settings[6][termios.VMIN] = 1
        settings[6][termios.VTIME] = 0
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, settings)
    try:
        return serve()
    except KeyboardInterrupt:
        return 0
    finally:
        if previous is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, previous)


if __name__ == '__main__':
    sys.exit(main())
