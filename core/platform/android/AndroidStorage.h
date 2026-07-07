// PROJECT AURA — core/platform/android/AndroidStorage.h
// IStorage for Android: read-only mmap of model files under the app files dir.
#ifndef AURA_PLATFORM_ANDROID_ANDROIDSTORAGE_H
#define AURA_PLATFORM_ANDROID_ANDROIDSTORAGE_H

#include <filesystem>

#include "core/platform/IStorage.h"

namespace aura::platform::android {

class AndroidStorage final : public IStorage {
 public:
  explicit AndroidStorage(std::filesystem::path baseDir) : baseDir_(std::move(baseDir)) {}

  std::filesystem::path baseDir() const override { return baseDir_; }
  common::Result<MappedRegion> mapReadOnly(const std::filesystem::path& path) override;
  void unmap(const MappedRegion& region) override;

 private:
  std::filesystem::path baseDir_;
};

}  // namespace aura::platform::android

#endif  // AURA_PLATFORM_ANDROID_ANDROIDSTORAGE_H
