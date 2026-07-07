#!/usr/bin/env python3
"""AURA dependency-graph linter (Stage 7 §2 / Stage 8 dependency-graph-linter).

Parses the `#include "core/<module>/..."` graph across core/ and enforces:
  1. Row ordering: a module may include only modules at or below its own row.
  2. No platform SDK headers (<jni.h>, <oboe/*>, <android/*>, <AudioToolbox/*>,
     ESP-IDF) outside core/platform/<os>/ — the rule that makes the PAL real.
  3. No cyclic dependencies between core modules.

This is a minimal but real implementation of the Stage-7 requirement that the row
rules be checked by tooling, not just discipline. Exit code != 0 on any violation
so CI (and the local pre-build CMake target) fails fast.

Usage: python tools/lint_deps.py [core_dir]   (default: ./core)
"""
import os
import re
import sys

# Row assignment per Stage 7 §2. `common` is the header-only foundation below
# Row 0 (a judgment call for the SAS's undefined value types — see REPORT.md).
ROWS = {
    "common": -1,
    "platform": 0, "config": 0,
    "scheduler": 1, "statemachine": 1, "security": 1,
    "audio": 2, "telemetry": 2, "model": 2, "power": 2,
    "dsp": 3, "ota": 3, "discovery": 3,
    "features": 4, "vad": 4,
    "runtime": 5,
    "detect": 6,
    "speaker": 7,
    "engine": 8,
}

# Platform SDK headers that may appear ONLY under core/platform/<os>/.
FORBIDDEN_SDK = re.compile(
    r'#\s*include\s*[<"]('
    r'jni\.h|android/[^">]+|oboe/[^">]+|AudioToolbox/[^">]+|AAudio/[^">]+|esp_[^">]+'
    r')[>"]'
)
INCLUDE_CORE = re.compile(r'#\s*include\s*"core/([A-Za-z0-9_]+)/')


def module_of(path_parts):
    # path_parts like ['core', 'platform', 'android', 'X.h'] -> 'platform'
    return path_parts[1] if len(path_parts) > 1 else None


def main():
    core_dir = sys.argv[1] if len(sys.argv) > 1 else "core"
    root = os.path.dirname(os.path.abspath(core_dir.rstrip("/\\")))
    violations = []
    edges = {}  # module -> set(modules it depends on)

    for dirpath, _dirs, files in os.walk(core_dir):
        for fn in files:
            if not fn.endswith((".h", ".hpp", ".cpp", ".cc")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            parts = rel.split("/")
            mod = module_of(parts)
            if mod not in ROWS:
                continue
            is_platform_impl = parts[:2] == ["core", "platform"] and len(parts) > 3
            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            # Rule 2: forbidden SDK headers outside platform/<os>/
            for m in FORBIDDEN_SDK.finditer(text):
                if not is_platform_impl:
                    violations.append(
                        f"{rel}: platform SDK header '{m.group(1)}' outside core/platform/<os>/ "
                        f"(Stage 7 §2)"
                    )

            # Rule 1: row ordering
            for m in INCLUDE_CORE.finditer(text):
                dep = m.group(1)
                if dep == mod or dep not in ROWS:
                    continue
                edges.setdefault(mod, set()).add(dep)
                if ROWS[dep] > ROWS[mod]:
                    violations.append(
                        f"{rel}: module '{mod}' (row {ROWS[mod]}) includes higher-row "
                        f"'{dep}' (row {ROWS[dep]}) (Stage 7 §2)"
                    )

    # Rule 3: cycles among modules
    WHITE, GREY, BLACK = 0, 1, 2
    color = {}

    def dfs(u, stack):
        color[u] = GREY
        for v in sorted(edges.get(u, ())):
            if color.get(v, WHITE) == GREY:
                cyc = " -> ".join(stack[stack.index(v):] + [v]) if v in stack else f"{u} -> {v}"
                violations.append(f"cyclic dependency: {cyc} (Stage 7 §2)")
            elif color.get(v, WHITE) == WHITE:
                dfs(v, stack + [v])
        color[u] = BLACK

    for mod in sorted(edges):
        if color.get(mod, WHITE) == WHITE:
            dfs(mod, [mod])

    if violations:
        print("AURA dependency-graph lint: FAIL")
        for v in sorted(set(violations)):
            print("  - " + v)
        return 1
    print("AURA dependency-graph lint: OK (row order, PAL isolation, no cycles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
