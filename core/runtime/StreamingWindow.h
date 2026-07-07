// PROJECT AURA — core/runtime/StreamingWindow.h
//
// Responsibilities : the on-device streaming feature-window accumulator a
//                    streaming wake-word detector carries as state (D2). It ingests
//                    one [nMels] log-Mel frame at a time and, every hop, hands the
//                    inference backend a contiguous [windowFrames, nMels] view of the
//                    most recent `windowFrames` frames in temporal order (oldest →
//                    newest, newest last — matching Stage1Detector's window layout).
// Dependencies     : none (header-only, standard library only). Row 5 (runtime), but
//                    includes no core/ modules, so it is trivially row-clean and
//                    carries no OS/SDK/PAL dependency (Stage 7 §2 dependency linter).
// Thread ownership : single-threaded per instance — owned by whichever thread drives
//                    the feature stream (the Inference thread in the cascade). Not
//                    internally synchronised.
// Memory ownership : owns one fixed, front-loaded backing buffer sized at
//                    construction (2 · windowFrames · nMels floats). No per-frame or
//                    per-view allocation; push() is O(nMels) — independent of
//                    windowFrames — and never recopies the whole window.
//
// Design note (why 2× storage): a plain ring buffer wraps in memory, so a temporally
// ordered view of the last N frames is not contiguous once the write head passes the
// end. The classic double-mirror trick writes each incoming frame to BOTH slot `head`
// and slot `head + windowFrames`; the contiguous window [head, head + windowFrames)
// is then always in bounds and already in temporal order. That makes push() a fixed
// two-row copy regardless of window size — as opposed to the O(windowFrames) memmove
// a naive shift-by-one buffer performs every frame.
#ifndef AURA_RUNTIME_STREAMINGWINDOW_H
#define AURA_RUNTIME_STREAMINGWINDOW_H

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <vector>

namespace aura::runtime {

class StreamingWindow {
 public:
  // windowFrames: temporal length of the view (e.g. 100). nMels: features per frame
  // (e.g. 40). The backing buffer is zero-initialised so that, before the window has
  // filled, the view carries a zero pre-roll with the newest frame at the end.
  StreamingWindow(int windowFrames, int nMels)
      : windowFrames_(windowFrames),
        nMels_(nMels),
        row_(static_cast<size_t>(nMels)),
        storage_(static_cast<size_t>(2) * static_cast<size_t>(windowFrames) * row_, 0.0f) {}

  // Push one [nMels] frame. O(nMels): writes exactly two rows (the live slot and its
  // mirror), independent of windowFrames — the whole window is never recopied.
  void push(const float* frame) {
    float* live = storage_.data() + static_cast<size_t>(head_) * row_;
    float* mirror = live + static_cast<size_t>(windowFrames_) * row_;
    std::memcpy(live, frame, row_ * sizeof(float));
    std::memcpy(mirror, frame, row_ * sizeof(float));
    head_ = (head_ + 1 == windowFrames_) ? 0 : head_ + 1;
    if (filled_ < windowFrames_) ++filled_;
    pushRowCopies_ += 2;  // instrumentation: proves constant per-push work
  }

  // Contiguous [windowFrames, nMels] view, row-major, oldest → newest (newest last).
  // Valid until the next push(); points into the owned backing buffer, no copy.
  const float* view() const { return storage_.data() + static_cast<size_t>(head_) * row_; }

  // Pointer to temporal frame i in [0, windowFrames): i == 0 is the oldest slot in the
  // view, i == windowFrames-1 is the most recent frame just pushed.
  const float* frame(int i) const { return view() + static_cast<size_t>(i) * row_; }

  int windowFrames() const { return windowFrames_; }
  int nMels() const { return nMels_; }
  int filled() const { return filled_; }        // real frames seen, capped at windowFrames
  bool full() const { return filled_ == windowFrames_; }

  // Total rows copied across all pushes. Exactly 2 per push, so this stays == 2·pushes
  // regardless of windowFrames — the O(1)-push witness used by the tests.
  uint64_t pushRowCopies() const { return pushRowCopies_; }

  void reset() {
    std::fill(storage_.begin(), storage_.end(), 0.0f);
    head_ = 0;
    filled_ = 0;
    pushRowCopies_ = 0;
  }

 private:
  int windowFrames_;
  int nMels_;
  size_t row_;
  std::vector<float> storage_;  // 2 · windowFrames · nMels, mirrored halves
  int head_ = 0;                // write index into the first half; also the view offset
  int filled_ = 0;
  uint64_t pushRowCopies_ = 0;
};

}  // namespace aura::runtime

#endif  // AURA_RUNTIME_STREAMINGWINDOW_H
