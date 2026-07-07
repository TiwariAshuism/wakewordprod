// PROJECT AURA — core/common/result.h
//
// Responsibilities : Result<T> — the tagged-union error model (Stage 7 §11) used
//                    for every fallible operation on the Audio/Inference hot path.
//                    No exceptions (Stage 7 §16 / Stage 9 §3).
// Dependencies     : core/common/error.h only.
// Thread ownership : value type; usable on any thread including the RT threads.
// Memory ownership : holds T inline (no heap) via std::optional; never allocates.
// Lifecycle        : ephemeral value; must be checked at the call site
//                    ([[nodiscard]]) — an unchecked Result is a CI error (Stage 9 §3).
//
// Usage surface required by the handbook's Good/Bad example:
//   explicit operator bool(), .error().toString(), Result<void> returning {}.
#ifndef AURA_COMMON_RESULT_H
#define AURA_COMMON_RESULT_H

#include <optional>
#include <utility>

#include "core/common/error.h"

namespace aura::common {

template <typename T>
class [[nodiscard]] Result {
 public:
  // Success construction (implicit, so `return value;` works).
  Result(T value) : value_(std::move(value)) {}       // NOLINT(runtime/explicit)
  // Failure construction.
  Result(Error error) : error_(error) {}              // NOLINT(runtime/explicit)

  [[nodiscard]] bool ok() const noexcept { return value_.has_value(); }
  explicit operator bool() const noexcept { return ok(); }

  // Precondition: ok(). Callers gate on operator bool first (Stage 9 §3).
  [[nodiscard]] const T& value() const& { return *value_; }
  [[nodiscard]] T& value() & { return *value_; }
  [[nodiscard]] T&& value() && { return std::move(*value_); }

  [[nodiscard]] const Error& error() const noexcept { return error_; }

 private:
  std::optional<T> value_{};
  Error error_{ErrorCode::kOk, ""};
};

// Void specialization: success is the default-constructed / {} value.
template <>
class [[nodiscard]] Result<void> {
 public:
  Result() = default;                                  // success
  Result(Error error) : ok_(false), error_(error) {}   // NOLINT(runtime/explicit)

  [[nodiscard]] bool ok() const noexcept { return ok_; }
  explicit operator bool() const noexcept { return ok_; }
  [[nodiscard]] const Error& error() const noexcept { return error_; }

 private:
  bool ok_ = true;
  Error error_{ErrorCode::kOk, ""};
};

// Convenience factory for the failure path, reads well at call sites:
//   return Err(ErrorCode::kUnsupportedFormat, "48kHz not supported");
inline Error Err(ErrorCode code, std::string_view message) { return Error{code, message}; }

}  // namespace aura::common

#endif  // AURA_COMMON_RESULT_H
