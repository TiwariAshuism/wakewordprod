// PROJECT AURA — core/features/FeatureFrame.h
// One log-Mel feature frame + its VAD speech flag: the ring-buffer slot for
// Stage 7 §5 pool #2 (audio -> inference handoff). POD; filled in place.
#ifndef AURA_FEATURES_FEATUREFRAME_H
#define AURA_FEATURES_FEATUREFRAME_H

#include <cstddef>
#include <cstdint>

namespace aura::features {

inline constexpr int kMaxMels = 64;

struct FeatureFrame {
  float mel[kMaxMels];
  int nMels = 0;
  bool speech = false;          // VAD gate for this frame (Stage 7 §3.9)
  uint64_t captureTimestampNanos = 0;
};

}  // namespace aura::features

#endif  // AURA_FEATURES_FEATUREFRAME_H
