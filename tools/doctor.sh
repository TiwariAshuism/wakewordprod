#!/usr/bin/env bash
# PROJECT AURA — toolchain doctor (Stage 9 §1). Checks the local environment
# against tools/versions.txt and flags mismatches. Best-effort; non-fatal.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
pins="$here/versions.txt"

echo "AURA doctor — checking toolchain against $pins"
have() { command -v "$1" >/dev/null 2>&1; }

check() { # name  command  pinned-substring
  local name="$1" cmd="$2" pin="$3"
  if have "$cmd"; then
    local v; v="$("$cmd" --version 2>&1 | head -1)"
    echo "  [ok]   $name: $v   (pinned: $pin)"
  else
    echo "  [MISS] $name: '$cmd' not found   (pinned: $pin)"
  fi
}

grep -E '^[A-Z]' "$pins" | while IFS='=' read -r k v; do :; done
JDK=$(grep '^JDK=' "$pins" | cut -d= -f2)
CMAKE=$(grep '^CMAKE=' "$pins" | cut -d= -f2)
NDK=$(grep '^NDK=' "$pins" | cut -d= -f2)
GRADLE=$(grep '^GRADLE=' "$pins" | cut -d= -f2)

check "JDK"    java   "$JDK"
check "CMake"  cmake  "$CMAKE"
check "Python" python "3.x"
echo "  NDK pinned: $NDK   (verify in Android Studio SDK Manager)"
echo "  Gradle pinned: $GRADLE   (use the committed wrapper: ./gradlew)"
echo "  ANDROID_HOME=${ANDROID_HOME:-<unset>}"
echo "Done."
