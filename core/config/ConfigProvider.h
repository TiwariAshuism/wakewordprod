// PROJECT AURA — core/config/ConfigProvider.h
//
// Full IConfigProvider (Stage 7 §3.2/§9): resolves a Config snapshot by precedence —
// compiled-in defaults -> platform overlay -> runtime overrides (highest) — and
// publishes an immutable snapshot on every change, notifying registered handlers.
// Readers hold a shared_ptr<const Config>, so an update never invalidates an in-flight
// reader. The publish is guarded by the Config-publish lock (level 3, Stage 7 §6).
//
// (DefaultConfigProvider remains for the compiled-in-only path; this adds the overlay +
// runtime-override + change-notification behavior the spec requires.)
#ifndef AURA_CONFIG_CONFIGPROVIDER_H
#define AURA_CONFIG_CONFIGPROVIDER_H

#include <functional>
#include <memory>
#include <utility>
#include <vector>

#include "core/common/lockorder.h"
#include "core/config/IConfigProvider.h"

namespace aura::config {

class ConfigProvider final : public IConfigProvider {
 public:
  using OverlayFn = std::function<void(Config&)>;    // platform overlay (Stage 7 §9)
  using OverrideFn = std::function<void(Config&)>;   // runtime/remote override
  using ChangeHandler = std::function<void(std::shared_ptr<const Config>)>;

  explicit ConfigProvider(Config defaults = {}, OverlayFn platformOverlay = {})
      : defaults_(std::move(defaults)), overlay_(std::move(platformOverlay)) {
    rebuildAndPublish(/*notify=*/false);
  }

  std::shared_ptr<const Config> current() const override {
    common::OrderedLock lock(mu_);
    return snapshot_;
  }

  void onConfigChanged(ChangeHandler handler) override {
    common::OrderedLock lock(mu_);
    handlers_.push_back(std::move(handler));
  }

  // Apply a runtime/remote override (highest precedence). Rebuilds the snapshot from
  // defaults -> overlay -> all accumulated overrides and publishes it. Runs on the
  // Background thread in production (Stage 7 §3.2).
  void applyOverride(OverrideFn override) {
    common::OrderedLock lock(mu_);
    overrides_.push_back(std::move(override));
    rebuildLocked();
    notifyLocked();
  }

 private:
  void rebuildAndPublish(bool notify) {
    common::OrderedLock lock(mu_);
    rebuildLocked();
    if (notify) notifyLocked();
  }
  void rebuildLocked() {
    Config c = defaults_;
    if (overlay_) overlay_(c);
    for (auto& o : overrides_) o(c);
    snapshot_ = std::make_shared<const Config>(std::move(c));
  }
  void notifyLocked() {
    auto snap = snapshot_;
    for (auto& h : handlers_) h(snap);
  }

  Config defaults_;
  OverlayFn overlay_;
  std::vector<OverrideFn> overrides_;
  std::vector<ChangeHandler> handlers_;
  std::shared_ptr<const Config> snapshot_;
  // Config snapshot publish lock — level 3 (Stage 7 §6).
  mutable common::OrderedMutex mu_{common::LockLevel::kConfigPublish};
};

}  // namespace aura::config

#endif  // AURA_CONFIG_CONFIGPROVIDER_H
