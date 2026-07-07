# Multilingual Expansion Plan — "hey m" Wake Word

Scope: expand "hey m" beyond V1 English accents. All coverage claims below are
grounded in the accent/language tags actually present in the placed dataset
(`PYTHONPATH=tools python tools/heym_data.py`) and the product audit docs.

## Ground truth: what the placed dataset actually contains

Accent/language tags emitted by `tools/heym_data.py`:

| Tag | Train clips | Test clips | Roadmap role |
|-----|------------:|-----------:|--------------|
| en-IN | 1430 | 331 | V1 Indian English |
| hi-IN | 316 | 52 | V2 Hindi |
| ta-IN | 149 | 47 | V3 Tamil-English |
| te-IN | 182 | 32 | V3 Telugu-English |
| kn-IN | 129 | 21 | Bonus (Kannada — not in roadmap) |
| ml-IN | 36 | 0 | Bonus (Malayalam — not in roadmap) |
| real | 10 | 0 | real-device positives |
| prod | 790 | 0 | production-collected (untagged locale, assume en-IN-dominant) |

**Absent tags (hard gaps): `en-US`, `en-GB`, `en-AU`, `mr-IN` (Marathi), `bn-IN` (Bengali).**

## Coverage vs. gaps per roadmap version

**V1 — Indian / American / British / Australian English.**
- Covered: **en-IN only** (strong: 1430 train / 331 test, plus ~790 `prod`).
- Missing: **en-US, en-GB, en-AU are entirely ABSENT.** V1 as specified is *not*
  fully backed by data — it currently ships Indian English only. The three
  foreign accents need net-new collection or public fill-in before V1 can honestly
  claim them.

**V2 — +Hindi, +Hinglish.**
- Hindi (**hi-IN**): covered — 316 train / 52 test. Usable for a first model.
- Hinglish (code-switched Hindi-English): **no explicit `hinglish` tag exists.**
  Partially implied by overlapping en-IN + hi-IN speakers, but not measurable as
  its own slice. Treat Hinglish as *unverified* until tagged or collected.

**V3 — +Tamil / Telugu / Marathi / Bengali English.**
- Tamil (**ta-IN**): covered — 149 / 47.
- Telugu (**te-IN**): covered — 182 / 32.
- Marathi (**mr-IN**): **ABSENT — blocked.**
- Bengali (**bn-IN**): **ABSENT — blocked.**
- Bonus: kn-IN and ml-IN are already present though not in the roadmap — near-free
  additional locales, but ml-IN has **0 test clips** so it cannot yet be evaluated.

Net: V2-Hindi and V3-Tamil/Telugu are **partially unblocked today**; V1 foreign
accents, V2-Hinglish, and V3-Marathi/Bengali are **data-blocked**.

## Ship per-locale models or one multilingual model?

Recommend **one shared multilingual model** with per-locale evaluation slices, not
a fan-out of per-locale binaries. Rationale:
- "hey m" is the *same acoustic target* across locales; the variation is
  accent/phonotactics, which a shared model handles via mixed-locale training —
  this is exactly the cross-lingual-transfer bet flagged as an open KWS question in
  `product/aura_phase1_audit.md` §11 and `aura_investment_committee_report.md`.
- Per-locale binaries multiply the ship/OTA/registry surface (already a scope risk
  called out across the product docs) and fragment the low-volume locales further.
- Keep per-locale models in reserve **only** for a locale that measurably regresses
  the shared model (e.g. if adding en-US drags down en-IN FA/hr).
- Gate: because ml-IN/low-volume locales ride on transfer, treat "shared model is
  good enough per-locale" as a **measured exit criterion**, not an assumption.

## Volume-parity risk (the load-bearing caveat)

`product/aura_phase1_audit.md` §6 is explicit: Common Voice (and MSWC, which is
forced-aligned *from* Common Voice — see `aura_addendum_v4.md`) solves **coverage,
not volume parity**. Indic per-language volume is far below English, and *volume
parity is what drives per-language quality*. Our own tags show the same shape:
en-IN (1430) dwarfs hi-IN (316), te-IN (182), ta-IN (149), ml-IN (36).

Implications:
- Do **not** treat "we added the tag" as "we support the locale." A locale with
  ~150 positives will underperform en-IN and must be reported as such.
- Public data narrows coverage gaps but will not reach parity; the durable fix is
  **internal opt-in device telemetry** (per §6 / §17 and `aura_addendum_v4.md`).
  Multilingual expansion is explicitly **gated on the volume-parity finding** in
  the product roadmap (Phase 2c) — budget for collection, not just public scraping.

## Fill-in data sources (to unblock the ABSENT tags)

- **MSWC (Multilingual Spoken Words Corpus)** — highest priority; KWS-native,
  forced-aligned. Use for negatives/phonetic hard-negatives and to seed en-US/en-GB
  and Indic locales. Caveat: inherits Common Voice's volume disparity; verify
  current MLCommons license before commercial use.
- **Common Voice** — accent-tagged en clips give **en-US / en-GB / en-AU** for V1,
  and mr / bn for V3. Uneven quality; use for accent breadth, not volume parity.
- **FLEURS** — ~100-language read speech; small per-language volume, good for
  low-resource **mr-IN / bn-IN** bootstrap and eval, weak as a primary training set.
- Note: none of these contain the literal "hey m" positive — they fill
  **negatives, accent/phonetic coverage, and per-locale eval**, with "hey m"
  positives coming from targeted internal collection per absent locale.

## Per-locale FA/hr and hit-rate evaluation

- Report **false-accepts/hour (FA/hr) and hit-rate per accent tag**, never a single
  pooled number — pooled metrics hide the low-volume locales. This matches the
  fixture-metadata rule in `aura_stage9_handbook.md` (every fixture carries an
  accent/language tag for accent-balance analysis).
- **Blocked eval today:** `ml-IN` has 0 test clips and `mr-IN`/`bn-IN`/`en-US`/
  `en-GB`/`en-AU` have no clips at all — these locales cannot be measured until test
  data lands. A locale is not "shipped" until it has a populated eval slice.
- Build the **internal FA/hr benchmark corpus** from real multilingual media/TV
  audio (Phase 2a deliverable per §17) so FA/hr is measured on realistic negatives
  per locale, not just held-out positives.
- Add canary/shadow eval before any staged OTA rollout of a new multilingual model
  so a per-locale regression is caught pre-release.

## Sequencing

1. **V1 completion** — collect/fill en-US, en-GB, en-AU; today V1 = en-IN only.
2. **V2** — Hindi shippable now (evaluate first); explicitly tag & collect Hinglish.
3. **V3** — Tamil/Telugu evaluate now; **collect Marathi (mr-IN) and Bengali
   (bn-IN)** — both fully blocked. Populate ml-IN test set to unlock the bonus locale.
4. Throughout: single shared model, per-locale FA/hr gates, volume-parity tracked as
   a first-class risk with internal collection budgeted, not assumed away.
