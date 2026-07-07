// PROJECT AURA — core/model/tests/model_test.cpp
#include <cstdio>
#include <filesystem>
#include <string>

#include "core/model/ModelManager.h"
#include "tests/mock_platform/MockPlatform.h"
#include "tests/support/test_framework.h"

using namespace aura;

namespace {
std::filesystem::path writeBytes(const std::string& name, const std::string& bytes) {
  const auto p = std::filesystem::temp_directory_path() / name;
  FILE* f = std::fopen(p.string().c_str(), "wb");
  std::fwrite(bytes.data(), 1, bytes.size(), f);
  std::fclose(f);
  return p;
}
}  // namespace

TEST(Model, MmapLoadAndActivate) {
  test::MockStorage storage(std::filesystem::temp_directory_path());
  model::ModelManager mgr(storage, common::ModelSlot::kStage1);
  writeBytes("aura_model_A.bin", "MODEL-A-bytes-xyz");

  auto staged = mgr.stage("aura_model_A.bin");
  ASSERT_TRUE(static_cast<bool>(staged));
  EXPECT_TRUE(staged.value().valid());
  EXPECT_EQ(staged.value().size, 17u);
  EXPECT_TRUE(static_cast<bool>(mgr.activate(staged.value())));
  EXPECT_EQ(mgr.current().data, staged.value().data);
  EXPECT_EQ(mgr.generation(), 1u);
}

TEST(Model, HotSwapAndRollback) {
  test::MockStorage storage(std::filesystem::temp_directory_path());
  model::ModelManager mgr(storage, common::ModelSlot::kStage1);
  writeBytes("aura_model_A.bin", "AAAA-model-a");
  writeBytes("aura_model_B.bin", "BBBB-model-b-longer");

  auto a = mgr.stage("aura_model_A.bin");
  ASSERT_TRUE(static_cast<bool>(a));
  ASSERT_TRUE(static_cast<bool>(mgr.activate(a.value())));
  const void* aData = mgr.current().data;

  // Hot-swap to B.
  auto b = mgr.stage("aura_model_B.bin");
  ASSERT_TRUE(static_cast<bool>(b));
  ASSERT_TRUE(static_cast<bool>(mgr.activate(b.value())));
  EXPECT_EQ(mgr.current().size, 19u);
  EXPECT_EQ(mgr.generation(), 2u);
  EXPECT_NE(mgr.current().data, aData);

  // Rollback to A (previous known-good).
  ASSERT_TRUE(static_cast<bool>(mgr.rollback()));
  EXPECT_EQ(mgr.current().data, aData);
  EXPECT_EQ(mgr.generation(), 3u);

  // No further previous -> rollback fails.
  auto rb2 = mgr.rollback();
  EXPECT_FALSE(static_cast<bool>(rb2));
  EXPECT_EQ(rb2.error().code, common::ErrorCode::kFailedPrecondition);
}

TEST(Model, RetiredRegionUnmapDeferredWhileInferenceInFlight) {
  test::MockStorage storage(std::filesystem::temp_directory_path());
  model::ModelManager mgr(storage, common::ModelSlot::kStage1);
  writeBytes("aura_model_A.bin", "aaaa");
  writeBytes("aura_model_B.bin", "bbbb");
  writeBytes("aura_model_C.bin", "cccc");

  auto a = mgr.stage("aura_model_A.bin"); (void)mgr.activate(a.value());
  auto b = mgr.stage("aura_model_B.bin"); (void)mgr.activate(b.value());

  // Pin an in-flight inference on the current generation, then swap again: the region
  // retired by this swap must NOT be unmapped until the inference completes.
  const uint32_t gen = mgr.beginInference();
  EXPECT_EQ(gen, 2u);
  auto c = mgr.stage("aura_model_C.bin");
  ASSERT_TRUE(static_cast<bool>(mgr.activate(c.value())));  // retires A's region (2 back)
  EXPECT_EQ(mgr.current().size, 4u);
  // Still valid to read the current model while an inference is in flight (no crash).
  EXPECT_TRUE(mgr.current().valid());
  mgr.endInference();  // now retired regions are unmapped safely
  EXPECT_TRUE(mgr.current().valid());  // active model unaffected by the deferred unmap
}

TEST(Model, MissingFileReturnsNotFound) {
  test::MockStorage storage(std::filesystem::temp_directory_path());
  model::ModelManager mgr(storage, common::ModelSlot::kStage1);
  auto staged = mgr.stage("does_not_exist_12345.bin");
  EXPECT_FALSE(static_cast<bool>(staged));
  EXPECT_EQ(staged.error().code, common::ErrorCode::kNotFound);
}
