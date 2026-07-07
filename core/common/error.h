// PROJECT AURA — core/common/error.h
//
// Responsibilities : Canonical error value used by Result<T> across every core/ module.
// Dependencies     : none (foundation, below Row 0).
// Thread ownership : none — value type, safe to construct/copy on any thread.
// Memory ownership : holds only a code + a non-owning string_view (points at a
//                    static string literal on the hot path; never allocates).
// Lifecycle        : ephemeral value.
//
// Coding standard (Stage 9 §3): no exceptions; hot-path construction must not
// allocate — that is why the message is a std::string_view over a literal, not a
// std::string. See the "Good vs. bad" example in the handbook.
#ifndef AURA_COMMON_ERROR_H
#define AURA_COMMON_ERROR_H

#include <cstdint>
#include <string>
#include <string_view>

namespace aura::common
{

  // Stable, cross-module error codes. Categories mirror Stage 7 §11's error table.
  enum class ErrorCode : uint16_t
  {
    kOk = 0,
    kUnknown,
    kInvalidArgument,
    kFailedPrecondition, // e.g. start() called before initialize()
    kUnavailable,        // transient platform I/O (device busy, storage unavailable)
    kNotFound,           // model file / asset missing
    kIoError,
    kUnsupportedFormat,   // IAudioInput::start() fast-fail
    kBackendError,        // inference backend internal failure
    kVerificationFailed,  // model signature / checksum mismatch
    kUnimplemented,       // v0 deliberately-unimplemented path (flagged, never silent)
    kBackpressureDropped, // ring buffer full; frame dropped per policy
  };

  // A lightweight, allocation-free error. `message` MUST reference storage that
  // outlives the Error (a string literal, in practice) on the Audio/Inference
  // threads. toString() is permitted to allocate and is therefore for use on
  // non-hot-path threads / logging only.
  struct Error
  {
    ErrorCode code = ErrorCode::kUnknown;
    std::string_view message{};

    constexpr Error() = default;
    constexpr Error(ErrorCode c, std::string_view m) : code(c), message(m) {}

    [[nodiscard]] std::string toString() const
    {
      // Allowed to allocate: only ever called off the hot path (Stage 9 §3).
      return std::string(codeName(code)) + ": " + std::string(message);
    }

    static constexpr std::string_view codeName(ErrorCode c)
    {
      switch (c)
      {
      case ErrorCode::kOk:
        return "Ok";
      case ErrorCode::kInvalidArgument:
        return "InvalidArgument";
      case ErrorCode::kFailedPrecondition:
        return "FailedPrecondition";
      case ErrorCode::kUnavailable:
        return "Unavailable";
      case ErrorCode::kNotFound:
        return "NotFound";
      case ErrorCode::kIoError:
        return "IoError";
      case ErrorCode::kUnsupportedFormat:
        return "UnsupportedFormat";
      case ErrorCode::kBackendError:
        return "BackendError";
      case ErrorCode::kVerificationFailed:
        return "VerificationFailed";
      case ErrorCode::kUnimplemented:
        return "Unimplemented";
      case ErrorCode::kBackpressureDropped:
        return "BackpressureDropped";
      case ErrorCode::kUnknown:
      default:
        return "Unknown";
      }
    }
  };

} // namespace aura::common

#endif // AURA_COMMON_ERROR_H
