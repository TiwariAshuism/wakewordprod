// PROJECT AURA — core/config/IConfigProvider.h
//
// Responsibilities : publish the immutable Config snapshot (Stage 7 §3.2/§4).
// Dependencies     : core/common, core/config/Config.h (Row 0).
// Thread ownership : current() is callable from any thread; readers hold a
//                    shared_ptr<const Config> so a config update never invalidates
//                    an in-flight reader (Stage 7 §3.2).
#ifndef AURA_CONFIG_ICONFIGPROVIDER_H
#define AURA_CONFIG_ICONFIGPROVIDER_H

#include <functional>
#include <memory>

#include "core/config/Config.h"

namespace aura::config {

// Exact signature per Stage 7 §4.
class IConfigProvider {
 public:
  virtual ~IConfigProvider() = default;
  virtual std::shared_ptr<const Config> current() const = 0;
  virtual void onConfigChanged(std::function<void(std::shared_ptr<const Config>)> handler) = 0;
};

}  // namespace aura::config

#endif  // AURA_CONFIG_ICONFIGPROVIDER_H
