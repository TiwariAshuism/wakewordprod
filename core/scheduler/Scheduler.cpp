// PROJECT AURA — core/scheduler/Scheduler.cpp
#include "core/scheduler/Scheduler.h"

#include <memory>
#include <utility>

#if defined(__ANDROID__) || defined(__linux__)
#include <pthread.h>
#include <sched.h>
#endif

namespace aura::scheduler {
namespace {

// Best-effort priority hint. Real RT-audio priority on Android is primarily
// governed by the Oboe stream's performance mode; this nudges the std::thread
// where the platform allows it. No-op on hosts that don't support it.
void applyPriority(std::thread& t, ThreadClass cls) {
#if defined(__ANDROID__) || defined(__linux__)
  int policy = SCHED_OTHER;
  sched_param param{};
  switch (cls) {
    case ThreadClass::kAudio:
      policy = SCHED_FIFO;
      param.sched_priority = 3;
      break;
    case ThreadClass::kInference:
      policy = SCHED_FIFO;
      param.sched_priority = 2;
      break;
    default:
      policy = SCHED_OTHER;
      param.sched_priority = 0;
      break;
  }
  // Failure is non-fatal (host lacks CAP_SYS_NICE, etc.).
  pthread_setschedparam(t.native_handle(), policy, &param);
#else
  (void)t;
  (void)cls;
#endif
}

}  // namespace

ManagedThread::ManagedThread(std::string name, ThreadClass cls, std::function<void()> tick)
    : name_(std::move(name)), class_(cls), tick_(std::move(tick)) {}

ManagedThread::~ManagedThread() {
  stop();
  join();
}

void ManagedThread::start() {
  if (running_.exchange(true)) return;
  stopRequested_.store(false, std::memory_order_release);
  thread_ = std::thread(&ManagedThread::run, this);
  applyPriority(thread_, class_);
}

void ManagedThread::stop() { stopRequested_.store(true, std::memory_order_release); }

void ManagedThread::join() {
  if (thread_.joinable()) thread_.join();
  running_.store(false, std::memory_order_release);
}

void ManagedThread::run() {
  while (!stopRequested_.load(std::memory_order_acquire)) {
    tick_();
  }
}

ManagedThread* Scheduler::spawnLoop(std::string name, ThreadClass cls, std::function<void()> tick) {
  threads_.push_back(std::make_unique<ManagedThread>(std::move(name), cls, std::move(tick)));
  ManagedThread* t = threads_.back().get();
  t->start();
  return t;
}

void Scheduler::stopAll() {
  for (auto& t : threads_) t->stop();
}

void Scheduler::joinAll() {
  stopAll();
  for (auto& t : threads_) t->join();
  threads_.clear();
}

}  // namespace aura::scheduler
