// PROJECT AURA — core/config/tests/config_test.cpp
#include "core/config/ConfigProvider.h"
#include "core/config/DefaultConfigProvider.h"
#include "tests/support/test_framework.h"

using namespace aura::config;

TEST(Config, DefaultsFullyPopulated) {
  DefaultConfigProvider provider;
  auto cfg = provider.current();
  ASSERT_TRUE(cfg != nullptr);
  // A resolved Config is always complete (Stage 7 §9).
  EXPECT_EQ(cfg->audio.sampleRate, 16000u);
  EXPECT_EQ(cfg->features.nMels, 40);
  EXPECT_EQ(cfg->features.sampleRate, 16000u);
  EXPECT_GT(cfg->detect.stage1WindowFrames, 0);
  EXPECT_TRUE(cfg->models.stage1WakeWord == "hey aura");
}

TEST(Config, SnapshotIsShared) {
  DefaultConfigProvider provider;
  auto a = provider.current();
  auto b = provider.current();
  EXPECT_EQ(a.get(), b.get());  // same immutable snapshot
}

TEST(Config, PlatformOverlayApplied) {
  // Overlay (e.g. an MCU tier) shrinks the ring buffer before overrides.
  ConfigProvider provider(Config{}, [](Config& c) { c.audio.pcmSlotCount = 8; });
  auto cfg = provider.current();
  EXPECT_EQ(cfg->audio.pcmSlotCount, 8u);
  EXPECT_EQ(cfg->audio.sampleRate, 16000u);  // untouched default remains
}

TEST(Config, RuntimeOverridePublishesAndNotifies) {
  ConfigProvider provider;
  auto before = provider.current();
  EXPECT_NEAR(before->detect.stage1Threshold, 0.35f, 1e-6);

  int fired = 0;
  float seen = 0.0f;
  provider.onConfigChanged([&](std::shared_ptr<const Config> c) {
    ++fired;
    seen = c->detect.stage1Threshold;
  });

  provider.applyOverride([](Config& c) { c.detect.stage1Threshold = 0.7f; });

  auto after = provider.current();
  EXPECT_EQ(fired, 1);
  EXPECT_NEAR(seen, 0.7f, 1e-6);
  EXPECT_NEAR(after->detect.stage1Threshold, 0.7f, 1e-6);
  EXPECT_NE(before.get(), after.get());                 // new immutable snapshot
  EXPECT_NEAR(before->detect.stage1Threshold, 0.35f, 1e-6);  // old snapshot unchanged
}

TEST(Config, OverrideWinsOverOverlay) {
  ConfigProvider provider(Config{}, [](Config& c) { c.detect.stage1Threshold = 0.6f; });
  EXPECT_NEAR(provider.current()->detect.stage1Threshold, 0.6f, 1e-6);  // overlay
  provider.applyOverride([](Config& c) { c.detect.stage1Threshold = 0.9f; });
  EXPECT_NEAR(provider.current()->detect.stage1Threshold, 0.9f, 1e-6);  // override wins
}
