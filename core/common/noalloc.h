// PROJECT AURA — core/common/noalloc.h
//
// Responsibilities : Debug-build assertion that no heap allocation occurs on the
//                    Audio/Inference hot path after startup (Stage 7 §5/§6:
//                    "a debug-build assertion catching a mid-pipeline malloc/new").
// Dependencies     : none (foundation).
// Thread ownership : the guard sets a thread_local flag; the operator-new override
//                    (noalloc.cpp) aborts if new/malloc fires while the flag is set.
// Build gate       : active only when AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION is
//                    defined (debug/CI builds); compiled out of release (Stage 7 §9).
//
// LIMITATION (flagged in REPORT.md): this guard covers *our* code. Third-party
// libraries invoked inside the guarded region (notably ONNX Runtime inside
// Silero VAD / Stage-1 inference) may allocate internally; those allocations are
// outside this instrumentation and are a known v0 gap.
#ifndef AURA_COMMON_NOALLOC_H
#define AURA_COMMON_NOALLOC_H

namespace aura::common {

#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)

// Incremented while a no-alloc region is active on the current thread.
extern thread_local int g_noAllocDepth;

// RAII scope. Wrap the per-frame hot path (DSP/features/handoff, per-inference
// body) in one of these; any new/malloc inside aborts the debug build.
class ScopedNoAllocGuard {
 public:
  ScopedNoAllocGuard() { ++g_noAllocDepth; }
  ~ScopedNoAllocGuard() { --g_noAllocDepth; }
  ScopedNoAllocGuard(const ScopedNoAllocGuard&) = delete;
  ScopedNoAllocGuard& operator=(const ScopedNoAllocGuard&) = delete;
};

// Escape hatch for the rare, deliberate allocation inside a guarded scope that we
// have consciously accepted (e.g. wrapping a third-party call we cannot change).
class ScopedAllowAllocGuard {
 public:
  ScopedAllowAllocGuard() : saved_(g_noAllocDepth) { g_noAllocDepth = 0; }
  ~ScopedAllowAllocGuard() { g_noAllocDepth = saved_; }
 private:
  int saved_;
};

#else  // instrumentation compiled out

class ScopedNoAllocGuard {
 public:
  ScopedNoAllocGuard() = default;
};
class ScopedAllowAllocGuard {
 public:
  ScopedAllowAllocGuard() = default;
};

#endif

}  // namespace aura::common

#endif  // AURA_COMMON_NOALLOC_H
