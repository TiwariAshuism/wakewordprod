// PROJECT AURA — hand-written JNI binding layer (Stage 9 §9 / ADR-Binding).
//
// Thin + mechanical by design: exposes an opaque jlong handle to a C++ engine
// bundle and marshals the IWakeWordListener callback back to a Kotlin object. It
// deliberately mirrors the C++ interfaces 1:1 with no idiomatic sugar — that lives
// in :aura-sdk — so a future codegen tool can drop-in replace this file.
//
// This file lives in sdk/ (not core/), so including <jni.h> is expected and does
// not violate the PAL rule (which governs core/ only, Stage 7 §2).
#include <jni.h>

#include <memory>
#include <string>

#include "core/common/log.h"
#include "core/config/Config.h"
#include "core/engine/WakeWordEngine.h"
#include "core/model/ModelManager.h"
#include "core/platform/android/AndroidLog.h"
#include "core/platform/android/AndroidPlatform.h"
#include "core/runtime/OnnxRuntimeBackend.h"
#include "core/vad/EnergyVad.h"
#include "core/vad/SileroVad.h"

using namespace aura;

namespace {

JavaVM* g_vm = nullptr;

// Marshals core callbacks to a Kotlin NativeBindings.Callback (Callback thread).
class JniListener final : public engine::IWakeWordListener {
 public:
  JniListener(JNIEnv* env, jobject callback) {
    cb_ = env->NewGlobalRef(callback);
    jclass cls = env->GetObjectClass(callback);
    onDetection_ = env->GetMethodID(cls, "onDetection", "(JJFJI)V");
    onState_ = env->GetMethodID(cls, "onState", "(I)V");
    onError_ = env->GetMethodID(cls, "onError", "(ILjava/lang/String;)V");
    env->DeleteLocalRef(cls);
  }
  ~JniListener() override {
    if (JNIEnv* env = attach()) env->DeleteGlobalRef(cb_);
  }

  void onWakeWordDetected(const common::DetectionEvent& e) override {
    if (JNIEnv* env = attach()) {
      env->CallVoidMethod(cb_, onDetection_, static_cast<jlong>(e.correlationId.hi),
                          static_cast<jlong>(e.correlationId.lo), static_cast<jfloat>(e.confidence),
                          static_cast<jlong>(e.timestampNanos),
                          static_cast<jint>(e.wakeWordIndex));
      detach();
    }
  }
  void onError(const engine::EngineError& err) override {
    if (JNIEnv* env = attach()) {
      jstring msg = env->NewStringUTF(err.message.c_str());
      env->CallVoidMethod(cb_, onError_, static_cast<jint>(err.code), msg);
      env->DeleteLocalRef(msg);
      detach();
    }
  }
  void onStateChanged(common::EngineState s) override {
    if (JNIEnv* env = attach()) {
      env->CallVoidMethod(cb_, onState_, static_cast<jint>(s));
      detach();
    }
  }

 private:
  JNIEnv* attach() {
    JNIEnv* env = nullptr;
    if (g_vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) == JNI_OK) {
      attached_ = false;
      return env;
    }
    if (g_vm->AttachCurrentThread(&env, nullptr) == JNI_OK) {
      attached_ = true;
      return env;
    }
    return nullptr;
  }
  void detach() {
    if (attached_) g_vm->DetachCurrentThread();
  }

  jobject cb_ = nullptr;
  jmethodID onDetection_ = nullptr;
  jmethodID onState_ = nullptr;
  jmethodID onError_ = nullptr;
  bool attached_ = false;
};

// Everything owned per engine instance, kept alive behind the opaque handle.
struct EngineBundle {
  std::unique_ptr<platform::android::AndroidPlatform> platform;
  std::unique_ptr<model::ModelManager> vadModel;
  std::shared_ptr<const config::Config> config;
  std::unique_ptr<engine::WakeWordEngine> engine;
  std::unique_ptr<JniListener> listener;
};

