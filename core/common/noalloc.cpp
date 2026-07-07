// PROJECT AURA — core/common/noalloc.cpp
//
// Debug-only global operator new/delete override that aborts if an allocation
// fires inside a ScopedNoAllocGuard region (Stage 7 §5/§6). Linked only when
// AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION is defined. Compiled out of release.
#include "core/common/noalloc.h"

#if defined(AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION)

#include <cstdio>
#include <cstdlib>
#include <new>

namespace aura::common {
thread_local int g_noAllocDepth = 0;
}  // namespace aura::common

namespace {
void checkNoAlloc() {
  if (aura::common::g_noAllocDepth > 0) {
    std::fprintf(stderr,
                 "[AURA][FATAL] heap allocation on the Audio/Inference hot path "
                 "(inside ScopedNoAllocGuard) — Stage 7 §5/§6 violation\n");
    std::abort();
  }
}
}  // namespace

void* operator new(std::size_t sz) {
  checkNoAlloc();
  if (sz == 0) sz = 1;
  void* p = std::malloc(sz);
  if (!p) throw std::bad_alloc();
  return p;
}
void* operator new[](std::size_t sz) { return ::operator new(sz); }

// Non-throwing overloads.
void* operator new(std::size_t sz, const std::nothrow_t&) noexcept {
  checkNoAlloc();
  return std::malloc(sz ? sz : 1);
}
void* operator new[](std::size_t sz, const std::nothrow_t& nt) noexcept {
  return ::operator new(sz, nt);
}

void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

#endif  // AURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION
