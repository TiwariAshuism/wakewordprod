// PROJECT AURA — core/statemachine/tests/statemachine_test.cpp
#include "core/statemachine/IStateMachine.h"
#include "tests/support/test_framework.h"

using namespace aura::statemachine;

namespace {
enum class S { kA, kB, kC };
enum class E { kGo, kBack };
}  // namespace

TEST(StateMachine, TransitionAndOnEnter) {
  int enters = 0;
  StateMachine<S, E> sm(
      S::kA,
      [](S s, const E& e) {
        if (s == S::kA && e == E::kGo) return S::kB;
        if (s == S::kB && e == E::kGo) return S::kC;
        if (e == E::kBack) return S::kA;
        return s;
      },
      [&](S, S, const E&) { ++enters; });

  EXPECT_EQ(sm.state(), S::kA);
  EXPECT_EQ(sm.dispatch(E::kGo), S::kB);
  EXPECT_EQ(sm.dispatch(E::kGo), S::kC);
  EXPECT_EQ(enters, 2);
  // No-op transition fires no onEnter.
  EXPECT_EQ(sm.dispatch(E::kGo), S::kC);
  EXPECT_EQ(enters, 2);
  EXPECT_EQ(sm.dispatch(E::kBack), S::kA);
  EXPECT_EQ(enters, 3);
}

TEST(StateMachine, CrossThreadPostDrain) {
  StateMachine<S, E> sm(S::kA, [](S s, const E& e) {
    return (s == S::kA && e == E::kGo) ? S::kB : s;
  });
  sm.post(E::kGo);          // queued, not yet applied
  EXPECT_EQ(sm.state(), S::kA);
  sm.drain();               // owner applies
  EXPECT_EQ(sm.state(), S::kB);
}
