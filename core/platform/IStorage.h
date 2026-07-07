// PROJECT AURA — core/platform/IStorage.h
//
// Responsibilities : filesystem gateway — read-only memory mapping of model files
//                    and path resolution (Stage 7 §3.1 public API: IStorage;
//                    §3.13: core/model depends on platform/IStorage for mmap).
// Dependencies     : none within core/ (Row 0).
// Thread ownership : mapping/unmapping happens on the OTA/startup thread, never the
//                    Audio/Inference hot path.
// Memory ownership : hands back a MappedRegion; the caller (core/model) owns the
//                    region's lifetime and must return it via unmap().
// Lifecycle        : one instance for the engine lifetime, owned by IPlatform.
//
// NOTE: field-level shape of IStorage is our design (Stage 7 §4 names IStorage but
// does not define it) — flagged in REPORT.md.
#ifndef AURA_PLATFORM_ISTORAGE_H
#define AURA_PLATFORM_ISTORAGE_H

#include <cstddef>
#include <filesystem>

#include "core/common/result.h"

namespace aura::platform {

// A read-only memory-mapped file region. `data` stays valid until unmap().
struct MappedRegion {
  const void* data = nullptr;
  size_t size = 0;
  void* opaque = nullptr;  // platform bookkeeping (fd / HANDLE / mapping ptr)
};

class IStorage {
 public:
  virtual ~IStorage() = default;

  // Base directory under which model assets are resolved (app files dir on
  // Android). Thread-safe, const.
  virtual std::filesystem::path baseDir() const = 0;

  // Memory-map a file read-only. Startup/OTA thread only. Returns kNotFound /
  // kIoError on failure (no exceptions).
  virtual common::Result<MappedRegion> mapReadOnly(const std::filesystem::path& path) = 0;

  // Release a region obtained from mapReadOnly. Safe to call with a zeroed region.
  virtual void unmap(const MappedRegion& region) = 0;
};

}  // namespace aura::platform

#endif  // AURA_PLATFORM_ISTORAGE_H
