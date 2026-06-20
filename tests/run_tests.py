"""Zero-dependency test runner.

Discovers every `test_*` function in the tests/ package, runs each, and reports
pass/fail. Mirrors what pytest would collect, so the same files work under both.

    python3 tests/run_tests.py
"""
from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    test_files = sorted(p for p in TESTS_DIR.glob("test_*.py"))
    passed = failed = 0
    failures: list[str] = []

    for path in test_files:
        module = _load_module(path)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            func = getattr(module, name)
            if not callable(func):
                continue
            try:
                func()
            except Exception:
                failed += 1
                failures.append(f"{path.name}::{name}\n{traceback.format_exc()}")
                print(f"FAIL  {path.name}::{name}")
            else:
                passed += 1
                print(f"ok    {path.name}::{name}")

    print(f"\n{passed} passed, {failed} failed")
    if failures:
        print("\n" + "=" * 70)
        for f in failures:
            print(f + "-" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
