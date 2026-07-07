// PROJECT AURA — core/model/ModelManager.cpp
#include "core/model/ModelManager.h"

#include <utility>

namespace aura::model {

using common::Err;
using common::ErrorCode;
using common::ModelHandle;
using common::Result;

ModelManager::~ModelManager() {
  common::OrderedLock lock(mu_);
  for (auto& r : retired_) storage_.unmap(r);
  retired_.clear();
  if (previousRegion_.data) storage_.unmap(previousRegion_);
  if (activeRegion_.data) storage_.unmap(activeRegion_);
  if (stagedRegion_.data) storage_.unmap(stagedRegion_);
}

Result<void> ModelManager::verifySignature(const ModelHandle& /*handle*/) {
  // v0: SIGNATURE VERIFICATION SKIPPED (Stage 7 scope — flagged). The full build routes
  // this through core/security against a signed manifest (addendum §6).
  return {};
}

Result<ModelHandle> ModelManager::stage(const std::filesystem::path& verifiedModelPath) {
  auto mapped = storage_.mapReadOnly(verifiedModelPath);
  if (!mapped) return mapped.error();

  common::OrderedLock lock(mu_);
  // A previous stage() that was never activated leaks its region — release it first.
  if (stagedRegion_.data) storage_.unmap(stagedRegion_);
  stagedRegion_ = mapped.value();

  ModelHandle handle{};
  handle.data = stagedRegion_.data;
  handle.size = stagedRegion_.size;
  handle.slot = slot_;
  handle.generation = generation_.load(std::memory_order_relaxed) + 1;

  auto verified = verifySignature(handle);
  if (!verified) {
    storage_.unmap(stagedRegion_);
    stagedRegion_ = {};
    return verified.error();
  }
  return handle;
}

Result<void> ModelManager::activate(const ModelHandle& staged) {
  if (!staged.valid()) return Err(ErrorCode::kInvalidArgument, "activate: invalid handle");
  common::OrderedLock lock(mu_);
  if (staged.data != stagedRegion_.data) {
    return Err(ErrorCode::kFailedPrecondition, "activate: handle was not staged here");
  }
  // Shift the buffers: active -> previous (rollback target), staged -> active. The old
  // previous (two versions back) is retired for unmap once inference has moved past it.
  if (previousRegion_.data) retire(previousRegion_);
  previous_ = active_;
  previousRegion_ = activeRegion_;
  active_ = staged;
  activeRegion_ = stagedRegion_;
  stagedRegion_ = {};
  generation_.fetch_add(1, std::memory_order_acq_rel);  // atomic publish (Stage 7 §5)
  tryUnmapRetired();
  return {};
}

Result<void> ModelManager::rollback() {
  common::OrderedLock lock(mu_);
  if (!previous_.valid()) return Err(ErrorCode::kFailedPrecondition, "rollback: no previous model");
  // Revert to the previous model; the (bad) current active is retired.
  retire(activeRegion_);
  active_ = previous_;
  activeRegion_ = previousRegion_;
  previous_ = {};
  previousRegion_ = {};
  generation_.fetch_add(1, std::memory_order_acq_rel);
  tryUnmapRetired();
  return {};
}

ModelHandle ModelManager::current() const {
  common::OrderedLock lock(mu_);
  return active_;
}

uint32_t ModelManager::beginInference() {
  inFlight_.fetch_add(1, std::memory_order_acq_rel);
  return generation_.load(std::memory_order_acquire);
}

void ModelManager::endInference() {
  if (inFlight_.fetch_sub(1, std::memory_order_acq_rel) == 1) {
    // Last in-flight inference finished — retired regions are now safe to unmap.
    common::OrderedLock lock(mu_);
    tryUnmapRetired();
  }
}

void ModelManager::retire(const platform::MappedRegion& region) {
  if (region.data) retired_.push_back(region);
}

void ModelManager::tryUnmapRetired() {
  // Safe only when no inference is currently reading a model region (generation-past
  // condition, Stage 7 §5). Conservative but race-free.
  if (inFlight_.load(std::memory_order_acquire) != 0) return;
  for (auto& r : retired_) storage_.unmap(r);
  retired_.clear();
}

}  // namespace aura::model
