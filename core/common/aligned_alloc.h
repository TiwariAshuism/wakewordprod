// PROJECT AURA — core/common/aligned_alloc.h
//
// Responsibilities : 64-byte aligned allocation wrapper (Stage 7 §5: all
//                    tensor/ring-buffer allocations are cache-line/SIMD aligned,
//                    "never raw new/malloc"). Startup-only; NOT called on the hot
//                    path after initialize().
// Dependencies     : none (foundation).
// Thread ownership : call only on Background/startup threads.
#ifndef AURA_COMMON_ALIGNED_ALLOC_H
#define AURA_COMMON_ALIGNED_ALLOC_H

#include <cstddef>
#include <cstdlib>
#include <new>

namespace aura::common
{

  inline constexpr size_t kCacheLineBytes = 64; // Stage 7 §5 alignment
  inline constexpr size_t kTensorAlignmentBytes = 64;

  // Allocate `bytes` aligned to `alignment` (default 64). Returns nullptr on
  // failure (no exceptions). Free with AlignedFree.
  inline void *AlignedAlloc(size_t bytes, size_t alignment = kTensorAlignmentBytes)
  {
    if (bytes == 0)
      bytes = alignment;
    // Round size up to a multiple of alignment (required by std::aligned_alloc /
    // some platforms).
    const size_t rounded = ((bytes + alignment - 1) / alignment) * alignment;
#if defined(_WIN32)
    return _aligned_malloc(rounded, alignment);
#else
    // NOT std::aligned_alloc: it is absent from Android's libc below API 28 (minSdk 26),
    // which makes libc++'s `using ::aligned_alloc` unresolved. posix_memalign is available
    // on every Android API level (and POSIX). alignment (64) is a power of two and a
    // multiple of sizeof(void*), as posix_memalign requires.
    void *p = nullptr;
    if (::posix_memalign(&p, alignment, rounded) != 0)
      return nullptr;
    return p;
#endif
  }

  inline void AlignedFree(void *p) noexcept
  {
#if defined(_WIN32)
    _aligned_free(p);
#else
    std::free(p);
#endif
  }

} // namespace aura::common

#endif // AURA_COMMON_ALIGNED_ALLOC_H
