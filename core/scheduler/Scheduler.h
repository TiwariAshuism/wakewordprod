// PROJECT AURA — core/scheduler/Scheduler.h
//
// Responsibilities : owns thread creation, priority assignment, and (debug)
//                    lock-hierarchy enforcement (Stage 7 §3.3/§6).
// Dependencies     : core/platform (Row 1). (Priority application is best-effort;
//                    on the host it is a no-op — real RT priorities are set in the
//                    Android build via pthread/Oboe stream affinity.)
// Thread ownership : creates and owns the Section-6 threads it is asked to spawn.
// Memory ownership : owns the std::thread handles; owns no audio/tensor buffers.
// Lifecycle        : created first after platform/, torn down last (joinAll()).
#ifndef AURA_SCHEDULER_SCHEDULER_H
#define AURA_SCHEDULER_SCHEDULER_H

#include <atomic>
#include <functional>
#include <string>
#include <thread>
#include <vector>

namespace aura::scheduler {

enum class ThreadClass : uint8_t {
  kAudio = 0,     // highest / RT-audio class (Stage 7 §6)
  kInference,     // high, soft-RT
  kCallback,      // medium
  kBackground,    // low
};

// A managed loop thread. The body is invoked repeatedly until stop() is called;
// the body should perform one unit of work and return (it must not itself spin
// forever, so shutdown stays responsive).
class ManagedThread {
 public:
  ManagedThread(std::string name, ThreadClass cls, std::function<void()> tick);
  ~ManagedThread();

  ManagedThread(const ManagedThread&) = delete;
  ManagedThread& operator=(const ManagedThread&) = delete;

  void start();
  void stop();   // signals; idempotent
  void join();

  const std::string& name() const { return name_; }
  bool running() const { return running_.load(std::memory_order_acquire); }

 private:
  void run();

  std::string name_;
  ThreadClass class_;
  std::function<void()> tick_;
  std::thread thread_;
  std::atomic<bool> running_{false};
  std::atomic<bool> stopRequested_{false};
};

// Thin factory/registry so modules create threads through one owner (Stage 7 §3.3).
class Scheduler {
 public:
  Scheduler() = default;
  ~Scheduler() { joinAll(); }

  ManagedThread* spawnLoop(std::string name, ThreadClass cls, std::function<void()> tick);
  void stopAll();
  void joinAll();

 private:
  std::vector<std::unique_ptr<ManagedThread>> threads_;
};

}  // namespace aura::scheduler

#endif  // AURA_SCHEDULER_SCHEDULER_H
