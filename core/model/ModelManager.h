// PROJECT AURA — core/model/ModelManager.h
//
// One Model Manager instance per model slot (Stage 7 §3.13). Implements the hot-swap
// architecture from Stage 7 §5: mmap-load, double-buffered active/previous handles, an
// atomic-observed generation counter, 1-level rollback, and safe unmap of a retired
// mmap region only after the Inference thread has moved past the swap point (no
// use-after-unmap, no full-engine pause).
//
// Thread ownership: stage()/activate()/rollback() run on the OTA/Background thread; the
// Inference thread reads current()/brackets its work with beginInference()/endInference()
// (Stage 7 §6 allows a priority-inheritance mutex on the ModelManager handle).
#ifndef AURA_MODEL_MODELMANAGER_H
#define AURA_MODEL_MODELMANAGER_H

#include <atomic>
#include <vector>

#include "core/common/lockorder.h"
#include "core/model/IModelLoader.h"
#include "core/platform/IStorage.h"

namespace aura::model {

class ModelManager final : public IModelLoader {
 public:
  ModelManager(platform::IStorage& storage, common::ModelSlot slot)
      : storage_(storage), slot_(slot) {}
  ~ModelManager() override;

  // IModelLoader (Stage 7 §4). stage()+activate() == a hot-swap; rollback() reverts to
  // the immediately-previous model.
  common::Result<common::ModelHandle> stage(
      const std::filesystem::path& verifiedModelPath) override;
  common::Result<void> activate(const common::ModelHandle& staged) override;
  common::Result<void> rollback() override;
  common::ModelHandle current() const override;

  // Inference-thread bracket: pins the active generation so a concurrent swap cannot
  // unmap the region this inference is reading. Returns the generation being served.
  uint32_t beginInference();
  void endInference();

  uint32_t generation() const { return generation_.load(std::memory_order_acquire); }

 private:
  common::Result<void> verifySignature(const common::ModelHandle& handle);
  void tryUnmapRetired();  // caller holds mu_
  void retire(const platform::MappedRegion& region);  // caller holds mu_

  platform::IStorage& storage_;
  common::ModelSlot slot_;

  // ModelManager handle lock — level 2 in the global hierarchy (Stage 7 §6).
  mutable common::OrderedMutex mu_{common::LockLevel::kModelHandle};
  std::atomic<uint32_t> generation_{0};
  std::atomic<int> inFlight_{0};

  common::ModelHandle active_{};
  common::ModelHandle previous_{};   // rollback target (one level)
  platform::MappedRegion activeRegion_{};
  platform::MappedRegion previousRegion_{};
  platform::MappedRegion stagedRegion_{};  // valid between stage() and activate()
  std::vector<platform::MappedRegion> retired_;  // pending unmap once no inference in flight
};

}  // namespace aura::model

#endif  // AURA_MODEL_MODELMANAGER_H
