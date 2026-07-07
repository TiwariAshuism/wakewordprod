// PROJECT AURA — core/common/tensor.h
//
// Responsibilities : TensorView, Arena (per-inference bump allocator), ModelHandle,
//                    BackendStats, BackendKind (Stage 7 §4/§5).
// Dependencies     : core/common/aligned_alloc.h.
// Thread ownership : Arena is single-threaded (one per IInferenceBackend instance,
//                    Inference thread). TensorView is a non-owning view.
// Memory ownership : Arena owns one pre-allocated aligned block; allocate() bumps a
//                    pointer and NEVER calls the system allocator (Stage 7 §5:
//                    "reset (not freed) after each call — zero heap allocation on
//                    the hot path"). ModelHandle references an mmap'd region owned
//                    by core/model/.
#ifndef AURA_COMMON_TENSOR_H
#define AURA_COMMON_TENSOR_H

#include <array>
#include <cstddef>
#include <cstdint>

#include "core/common/aligned_alloc.h"

namespace aura::common {

inline constexpr int kMaxTensorRank = 4;

// Non-owning, row-major float tensor view. Points at arena / feature-slot memory.
struct TensorView {
  float* data = nullptr;
  std::array<int64_t, kMaxTensorRank> shape{0, 0, 0, 0};
  int rank = 0;

  constexpr int64_t elementCount() const {
    int64_t n = rank > 0 ? 1 : 0;
    for (int i = 0; i < rank; ++i) n *= shape[i];
    return n;
  }
};

// Bump allocator. Construct once at model-load time (sized from the model
// manifest, Stage 7 §5); reset() at the top of every infer() call. allocate() is
// hot-path safe: no system allocator, no locks.
class Arena {
 public:
  Arena() = default;
  explicit Arena(size_t capacityBytes) { reserve(capacityBytes); }
  ~Arena() { AlignedFree(base_); }

  Arena(const Arena&) = delete;
  Arena& operator=(const Arena&) = delete;

  // Startup only (allocates). Safe to call once before entering the hot path.
  void reserve(size_t capacityBytes) {
    AlignedFree(base_);
    base_ = static_cast<uint8_t*>(AlignedAlloc(capacityBytes, kTensorAlignmentBytes));
    capacity_ = base_ ? capacityBytes : 0;
    offset_ = 0;
  }

  // Hot-path: returns 64-byte-aligned scratch or nullptr if exhausted. Never
  // grows (Stage 7 §5: no dynamic growth on the hot path).
  void* allocate(size_t bytes) {
    const size_t aligned = ((offset_ + kTensorAlignmentBytes - 1) / kTensorAlignmentBytes) *
                           kTensorAlignmentBytes;
    if (aligned + bytes > capacity_) return nullptr;
    void* p = base_ + aligned;
    offset_ = aligned + bytes;
    if (offset_ > highWater_) highWater_ = offset_;
    return p;
  }

  float* allocateFloats(size_t count) { return static_cast<float*>(allocate(count * sizeof(float))); }

  // Called at infer() entry — resets the bump pointer, keeps the buffer.
  void reset() { offset_ = 0; }

  size_t capacity() const { return capacity_; }
  size_t highWater() const { return highWater_; }

 private:
  uint8_t* base_ = nullptr;
  size_t capacity_ = 0;
  size_t offset_ = 0;
  size_t highWater_ = 0;
};

// Identifies which model slot a handle serves.
enum class ModelSlot : uint8_t { kStage1 = 0, kStage2, kSpeaker, kVad };

// A loaded (mmap'd) model. Owned by core/model/; passed by const-ref to
// IInferenceBackend::loadModel. `generation` supports the hot-swap unmap timing
// (Stage 7 §5) — always 0 in v0 (single load-at-startup, no hot-swap).
struct ModelHandle {
  const void* data = nullptr;   // mmap base (or file bytes)
  size_t size = 0;
  ModelSlot slot = ModelSlot::kStage1;
  uint32_t generation = 0;
  bool valid() const { return data != nullptr && size > 0; }
};

enum class BackendKind : uint8_t { kOnnxRuntime = 0, kTfliteMicro, kExecuTorch, kFake };

// Per-backend latency accounting feeding wake.latency.stage1 (Stage 7 §13).
struct BackendStats {
  uint64_t lastInferenceNanos = 0;
  uint64_t inferenceCount = 0;
};

}  // namespace aura::common

#endif  // AURA_COMMON_TENSOR_H
