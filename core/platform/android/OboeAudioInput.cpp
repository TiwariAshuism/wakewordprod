// PROJECT AURA — core/platform/android/OboeAudioInput.cpp
#include "core/platform/android/OboeAudioInput.h"

#include <utility>

namespace aura::platform::android {

using common::AudioFormat;
using common::AudioFrameView;
using common::Err;
using common::ErrorCode;
using common::Result;
using common::SampleFormat;

Result<void> OboeAudioInput::start(const AudioFormat& requestedFormat, FrameCallback cb) {
  if (stream_) return Err(ErrorCode::kFailedPrecondition, "OboeAudioInput already started");
  if (requestedFormat.format != SampleFormat::kInt16) {
    // Fail fast on unsupported format (Stage 7 §4). core/audio handles resampling,
    // but v0 fixes I16/mono/16k end-to-end.
    return Err(ErrorCode::kUnsupportedFormat, "only Int16 PCM supported in v0");
  }
  frameCallback_ = std::move(cb);
  format_ = requestedFormat;

  oboe::AudioStreamBuilder builder;
  builder.setDirection(oboe::Direction::Input)
      ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
      ->setSharingMode(oboe::SharingMode::Exclusive)
      ->setFormat(oboe::AudioFormat::I16)
      ->setChannelCount(requestedFormat.channels)
      ->setSampleRate(static_cast<int32_t>(requestedFormat.sampleRate))
      ->setSampleRateConversionQuality(oboe::SampleRateConversionQuality::Medium)
      ->setInputPreset(oboe::InputPreset::VoiceRecognition)
      ->setDataCallback(this)
      ->setErrorCallback(this);

  const oboe::Result r = builder.openStream(stream_);
  if (r != oboe::Result::OK) {
    stream_.reset();
    return Err(ErrorCode::kUnavailable, oboe::convertToText(r));
  }
  // Reflect what the device actually granted (may differ from requested).
  format_.sampleRate = static_cast<uint32_t>(stream_->getSampleRate());
  format_.channels = static_cast<uint8_t>(stream_->getChannelCount());

  const oboe::Result started = stream_->requestStart();
  if (started != oboe::Result::OK) {
    stream_->close();
    stream_.reset();
    return Err(ErrorCode::kUnavailable, oboe::convertToText(started));
  }
  return {};
}

Result<void> OboeAudioInput::stop() {
  if (!stream_) return {};
  stream_->requestStop();
  stream_->close();
  stream_.reset();
  return {};
}

Result<AudioFormat> OboeAudioInput::currentFormat() const {
  if (!stream_) return Err(ErrorCode::kFailedPrecondition, "not started");
  return format_;
}

void OboeAudioInput::onDeviceChanged(
    std::function<void(const common::DeviceChangeEvent&)> handler) {
  deviceChangedHandler_ = std::move(handler);
}

// ISR-equivalent context: no heap alloc, no locks (Stage 7 §4/§6).
oboe::DataCallbackResult OboeAudioInput::onAudioReady(oboe::AudioStream* stream, void* audioData,
                                                      int32_t numFrames) {
  if (frameCallback_) {
    AudioFrameView view;
    view.i16 = static_cast<const int16_t*>(audioData);
    view.frames = static_cast<size_t>(numFrames);
    view.sampleRate = static_cast<uint32_t>(stream->getSampleRate());
    view.channels = static_cast<uint8_t>(stream->getChannelCount());
    frameCallback_(view, clock_.nowMonotonicNanos());
  }
  return oboe::DataCallbackResult::Continue;
}

void OboeAudioInput::onErrorAfterClose(oboe::AudioStream* /*stream*/, oboe::Result /*error*/) {
  // Device disconnected / route changed. core/audio will re-open via the handler.
  if (deviceChangedHandler_) {
    deviceChangedHandler_(common::DeviceChangeEvent{common::DeviceChangeKind::kDisconnected});
  }
}

}  // namespace aura::platform::android
