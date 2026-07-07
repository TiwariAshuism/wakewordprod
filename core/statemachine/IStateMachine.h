// PROJECT AURA — core/statemachine/IStateMachine.h
//
// Responsibilities : generic, reusable state-machine execution engine used by every
//                    Section-7 machine (Stage 7 §3.4). Header-only template
//                    (permitted generic utility, Stage 7 §16).
// Dependencies     : core/common (Row 1; depends only on scheduler-agnostic bits
//                    here — cross-thread posting is provided but the owning thread
//                    is chosen by the consumer, per §3.4).
// Thread ownership : each instance is pinned to a single owning thread; transitions
//                    from other threads are queued via post() and applied by the
//                    owner in drain(), never executed cross-thread directly.
// Memory ownership : owns its current-state value and a bounded event queue.
#ifndef AURA_STATEMACHINE_ISTATEMACHINE_H
#define AURA_STATEMACHINE_ISTATEMACHINE_H

#include <functional>
#include <mutex>
#include <optional>
#include <queue>

namespace aura::statemachine {

// TState and TEvent are small trivially-copyable enums/structs. The transition
// function maps (currentState, event) -> nextState. onEnter fires when a
// transition changes the state.
template <typename TState, typename TEvent>
class StateMachine {
 public:
  using TransitionFn = std::function<TState(TState current, const TEvent& event)>;
  using OnEnterFn = std::function<void(TState previous, TState next, const TEvent& cause)>;

  StateMachine(TState initial, TransitionFn transition, OnEnterFn onEnter = {})
      : state_(initial), transition_(std::move(transition)), onEnter_(std::move(onEnter)) {}

  TState state() const { return state_; }

  // Apply an event synchronously on the owning thread. Returns the new state.
  TState dispatch(const TEvent& event) {
    const TState previous = state_;
    const TState next = transition_(previous, event);
    if (next != previous) {
      state_ = next;
      if (onEnter_) onEnter_(previous, next, event);
    }
    return state_;
  }

  // Post an event from another thread; applied later by the owner in drain().
  void post(const TEvent& event) {
    std::lock_guard<std::mutex> lock(mu_);
    queue_.push(event);
  }

  // Called by the owning thread to apply all queued cross-thread events.
  void drain() {
    for (;;) {
      std::optional<TEvent> ev;
      {
        std::lock_guard<std::mutex> lock(mu_);
        if (queue_.empty()) break;
        ev = queue_.front();
        queue_.pop();
      }
      dispatch(*ev);
    }
  }

 private:
  TState state_;
  TransitionFn transition_;
  OnEnterFn onEnter_;
  std::mutex mu_;
  std::queue<TEvent> queue_;
};

}  // namespace aura::statemachine

#endif  // AURA_STATEMACHINE_ISTATEMACHINE_H
