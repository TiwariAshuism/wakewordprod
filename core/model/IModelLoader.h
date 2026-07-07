// PROJECT AURA — core/model/IModelLoader.h
//
// Responsibilities : model lifecycle — mmap load + (in full form) hot-swap/eviction
//                    (Stage 7 §3.13/§5). v0 implements a single load-at-startup
//                    path only; hot-swap/rollback are NOT built (flagged).
// Dependencies     : core/platform/IStorage (Row 2). NOTE: the full spec also
//                    depends on core/security for signature verification, which is
//                    OUT OF SCOPE — model/ calls a local verifySignature() that is
//                    a documented no-op (Stage 7: signature check SKIPPED for v0).
// Thread ownership : load/swap on the OTA/startup thread; the (would-be) atomic
//                    pointer swap is the only cross-thread op. v0 loads before the
//                    Inference thread starts, so there is no live swap.
// Memory ownership : owns the mmap'd model regions (released on destruction).
#ifndef AURA_MODEL_IMODELLOADER_H
#define AURA_MODEL_IMODELLOADER_H

#include <filesystem>

#include "core/common/result.h"
#include "core/common/tensor.h"

namespace aura::model {

// Exact signature per Stage 7 §4.
class IModelLoader {
 public:
  virtual ~IModelLoader() = default;
  virtual common::Result<common::ModelHandle> stage(
      const std::filesystem::path& verifiedModelPath) = 0;
  virtual common::Result<void> activate(const common::ModelHandle& staged) = 0;
  virtual common::Result<void> rollback() = 0;
  virtual common::ModelHandle current() const = 0;
};

}  // namespace aura::model

#endif  // AURA_MODEL_IMODELLOADER_H
