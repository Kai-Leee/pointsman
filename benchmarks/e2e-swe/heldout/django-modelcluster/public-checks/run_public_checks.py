#!/usr/bin/env python3
"""Held-out public checks: cases in cases.py, authored from the task's public instruction.md only.

Usage: run_public_checks.py --list | --suite <suite> --binding <binding.json> [--only-test-id <id> ...]
"""
import harness

if __name__ == "__main__":
    raise SystemExit(harness.main())
