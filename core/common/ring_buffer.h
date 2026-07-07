// PROJECT AURA — core/common/ring_buffer.h
//
// Responsibilities : Single-producer/single-consumer fixed-slot pool used for the
//                    two zero-copy handoffs in Stage 7 §5 (platform->audio raw PCM;
//                    audio->inference log-Mel). Slots are filled in place
//                    (acquireWrite/commitWrite) so payloads are moved, not copied.
// Dependencies     : none (foundation).
// Thread ownership : exactly one producer thread and one consumer thread. Indices
//                    are monotonically increasing 64-bit counters; the slot header
//                    (head/tail) is padded to separate cache lines to avoid false
//                    sharing (Stage 7 §5), since producer and consumer touch them
//                    concurrently.
// Memory ownership : owns N pre-allocated slots; fixed at construction, no dynamic
//                    growth. A full pool triggers backpressure, not allocation.
#ifndef AURA_COMMON_RING_BUFFER_H
#define AURA_COMMON_RING_BUFFER_H

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <vector>

#include "core/common/aligned_alloc.h"

namespace aura::common {

enum class BackpressurePolicy : uint8_t { kDropOldest = 0, kDropNewest };

// SPSC ring of `capacity` slots of T. T is a POD-ish slot payload (e.g. a
// fixed-size sample buffer). Not copyable.
template <typename T>
class RingBuffer {
 public:
  RingBuffer() = default;
  explicit RingBuffer(size_t capacity, BackpressurePolicy policy = BackpressurePolicy::kDropOldest) {
    reserve(capacity, policy);
  }

  RingBuffer(const RingBuffer&) = delete;
  RingBuffer& operator=(const RingBuffer&) = delete;

  // Startup only (allocates the slot storage).
  void reserve(size_t capacity, BackpressurePolicy policy = BackpressurePolicy::kDropOldest) {
    slots_.assign(capacity, T{});
    capacity_ = capacity;
    policy_ = policy;
    head_.store(0, std::memory_order_relaxed);
    tail_.store(0, std::memory_order_relaxed);
    dropCount_.store(0, std::memory_order_relaxed);
  }

  size_t capacity() const { return capacity_; }

  size_t size() const {
    return static_cast<size_t>(head_.load(std::memory_order_acquire) -
                               tail_.load(std::memory_order_acquire));
  }
  bool empty() const { return size() == 0; }
  bool full() const { return size() >= capacity_; }
  uint64_t dropCount() const { return dropCount_.load(std::memory_order_relaxed); }

  // --- Producer side (one thread) ---------------------------------------

  // Returns a pointer to the slot to fill in place, or nullptr if the pool is
  // full AND policy is kDropNewest. Under kDropOldest a full pool drops the
  // oldest slot (advances tail) and returns a writable slot. Fill it, then call
  // commitWrite().
  T* acquireWrite() {
    const uint64_t head = head_.load(std::memory_order_relaxed);
    const uint64_t tail = tail_.load(std::memory_order_acquire);
    if (head - tail >= capacity_) {
      if (policy_ == BackpressurePolicy::kDropNewest) {
        dropCount_.fetch_add(1, std::memory_order_relaxed);
        return nullptr;
      }
      // drop-oldest: a stale frame is worthless once superseded (Stage 7 §5).
      tail_.fetch_add(1, std::memory_order_acq_rel);
      dropCount_.fetch_add(1, std::memory_order_relaxed);
    }
    return &slots_[head % capacity_];
  }

  void commitWrite() { head_.fetch_add(1, std::memory_order_release); }

  // --- Consumer side (one thread) ---------------------------------------

  // Returns the oldest unread slot, or nullptr if empty. Read it, then
  // commitRead().
  const T* acquireRead() {
    const uint64_t tail = tail_.load(std::memory_order_relaxed);
    const uint64_t head = head_.load(std::memory_order_acquire);
    if (tail >= head) return nullptr;
    return &slots_[tail % capacity_];
  }

  void commitRead() { tail_.fetch_add(1, std::memory_order_release); }

 private:
  static constexpr size_t kPad = 64;  // cache line

  std::vector<T> slots_;
  size_t capacity_ = 0;
  BackpressurePolicy policy_ = BackpressurePolicy::kDropOldest;

  alignas(kPad) std::atomic<uint64_t> head_{0};  // producer-owned
  alignas(kPad) std::atomic<uint64_t> tail_{0};  // consumer-owned (+ producer on drop-oldest)
  alignas(kPad) std::atomic<uint64_t> dropCount_{0};
};

}  // namespace aura::common

#endif  // AURA_COMMON_RING_BUFFER_H
