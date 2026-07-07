# Graph Report - C:\Users\Ashu\Documents\wakewordprod  (2026-07-07)

## Corpus Check
- 130 files · ~161,578 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 521 nodes · 796 edges · 75 communities detected
- Extraction: 67% EXTRACTED · 33% INFERRED · 0% AMBIGUOUS · INFERRED: 266 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]

## God Nodes (most connected - your core abstractions)
1. `join()` - 34 edges
2. `load()` - 18 edges
3. `main()` - 17 edges
4. `Err()` - 16 edges
5. `items()` - 15 edges
6. `run()` - 14 edges
7. `process()` - 12 edges
8. `main()` - 12 edges
9. `iter_clips()` - 12 edges
10. `main()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Err()` --calls--> `currentFormat()`  [INFERRED]
  C:\Users\Ashu\Documents\wakewordprod\core\common\result.h → C:\Users\Ashu\Documents\wakewordprod\core\platform\android\OboeAudioInput.cpp
- `main()` --calls--> `softmax_marvin()`  [INFERRED]
  C:\Users\Ashu\Documents\wakewordprod\tools\train_kws_model.py → C:\Users\Ashu\Documents\wakewordprod\tools\verify_kws_host.py
- `EnergyGate` --uses--> `Ambient + broad speech dominate; confusables sprinkled at realistic low frequenc`  [INFERRED]
  C:\Users\Ashu\Documents\wakewordprod\benchmarks\harness\bench_kws.py → C:\Users\Ashu\Documents\wakewordprod\tools\heym_eval.py
- `precompute()` --calls--> `run()`  [INFERRED]
  C:\Users\Ashu\Documents\wakewordprod\benchmarks\harness\bench_kws.py → C:\Users\Ashu\Documents\wakewordprod\core\scheduler\Scheduler.cpp
