#!/usr/bin/env bash
# PROJECT AURA — tools/device_measure.sh
# ---------------------------------------------------------------------------
# On-device measurement kit for the v1 "hard metrics" table.
#
#   Metric            Hard target   How this script measures it
#   ----------------  ------------  ------------------------------------------
#   Detection latency  < 100 ms     AURA logcat: delta between the "VAD triggered"
#                                   line and the matching "marvin detected"/CONFIRMED
#                                   line that share the same correlation id (cid).
#   CPU (idle listen)  < 5 %        `top -b -n1 -p <pid>` sampled over ~10 s, %CPU avg.
#   RAM                < 20 MB      `dumpsys meminfo <pid>` -> "TOTAL PSS" (KB->MB).
#   Cold startup       < 1 s        `am start -W` -> TotalTime / WaitTime (ms).
#
# Usage:   bash tools/device_measure.sh [SERIAL]
#          SERIAL defaults to EQEISSXW5XQKSGY5 (arm64, Android 13).
#
# Detection latency needs a REAL spoken utterance: the mic cannot be injected
# without an in-app test hook, so the script clears logcat, arms a watcher, and
# asks you to say the wake word ("marvin") out loud. It then correlates the
# resulting AURA log lines by cid and reports the ms delta.
#
# See DEVICE_RUNBOOK.md for the full provisioning/build procedure.
# ---------------------------------------------------------------------------
set -u

# ---- config ---------------------------------------------------------------
SERIAL="${1:-EQEISSXW5XQKSGY5}"
PKG="com.getnyx.aura.app"
ACT=".MainActivity"
APK="apps/android/build/outputs/apk/debug/android-debug.apk"
OUT="benchmarks/dashboards/device_metrics.md"

# Hard targets (numeric, used for MET/NO evaluation)
TGT_LATENCY_MS=100
TGT_CPU_PCT=5
TGT_RAM_MB=20
TGT_START_MS=1000

# Tunables
CPU_SAMPLES=5          # top iterations
CPU_INTERVAL=2         # seconds between samples (~10 s total)
LAT_WATCH_SECS=30      # how long to watch logcat for a spoken detection

ADB=(adb -s "$SERIAL")

# Resolve repo root (script lives in <root>/tools) so relative paths work from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "======================================================================"
echo " AURA on-device measurement kit"
echo "   serial : $SERIAL"
echo "   package: $PKG/$ACT"
echo "   apk    : $APK"
echo "   output : $OUT"
echo "======================================================================"

# ---- helpers --------------------------------------------------------------
die() { echo "FATAL: $*" >&2; exit 1; }

# Numeric "a < b" using awk (no bc dependency). Returns 0 (true) / 1 (false).
lt() { awk -v a="$1" -v b="$2" 'BEGIN{ exit !(a+0 < b+0) }'; }

# Evaluate a measured value vs target; echoes "MET" / "NO" / "PENDING".
verdict() {
  local val="$1" tgt="$2"
  if [ -z "$val" ] || [ "$val" = "n/a" ]; then echo "PENDING"; return; fi
  if lt "$val" "$tgt"; then echo "MET"; else echo "NO"; fi
}

get_pid() {
  # pidof is the most reliable; fall back to `ps` parsing on older toybox.
  local p
  p="$("${ADB[@]}" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  if [ -z "$p" ]; then
    p="$("${ADB[@]}" shell ps -A 2>/dev/null | tr -d '\r' | awk -v pkg="$PKG" '$NF==pkg{print $2; exit}')"
  fi
  echo "$p"
}

# ---- 0. device reachable --------------------------------------------------
echo
echo "[0/5] Checking device is online..."
STATE="$("${ADB[@]}" get-state 2>/dev/null | tr -d '\r' || true)"
[ "$STATE" = "device" ] || die "device $SERIAL not in 'device' state (got '${STATE:-none}'). Run: adb devices"
ABI="$("${ADB[@]}" shell getprop ro.product.cpu.abi 2>/dev/null | tr -d '\r')"
REL="$("${ADB[@]}" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')"
echo "      online — abi=$ABI android=$REL"

# ---- 1. install + grant + force-stop -------------------------------------
echo
echo "[1/5] Installing debug APK (force-stop first, then grant RECORD_AUDIO)..."
"${ADB[@]}" shell am force-stop "$PKG" 2>/dev/null || true
[ -f "$APK" ] || die "APK not found at $APK — build it first (./gradlew :apps:android:assembleDebug)"
"${ADB[@]}" install -r -g "$APK" || {
  echo "      -g (grant-all) install failed; retrying plain install + explicit grant"
  "${ADB[@]}" install -r "$APK" || die "adb install failed"
}
# Belt-and-suspenders: explicitly grant the runtime mic permission.
"${ADB[@]}" shell pm grant "$PKG" android.permission.RECORD_AUDIO 2>/dev/null || true
echo "      installed + RECORD_AUDIO granted"