std::string jstr(JNIEnv* env, jstring s) {
  const char* c = env->GetStringUTFChars(s, nullptr);
  std::string out(c ? c : "");
  env->ReleaseStringUTFChars(s, c);
  return out;
}

EngineBundle* fromHandle(jlong h) { return reinterpret_cast<EngineBundle*>(h); }

}  // namespace

extern "C" JNIEXPORT jint JNI_OnLoad(JavaVM* vm, void*) {
  g_vm = vm;
  return JNI_VERSION_1_6;
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeCreate(JNIEnv* env, jobject, jstring filesDir) {
  platform::android::InstallAndroidLogSink();
  const std::string dir = jstr(env, filesDir);

  auto bundle = std::make_unique<EngineBundle>();
  bundle->platform = std::make_unique<platform::android::AndroidPlatform>(dir);
  bundle->config = std::make_shared<const config::Config>(config::Config{});

  const std::string modelDir = dir + "/models";

  // Load the Silero VAD model (owned by a dedicated ModelManager slot) and build
  // the Silero VAD; fall back to EnergyVad if the model is missing.
  std::unique_ptr<vad::IVad> vadImpl;
  bundle->vadModel =
      std::make_unique<model::ModelManager>(bundle->platform->storage(), common::ModelSlot::kVad);
  auto vadStaged = bundle->vadModel->stage(modelDir + "/" + bundle->config->models.vadModelFile);
  if (vadStaged) {
    auto silero = vad::SileroVad::Create(vadStaged.value(),
                                         static_cast<int>(bundle->config->features.sampleRate));
    if (silero) {
      vadImpl = std::move(silero);
    }
  }
  if (!vadImpl) {
    common::Log(common::LogLevel::kWarn, common::LogCategory::kVad,
                "Silero unavailable; using EnergyVad fallback");
    vadImpl = std::make_unique<vad::EnergyVad>();
  }

  auto backend = std::make_unique<runtime::OnnxRuntimeBackend>();
  // Stage-2 verifier backend (two-stage cascade). The engine loads the stage2 model in
  // initialize(); if it's absent the cascade falls back to Stage-1-only.
  auto backend2 = std::make_unique<runtime::OnnxRuntimeBackend>();
  bundle->engine = std::make_unique<engine::WakeWordEngine>(
      *bundle->platform, bundle->config, std::move(backend), std::move(vadImpl),
      std::move(backend2));
  return reinterpret_cast<jlong>(bundle.release());
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeInitialize(JNIEnv* env, jobject, jlong handle,
                                                              jstring modelDir) {
  auto* b = fromHandle(handle);
  engine::EngineOptions opts;
  opts.modelDir = jstr(env, modelDir);
  return static_cast<jboolean>(static_cast<bool>(b->engine->initialize(opts)));
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeAddWakeWord(JNIEnv* env, jobject, jlong handle,
                                                               jstring id, jfloat threshold) {
  auto* b = fromHandle(handle);
  engine::WakeWordSpec spec;
  spec.id = jstr(env, id);
  spec.phrase = spec.id;
  spec.threshold = threshold;
  return static_cast<jboolean>(static_cast<bool>(b->engine->addWakeWord(spec)));
}

extern "C" JNIEXPORT void JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeSetListener(JNIEnv* env, jobject, jlong handle,
                                                               jobject callback) {
  auto* b = fromHandle(handle);
  b->listener = std::make_unique<JniListener>(env, callback);
  b->engine->setListener(b->listener.get());
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeStart(JNIEnv*, jobject, jlong handle) {
  return static_cast<jboolean>(static_cast<bool>(fromHandle(handle)->engine->start()));
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeStop(JNIEnv*, jobject, jlong handle) {
  return static_cast<jboolean>(static_cast<bool>(fromHandle(handle)->engine->stop()));
}

extern "C" JNIEXPORT void JNICALL
Java_com_getnyx_aura_bindings_NativeBindings_nativeDestroy(JNIEnv*, jobject, jlong handle) {
  delete fromHandle(handle);  // tears down engine (joins threads), listener, models
}
