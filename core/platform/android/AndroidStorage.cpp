// PROJECT AURA — core/platform/android/AndroidStorage.cpp
#include "core/platform/android/AndroidStorage.h"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace aura::platform::android {

using common::Err;
using common::ErrorCode;
using common::Result;

namespace {
// Small holder so unmap() can recover the length + fd from `opaque`.
struct MappingBookkeeping {
  size_t length;
};
}  // namespace

Result<MappedRegion> AndroidStorage::mapReadOnly(const std::filesystem::path& path) {
  const std::filesystem::path full = path.is_absolute() ? path : (baseDir_ / path);
  const int fd = ::open(full.c_str(), O_RDONLY);
  if (fd < 0) return Err(ErrorCode::kNotFound, "AndroidStorage: open failed");

  struct stat st{};
  if (::fstat(fd, &st) != 0 || st.st_size <= 0) {
    ::close(fd);
    return Err(ErrorCode::kIoError, "AndroidStorage: fstat failed");
  }
  const size_t length = static_cast<size_t>(st.st_size);
  void* addr = ::mmap(nullptr, length, PROT_READ, MAP_PRIVATE, fd, 0);
  ::close(fd);  // mapping survives the fd being closed
  if (addr == MAP_FAILED) return Err(ErrorCode::kIoError, "AndroidStorage: mmap failed");

  auto* book = new MappingBookkeeping{length};  // startup-only alloc (not hot path)
  return MappedRegion{addr, length, book};
}

void AndroidStorage::unmap(const MappedRegion& region) {
  if (!region.data || !region.opaque) return;
  auto* book = static_cast<MappingBookkeeping*>(region.opaque);
  ::munmap(const_cast<void*>(region.data), book->length);
  delete book;
}

}  // namespace aura::platform::android