# ---- 2. STARTUP (cold) ----------------------------------------------------
echo
echo "[2/5] Startup: am start -W (TotalTime / WaitTime)..."
"${ADB[@]}" shell am force-stop "$PKG" 2>/dev/null || true
START_OUT="$("${ADB[@]}" shell am start -W -n "$PKG/$ACT" 2>&1 | tr -d '\r')"
echo "$START_OUT" | sed 's/^/      | /'
TOTAL_MS="$(echo "$START_OUT" | awk -F: '/TotalTime/{gsub(/ /,"",$2); print $2; exit}')"
WAIT_MS="$(echo  "$START_OUT" | awk -F: '/WaitTime/ {gsub(/ /,"",$2); print $2; exit}')"
[ -n "${TOTAL_MS:-}" ] || TOTAL_MS="n/a"
[ -n "${WAIT_MS:-}"  ] || WAIT_MS="n/a"
echo "      TotalTime=${TOTAL_MS} ms  WaitTime=${WAIT_MS} ms"

# Give the engine a moment to spin up its audio/VAD threads before profiling.
sleep 3
PID="$(get_pid)"
[ -n "$PID" ] || die "could not resolve pid for $PKG — is the app running / did it crash?"
echo "      pid=$PID"

# ---- 3. RAM (TOTAL PSS) ---------------------------------------------------
echo
echo "[3/5] RAM: dumpsys meminfo $PID -> TOTAL PSS..."
MEMINFO="$("${ADB[@]}" shell dumpsys meminfo "$PID" 2>/dev/null | tr -d '\r')"
# Match the "TOTAL PSS" summary row (newer Android) or legacy "TOTAL" row; value is KB.
RAM_KB="$(echo "$MEMINFO" | awk '
  /TOTAL PSS:/ { for(i=1;i<=NF;i++) if($i=="PSS:"){print $(i+1); found=1; exit} }
  END { if(!found) exit }')"
if [ -z "${RAM_KB:-}" ]; then
  # Legacy layout: a line beginning with "TOTAL" whose first number column is PSS.
  RAM_KB="$(echo "$MEMINFO" | awk '/^[[:space:]]*TOTAL[[:space:]]/{print $2; exit}')"
fi
if [ -n "${RAM_KB:-}" ]; then
  RAM_MB="$(awk -v k="$RAM_KB" 'BEGIN{printf "%.1f", k/1024}')"
else
  RAM_MB="n/a"
fi
echo "      TOTAL PSS = ${RAM_KB:-?} KB  (${RAM_MB} MB)"

# ---- 4. CPU (top over ~10 s) ---------------------------------------------
echo
echo "[4/5] CPU: sampling top -b -n1 -p $PID x${CPU_SAMPLES} (~$((CPU_SAMPLES*CPU_INTERVAL)) s)..."
CPU_SUM=0; CPU_CNT=0
for i in $(seq 1 "$CPU_SAMPLES"); do
  # Toybox top columns: PID USER PR NI VIRT RES SHR S [%CPU] %MEM TIME+ ARGS.
  # Locate the %CPU column by parsing the header row, then read that column from the
  # process row — robust across toybox layouts where %CPU may carry a state prefix.
  RAW="$("${ADB[@]}" shell top -b -n 1 -p "$PID" 2>/dev/null | tr -d '\r')"
  CPU_ONE="$(echo "$RAW" | awk -v p="$PID" '
    /%CPU/ && col==0 { for(i=1;i<=NF;i++){ h=$i; gsub(/[^A-Za-z%]/,"",h); if(h=="%CPU"||h=="CPU%"||h=="[%CPU]"){col=i} } next }
    $1==p && col>0 { v=$col; gsub(/[^0-9.]/,"",v); print v; exit }')"
  if [ -n "${CPU_ONE:-}" ]; then
    CPU_SUM="$(awk -v s="$CPU_SUM" -v v="$CPU_ONE" 'BEGIN{printf "%.3f", s+v}')"
    CPU_CNT=$((CPU_CNT+1))
    echo "      sample $i: %CPU=${CPU_ONE}"
  else
    echo "      sample $i: (no row — process gone?)"
  fi
  [ "$i" -lt "$CPU_SAMPLES" ] && sleep "$CPU_INTERVAL"
done
if [ "$CPU_CNT" -gt 0 ]; then
  CPU_PCT="$(awk -v s="$CPU_SUM" -v n="$CPU_CNT" 'BEGIN{printf "%.1f", s/n}')"
else
  CPU_PCT="n/a"
fi
echo "      mean %CPU = ${CPU_PCT} (n=$CPU_CNT)   [note: toybox top %CPU is per-core-normalised]"

# ---- 5. DETECTION LATENCY (needs a spoken utterance) ---------------------
echo
echo "[5/5] Detection latency: clearing logcat, then WATCHING for a spoken wake word."
echo "      >>> ACTION REQUIRED: say the wake word (\"marvin\") clearly into the device mic."
echo "      >>> The mic cannot be injected from adb (no app test-hook), so a real"
echo "      >>> utterance is required. Watching AURA logs for up to ${LAT_WATCH_SECS}s..."
"${ADB[@]}" logcat -c 2>/dev/null || true