- `build_negative_stream()` --calls--> `load_background_noise()`  [INFERRED]
  C:\Users\Ashu\Documents\wakewordprod\benchmarks\harness\bench_kws.py → C:\Users\Ashu\Documents\wakewordprod\tools\aura_augment.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (24): audio(), AuraEngine, TEST(), buildEngine(), TEST(), feed(), android(), Err() (+16 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (29): main(), synth(), load_catalog(), load_versions_txt(), main(), main(), module_of(), eval_model() (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (28): augment(), load_background_noise(), make_rir(), _mix_noise(), Online SpecAugment on a single [T, n_mels] numpy log-Mel frame-stack (train only, Load the _background_noise_ clips (long float arrays) for mixing + a silence cla, Synthetic exponential-decay room impulse response (no external RIR corpus needed, A ~1 s low-level noise clip for the _silence_ class. (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (19): version(), makeFrame(), TEST(), infer(), loadModel(), monoNanos(), OnnxRuntimeBackend(), runtime() (+11 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (23): apply_dsp(), _hz_to_mel(), log_mel(), _mel_filterbank(), _mel_to_hz(), Streaming log-Mel (win 400 / hop 160, center=False). Returns [T, 40] float32., Block-streamed AGC -> AEC(no-op) -> NS, mirroring DspChain.cpp. Vectorized but, build_negative_stream() (+15 more)

### Community 5 - "Community 5"
Cohesion: 0.12
Nodes (24): CalibrationDataReader, build_qat_model(), eval_onnx(), export_float_onnx(), export_qat_int8(), fusion_list(), load_features(), main() (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (13): android(), mapReadOnly(), TEST(), TEST(), currentFormat(), start(), stop(), aura() (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.1
Nodes (16): TEST(), AudioPipeline(), audioThreadTick(), drainOnceForTest(), onCaptureFrame(), setFrameSink(), start(), stop() (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.16
Nodes (17): TEST(), applyOverride(), onConfigChanged(), config(), unmap(), TEST(), writeBytes(), activate() (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (8): _BCResBlock, BCResNet, build_model(), CNN, _DSBlock, DSCNN, _Norm, Folded (x-mean)/std over the 40 mel bins, then reshape to [B,1,F,T].

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (7): Depthwise-separable causal Conv1d over time (channels = features). Streamable vi, _selftest(), StreamCausalConv, StreamingKWS, main(), per_frame_macs(), Analytic MACs for ONE streaming frame (each conv emits 1 output column).     Con

### Community 11 - "Community 11"
Cohesion: 0.27
Nodes (10): fromHandle(), Java_com_getnyx_aura_bindings_NativeBindings_nativeAddWakeWord(), Java_com_getnyx_aura_bindings_NativeBindings_nativeCreate(), Java_com_getnyx_aura_bindings_NativeBindings_nativeDestroy(), Java_com_getnyx_aura_bindings_NativeBindings_nativeInitialize(), Java_com_getnyx_aura_bindings_NativeBindings_nativeSetListener(), Java_com_getnyx_aura_bindings_NativeBindings_nativeStart(), Java_com_getnyx_aura_bindings_NativeBindings_nativeStop() (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.17
Nodes (2): Callback, NativeBindings

### Community 13 - "Community 13"
Cohesion: 0.26
Nodes (11): analyze_macs(), conv_macs(), fmt_macs(), gemm_macs(), main(), make_stream(), measure_windowed(), A continuous audio stream through the real front-end -> [T, 40] mel. (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (6): baseCfg(), pushProb(), TEST(), fire(), mintCorrelationId(), pushFrame()

### Community 15 - "Community 15"
Cohesion: 0.33
Nodes (8): applyPriority(), joinAll(), ManagedThread(), Scheduler(), spawnLoop(), start(), stop(), stopAll()

### Community 16 - "Community 16"
Cohesion: 0.25
Nodes (2): SetLockOrderViolationHandler(), TEST()

### Community 17 - "Community 17"
Cohesion: 0.39
Nodes (6): buildMelFilterbank(), computeFrameFromWindow(), hzToMel(), LogMelExtractor(), melToHz(), process()

### Community 18 - "Community 18"
Cohesion: 0.29
Nodes (1): MainActivity

### Community 19 - "Community 19"
Cohesion: 0.33
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 0.7
Nodes (4): main(), make_real(), make_synthetic(), print_frontend()

### Community 21 - "Community 21"
Cohesion: 0.5
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 0.5
Nodes (2): CorrelationId, DetectionEvent

### Community 23 - "Community 23"
Cohesion: 0.67
Nodes (1): version()

### Community 24 - "Community 24"
Cohesion: 0.67
Nodes (0): 

### Community 25 - "Community 25"
Cohesion: 0.67
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 0.67
Nodes (0): 

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (0): 

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (0): 

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (0): 

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): onnxruntime static PTQ: per-channel QDQ INT8, calibrated on real training window

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Extract [N,100,40] features + labels for one subset, with per-class caps.

## Knowledge Gaps
- **32 isolated node(s):** `Compute, ONCE, the per-frame VAD gate and the marvin score at each hop window.`, `Sequential gate + M-of-N smoothing + refractory (faithful to Stage1Detector).`, `Continuous non-keyword audio: background noise + concatenated non-marvin words.`, `DetectionEvent`, `Load the _background_noise_ clips (long float arrays) for mixing + a silence cla` (+27 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 27`** (2 nodes): `IAudioPipeline.h`, `audio()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `PcmFrame.h`, `audio()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `Resampler.h`, `audio()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `common()`, `aligned_alloc.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `DeviceChangeKind()`, `audio_types.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `error.h`, `common()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `lockorder.h`, `LockLevel()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `log.h`, `LogCategory()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `noalloc.cpp`, `checkNoAlloc()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `noalloc.h`, `common()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `IConfigProvider.h`, `config()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `Stage1Detector.h`, `CascadeEvent()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `StreamingDetector.h`, `detect()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `IDspStage.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (2 nodes): `EngineTypes.h`, `engine()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (2 nodes): `IWakeWordEngine.h`, `engine()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (2 nodes): `FeatureFrame.h`, `features()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (2 nodes): `LogMelExtractor.h`, `features()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (2 nodes): `ModelManager.h`, `mu_()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (2 nodes): `IAudioInput.h`, `platform()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (2 nodes): `IClock.h`, `platform()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (2 nodes): `IPlatform.h`, `platform()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (2 nodes): `IPowerManager.h`, `PowerState()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (2 nodes): `IStorage.h`, `platform()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (2 nodes): `android()`, `AndroidClock.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (2 nodes): `android()`, `AndroidLog.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (2 nodes): `android()`, `AndroidPlatform.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (2 nodes): `android()`, `AndroidPowerManager.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (2 nodes): `IInferenceBackend.h`, `runtime()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `StreamingWindow.h`, `runtime()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (2 nodes): `IStateMachine.h`, `statemachine()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (2 nodes): `statemachine_test.cpp`, `TEST()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (2 nodes): `EnergyVad.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (2 nodes): `IVad.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (2 nodes): `VadGate.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (2 nodes): `FakeInferenceBackend.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (2 nodes): `SyntheticSpeech.h`, `aura()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Fft.h`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `microgtest_main.cpp`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `onnxruntime static PTQ: per-channel QDQ INT8, calibrated on real training window`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Extract [N,100,40] features + labels for one subset, with per-class caps.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `load()` connect `Community 1` to `Community 2`, `Community 4`, `Community 5`, `Community 8`, `Community 10`, `Community 13`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Why does `join()` connect `Community 1` to `Community 2`, `Community 4`, `Community 5`, `Community 7`, `Community 10`, `Community 13`, `Community 15`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **Why does `run()` connect `Community 1` to `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 13`, `Community 15`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Are the 31 inferred relationships involving `join()` (e.g. with `main()` and `stop()`) actually correct?**
  _`join()` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `load()` (e.g. with `main()` and `common()`) actually correct?**
  _`load()` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `main()` (e.g. with `find_root()` and `join()`) actually correct?**
  _`main()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Err()` (e.g. with `start()` and `TEST()`) actually correct?**
  _`Err()` has 15 INFERRED edges - model-reasoned connections that need verification._