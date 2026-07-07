// PROJECT AURA — core/platform/IPlatform.h
//
// Responsibilities : the Platform Abstraction Layer (PAL) — the sole gateway to OS
//                    primitives (audio I/O, clock, storage, power). This is the
//                    primary, load-bearing plugin point of the architecture
//                    (Stage 7 §3.1/§4/§10, ADR-PAL).
// Dependencies     : none within core/ (Row 0).
// Thread ownership : owns no core-engine thread; delivers the audio callback into
//                    threads owned by scheduler/.
// Memory ownership : owns the per-OS resource handles; owns no long-lived engine
//                    state.
// Lifecycle        : constructed once at startup, destroyed once at shutdown.
//
// HARD RULE (Stage 7 §2): this interface, and the platform/<os>/ implementations,
// are the ONLY place OS/SDK headers (<jni.h>, Oboe, AAudio, ...) may be included.
// No other core/ module may include them.
#ifndef AURA_PLATFORM_IPLATFORM_H
#define AURA_PLATFORM_IPLATFORM_H

#include "core/platform/IAudioInput.h"
#include "core/platform/IClock.h"
#include "core/platform/IPowerManager.h"
#include "core/platform/IStorage.h"

namespace aura::platform {

// Exact signature per Stage 7 §4. Accessors return references to platform-owned
// singletons (non-owning from the caller's perspective, per §4 ownership summary).
class IPlatform {
 public:
  virtual ~IPlatform() = default;
  virtual IAudioInput& audioInput() = 0;
  virtual IClock& clock() = 0;
  virtual IStorage& storage() = 0;
  virtual IPowerManager& powerManager() = 0;
};

}  // namespace aura::platform

#endif  // AURA_PLATFORM_IPLATFORM_H