# Capture AURA logs with epoch timestamps (seconds.millis) so we can diff by cid.
LOGTMP="$(mktemp 2>/dev/null || echo "/tmp/aura_lat_$$.log")"
"${ADB[@]}" logcat -v epoch -s AURA:V > "$LOGTMP" 2>/dev/null &
LOGPID=$!
# Watch loop: stop early once we see a "marvin detected"/CONFIRMED line.
waited=0
while [ "$waited" -lt "$LAT_WATCH_SECS" ]; do
  if grep -qiE 'marvin detected|wake word CONFIRMED' "$LOGTMP" 2>/dev/null; then
    sleep 1  # let the matching lines flush
    break
  fi
  sleep 1
  waited=$((waited+1))
done
kill "$LOGPID" 2>/dev/null || true
wait "$LOGPID" 2>/dev/null || true

echo "      --- captured AURA lines ---"
sed 's/^/      | /' "$LOGTMP" 2>/dev/null | head -40

# Correlate by cid: for each detected/CONFIRMED line, find the earlier "VAD triggered"
# line with the same cid=<hex> and compute the epoch-timestamp delta in ms.
# Log line shape (tag AURA, -v epoch):  "  1712500000.123  <pid> <tid> D AURA : [vad] cid=a0da00001 VAD triggered"
LAT_MS="$(awk '
  # epoch ts is the first token on the line with -v epoch
  {
    ts=$1+0
    # extract cid=<hex> token
    cid=""
    if (match($0, /cid=[0-9a-fA-F]+/)) { cid=substr($0, RSTART+4, RLENGTH-4) }
  }
  /VAD triggered/ && cid!="" { vad[cid]=ts }
  (/marvin detected/ || /wake word CONFIRMED/) && cid!="" {
    if (cid in vad) {
      d=(ts - vad[cid])*1000.0
      if (d>=0 && (best=="" || d<best)) best=d
    }
  }
  END { if (best!="") printf "%.1f", best }
' "$LOGTMP" 2>/dev/null)"

if [ -n "${LAT_MS:-}" ]; then
  echo "      detection latency (VAD triggered -> detected, matched cid) = ${LAT_MS} ms"
else
  LAT_MS="n/a"
  echo "      NO correlated detection captured (no utterance spoken, or model did not fire)."
  echo "      Re-run and speak \"marvin\" during the ${LAT_WATCH_SECS}s window."
fi
rm -f "$LOGTMP" 2>/dev/null || true

# ---- verdicts -------------------------------------------------------------
V_LAT="$(verdict "$LAT_MS"  "$TGT_LATENCY_MS")"
V_CPU="$(verdict "$CPU_PCT" "$TGT_CPU_PCT")"
V_RAM="$(verdict "$RAM_MB"  "$TGT_RAM_MB")"
V_START="$(verdict "$TOTAL_MS" "$TGT_START_MS")"

# ---- write dashboard ------------------------------------------------------
mkdir -p "$(dirname "$OUT")"
NOW="$(date -u '+%Y-%m-%d %H:%M:%SZ' 2>/dev/null || echo 'unknown')"
{
  echo "# AURA — On-Device Hard Metrics (measured)"
  echo
  echo "- Device serial: \`$SERIAL\` (abi=${ABI:-?}, Android ${REL:-?})"
  echo "- Package: \`$PKG/$ACT\`"
  echo "- Measured: $NOW  (pid=$PID)"
  echo "- Tool: \`tools/device_measure.sh\`"
  echo
  echo "| Metric | Measured | Hard target | Verdict |"
  echo "|---|---|---|---|"
  echo "| Detection latency (VAD triggered -> detected) | ${LAT_MS} ms | < ${TGT_LATENCY_MS} ms | ${V_LAT} |"
  echo "| CPU (idle listening, top %CPU avg) | ${CPU_PCT} % | < ${TGT_CPU_PCT} % | ${V_CPU} |"
  echo "| RAM (dumpsys meminfo TOTAL PSS) | ${RAM_MB} MB | < ${TGT_RAM_MB} MB | ${V_RAM} |"
  echo "| Cold startup (am start -W TotalTime) | ${TOTAL_MS} ms | < ${TGT_START_MS} ms | ${V_START} |"
  echo
  echo "Startup WaitTime (incl. system) = ${WAIT_MS} ms."
  echo
  echo "## Notes"
  echo "- Verdict legend: **MET** = under target, **NO** = over target, **PENDING** = not captured."
  echo "- **Detection latency requires a real spoken \"marvin\"** — the mic cannot be"
  echo "  injected over adb without an in-app test hook. Latency is the epoch-timestamp"
  echo "  delta between the AURA \`VAD triggered\` log line and the matching"
  echo "  \`marvin detected\`/\`wake word CONFIRMED\` line sharing the same \`cid=\`."
  echo "- CPU is toybox \`top\` %CPU (per-core-normalised), averaged over ${CPU_SAMPLES} samples."
  echo "- RAM is the \`TOTAL PSS\` summary row from \`dumpsys meminfo\` (KB converted to MB)."
  echo "- Startup is a cold \`am start -W\` after \`am force-stop\`."
} > "$OUT"

echo
echo "======================================================================"
echo " Wrote $OUT"
echo "======================================================================"
cat "$OUT"
