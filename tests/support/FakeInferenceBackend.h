// PROJECT AURA — tests/support/FakeInferenceBackend.h
//
// Deterministic IInferenceBackend test double. The real ONNX Runtime backend is
// exercised on-device (acceptance #2); the host golden test uses this fake because
// ORT output is not guaranteed bit-reproducible across builds (Stage 7 §14
// determinism), whereas the whole point of a golden fixture is exact reproducibility.
//
// Scoring: emits `numClasses` logits; the target class logit is high when the mean
// of the input log-Mel window exceeds `gate` (i.e. energetic speech/keyword region),
// low otherwise. Softmax in the detector then yields ~1.0 vs ~0.0.
#ifndef AURA_TESTS_SUPPORT_FAKEINFERENCEBACKEND_H
#define AURA_TESTS_SUPPORT_FAKEINFERENCEBACKEND_H

#include <vector>

#include "core/runtime/IInferenceBackend.h"

namespace aura::test
{

  class FakeInferenceBackend final : public runtime::IInferenceBackend
  {
  public:
    FakeInferenceBackend(int numClasses, int targetClass, float gate)
        : numClasses_(numClasses), targetClass_(targetClass), gate_(gate) {}

    common::Result<void> loadModel(const common::ModelHandle &) override { return {}; }

    common::Result<common::TensorView> infer(const common::TensorView &input,
                                             common::Arena &scratchArena) override
    {
      const int64_t n = input.elementCount();
      // Use the MAX log-Mel value over the window: robustly separates any window
      // containing the energetic keyword burst from all-silence windows (far less
      // sensitive to the silence/burst ratio than a mean would be).
      float peak = -1e30f;
      for (int64_t i = 0; i < n; ++i)
        if (input.data[i] > peak) peak = input.data[i];

      float *out = scratchArena.allocateFloats(static_cast<size_t>(numClasses_));
      for (int c = 0; c < numClasses_; ++c)
        out[c] = 0.0f;
      out[targetClass_] = (peak > gate_) ? 10.0f : -10.0f;

      stats_.inferenceCount++;
      common::TensorView v;
      v.data = out;
      v.rank = 1;
      v.shape[0] = numClasses_;
      return v;
    }

    common::BackendStats stats() const override { return stats_; }
    common::BackendKind kind() const override { return common::BackendKind::kFake; }

  private:
    int numClasses_;
    int targetClass_;
    float gate_;
    common::BackendStats stats_{};
  };

} // namespace aura::test

#endif // AURA_TESTS_SUPPORT_FAKEINFERENCEBACKEND_H
