# AURA — On-Device Hard Metrics (measured)

- Device serial: `EQEISSXW5XQKSGY5` (abi=arm64-v8a, Android 13)
- Package: `com.getnyx.aura.app/.MainActivity`
- Measured: 2026-07-07 16:06:21Z  (pid=30671)
- Tool: `tools/device_measure.sh`

| Metric | Measured | Hard target | Verdict |
|---|---|---|---|
| Detection latency (VAD triggered -> detected) | n/a ms | < 100 ms | PENDING |
| CPU (idle listening, top %CPU avg) | n/a % | < 5 % | PENDING |
| RAM (dumpsys meminfo TOTAL PSS) | 81.6 MB | < 20 MB | NO |
| Cold startup (am start -W TotalTime) | 2820 ms | < 1000 ms | NO |

Startup WaitTime (incl. system) = 2829 ms.

## Notes
- Verdict legend: **MET** = under target, **NO** = over target, **PENDING** = not captured.
- **Detection latency requires a real spoken "marvin"** — the mic cannot be
  injected over adb without an in-app test hook. Latency is the epoch-timestamp
  delta between the AURA `VAD triggered` log line and the matching
  `marvin detected`/`wake word CONFIRMED` line sharing the same `cid=`.
- CPU is toybox `top` %CPU (per-core-normalised), averaged over 5 samples.
- RAM is the `TOTAL PSS` summary row from `dumpsys meminfo` (KB converted to MB).
- Startup is a cold `am start -W` after `am force-stop`.
