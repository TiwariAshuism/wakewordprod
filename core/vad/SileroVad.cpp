// PROJECT AURA — core/vad/SileroVad.cpp
// Compiled only when ONNX Runtime is available (AURA_ENABLE_ONNXRUNTIME); the host
// build excludes this TU and uses EnergyVad instead.
#include "core/vad/SileroVad.h"

#if defined(AURA_ENABLE_ONNXRUNTIME)

#include <onnxruntime_cxx_api.h>

#include <array>
#include <cstring>
#include <vector>

#include "core/common/noalloc.h"  // ScopedAllowAllocGuard (ORT allocation boundary)

namespace aura::vad {

namespace {
constexpr int kChunk = 512;      // Silero v5 native chunk @ 16 kHz
constexpr int kContext = 64;     // v5 prepends 64 samples of prior context (else prob==0!)
constexpr int kInput = kChunk + kContext;  // actual model input length = 576
constexpr int kStateSize = 2 * 1 * 128;  // [2,1,128]
}  // namespace

struct SileroVad::Impl {
  Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "aura-silero"};
  Ort::SessionOptions opts;
  std::unique_ptr<Ort::Session> session;
  Ort::MemoryInfo memInfo = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

  std::vector<float> state;      // [2,1,128], persists across calls
  std::vector<float> chunk;      // 512-sample accumulation buffer
  std::vector<float> context;    // last 64 samples of prior input (Silero context)
  std::vector<float> inBuf;      // [context(64) ++ chunk(512)] = 576, reused each call
  int chunkFill = 0;
  int64_t sampleRate = 16000;
  float lastProb = 0.0f;

  const char* inNames[3] = {"input", "state", "sr"};
  const char* outNames[2] = {"output", "stateN"};
};

std::unique_ptr<SileroVad> SileroVad::Create(const common::ModelHandle& model, int sampleRate) {
  if (!model.valid()) return nullptr;
  auto impl = std::make_unique<Impl>();
  impl->opts.SetIntraOpNumThreads(1);
  impl->opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
  try {
    impl->session = std::make_unique<Ort::Session>(
        impl->env, model.data, model.size, impl->opts);
  } catch (const Ort::Exception&) {
    return nullptr;  // convert exception to null at the boundary (Stage 9 §3)
  }
  impl->state.assign(kStateSize, 0.0f);
  impl->chunk.assign(kChunk, 0.0f);
  impl->context.assign(kContext, 0.0f);
  impl->inBuf.assign(kInput, 0.0f);
  impl->sampleRate = sampleRate;
  return std::unique_ptr<SileroVad>(new SileroVad(std::move(impl)));
}

SileroVad::SileroVad(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}
SileroVad::~SileroVad() = default;

void SileroVad::reset() {
  std::fill(impl_->state.begin(), impl_->state.end(), 0.0f);
  std::fill(impl_->context.begin(), impl_->context.end(), 0.0f);
  impl_->chunkFill = 0;
  impl_->lastProb = 0.0f;
}

float SileroVad::process(const float* samples, size_t n) {
  auto& im = *impl_;
  size_t i = 0;
  while (i < n) {
    const int take = std::min<int>(kChunk - im.chunkFill, static_cast<int>(n - i));
    std::memcpy(im.chunk.data() + im.chunkFill, samples + i, take * sizeof(float));
    im.chunkFill += take;
    i += static_cast<size_t>(take);
    if (im.chunkFill < kChunk) break;
    im.chunkFill = 0;

    // Silero runs its own ONNX Runtime session; Run() allocates internally. This is on the
    // audio hot path (under WakeWordEngine's ScopedNoAllocGuard), so mark the ORT boundary
    // as an allowed allocation site (same as OnnxRuntimeBackend::infer) — device-only abort.
    common::ScopedAllowAllocGuard allow;

    // Silero v5 input = [context(64) ++ new_chunk(512)] = 576 samples; context is the last
    // 64 samples of the previous input, carried across calls. Feeding only the 512 (no
    // context) makes the model output ~0 for all audio — the on-device no-detection bug.
    std::memcpy(im.inBuf.data(), im.context.data(), kContext * sizeof(float));
    std::memcpy(im.inBuf.data() + kContext, im.chunk.data(), kChunk * sizeof(float));
    std::memcpy(im.context.data(), im.inBuf.data() + kInput - kContext, kContext * sizeof(float));

    const std::array<int64_t, 2> inShape{1, kInput};
    const std::array<int64_t, 3> stShape{2, 1, 128};
    const std::array<int64_t, 1> srShape{1};

    Ort::Value input = Ort::Value::CreateTensor<float>(
        im.memInfo, im.inBuf.data(), im.inBuf.size(), inShape.data(), inShape.size());
    Ort::Value stateV = Ort::Value::CreateTensor<float>(
        im.memInfo, im.state.data(), im.state.size(), stShape.data(), stShape.size());
    Ort::Value sr = Ort::Value::CreateTensor<int64_t>(
        im.memInfo, &im.sampleRate, 1, srShape.data(), srShape.size());

    std::array<Ort::Value, 3> inputs{std::move(input), std::move(stateV), std::move(sr)};
    try {
      auto outputs = im.session->Run(Ort::RunOptions{nullptr}, im.inNames, inputs.data(),
                                     inputs.size(), im.outNames, 2);
      im.lastProb = outputs[0].GetTensorData<float>()[0];
      const float* newState = outputs[1].GetTensorData<float>();
      std::memcpy(im.state.data(), newState, im.state.size() * sizeof(float));
    } catch (const Ort::Exception&) {
      im.lastProb = 0.0f;  // fail closed
    }
  }
  return im.lastProb;
}

}  // namespace aura::vad

#endif  // AURA_ENABLE_ONNXRUNTIME
