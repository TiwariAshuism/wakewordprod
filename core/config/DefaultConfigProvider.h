// PROJECT AURA — core/config/DefaultConfigProvider.h
//
// Compiled-in-defaults IConfigProvider (Stage 7 §9 lowest-precedence source).
// v0 has no remote config / on-device overrides, so the snapshot is fixed at
// construction; onConfigChanged is accepted but never fires (flagged in REPORT.md).
#ifndef AURA_CONFIG_DEFAULTCONFIGPROVIDER_H
#define AURA_CONFIG_DEFAULTCONFIGPROVIDER_H

#include <memory>
#include <utility>

#include "core/config/IConfigProvider.h"

namespace aura::config {

class DefaultConfigProvider final : public IConfigProvider {
 public:
  DefaultConfigProvider() : snapshot_(std::make_shared<const Config>(Config{})) {}
  explicit DefaultConfigProvider(Config cfg)
      : snapshot_(std::make_shared<const Config>(std::move(cfg))) {}

  std::shared_ptr<const Config> current() const override { return snapshot_; }

  void onConfigChanged(std::function<void(std::shared_ptr<const Config>)>) override {
    // No-op in v0: compiled-in defaults never change at runtime.
  }

 private:
  std::shared_ptr<const Config> snapshot_;
};

}  // namespace aura::config

#endif  // AURA_CONFIG_DEFAULTCONFIGPROVIDER_H
