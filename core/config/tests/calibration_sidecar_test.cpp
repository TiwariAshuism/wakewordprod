// PROJECT AURA — core/config/tests/calibration_sidecar_test.cpp
//
// Unit tests for the dependency-free labels.json CONFIDENCE-calibration parser.
#include <cstring>
#include <string>

#include "core/config/calibration_sidecar.h"
#include "tests/support/test_framework.h"

using namespace aura::config;

namespace {
CalibrationSidecar parse(const std::string& s) {
  return parseCalibrationSidecar(s.c_str(), s.size());
}
}  // namespace

// A well-formed Platt block: per-stage a/b parsed, method propagated to both stages.
TEST(CalibrationSidecar, ValidPlattParsed) {
  const std::string json =
      "{\"wake_word\":\"hey aura\",\"arch\":\"dscnn\",\"num_classes\":2,\"target_index\":1,"
      "\"labels\":[\"not\",\"hey aura\"],"
      "\"calibration\":{\"method\":\"platt\","
      "\"stage1\":{\"a\":2.0,\"b\":-1.0,\"temperature\":1.0},"
      "\"stage2\":{\"a\":1.5,\"b\":0.25,\"temperature\":2.0}}}";
  const auto c = parse(json);
  EXPECT_EQ(c.stage1.method, StageCalibration::kPlatt);
  EXPECT_NEAR(c.stage1.plattA, 2.0f, 1e-6);
  EXPECT_NEAR(c.stage1.plattB, -1.0f, 1e-6);
  EXPECT_EQ(c.stage2.method, StageCalibration::kPlatt);
  EXPECT_NEAR(c.stage2.plattA, 1.5f, 1e-6);
  EXPECT_NEAR(c.stage2.plattB, 0.25f, 1e-6);
  EXPECT_NEAR(c.stage2.temperature, 2.0f, 1e-6);
}

// A temperature block: per-stage T parsed independently.
TEST(CalibrationSidecar, ValidTemperatureParsed) {
  const std::string json =
      "{\"calibration\":{\"method\":\"temperature\","
      "\"stage1\":{\"a\":1.0,\"b\":0.0,\"temperature\":2.5},"
      "\"stage2\":{\"a\":1.0,\"b\":0.0,\"temperature\":3.0}}}";
  const auto c = parse(json);
  EXPECT_EQ(c.stage1.method, StageCalibration::kTemperature);
  EXPECT_NEAR(c.stage1.temperature, 2.5f, 1e-6);
  EXPECT_EQ(c.stage2.method, StageCalibration::kTemperature);
  EXPECT_NEAR(c.stage2.temperature, 3.0f, 1e-6);
}

// method:"none" => identity (params ignored / stay at identity semantics).
TEST(CalibrationSidecar, NoneMethodIsIdentity) {
  const std::string json =
      "{\"calibration\":{\"method\":\"none\","
      "\"stage1\":{\"a\":5.0,\"b\":5.0,\"temperature\":5.0}}}";
  const auto c = parse(json);
  EXPECT_EQ(c.stage1.method, StageCalibration::kNone);
  EXPECT_EQ(c.stage2.method, StageCalibration::kNone);
}

// Absent calibration block => full identity for both stages.
TEST(CalibrationSidecar, MissingBlockIsIdentity) {
  const std::string json = "{\"wake_word\":\"hey aura\",\"num_classes\":2,\"target_index\":1}";
  const auto c = parse(json);
  EXPECT_EQ(c.stage1.method, StageCalibration::kNone);
  EXPECT_NEAR(c.stage1.plattA, 1.0f, 1e-6);
  EXPECT_NEAR(c.stage1.plattB, 0.0f, 1e-6);
  EXPECT_NEAR(c.stage1.temperature, 1.0f, 1e-6);
  EXPECT_EQ(c.stage2.method, StageCalibration::kNone);
  EXPECT_NEAR(c.stage2.temperature, 1.0f, 1e-6);
}

// Truncated / malformed JSON => identity (no crash, no partial garbage).
TEST(CalibrationSidecar, MalformedIsIdentity) {
  const std::string json = "{\"calibration\":{\"method\":\"platt\",\"stage1\":{\"a\":";  // truncated
  const auto c = parse(json);
  EXPECT_NEAR(c.stage1.plattA, 1.0f, 1e-6);  // unbalanced stage1 object -> identity
  EXPECT_NEAR(c.stage1.plattB, 0.0f, 1e-6);
  EXPECT_EQ(c.stage1.method, StageCalibration::kNone);
}

// Empty / null buffer => identity.
TEST(CalibrationSidecar, EmptyBufferIsIdentity) {
  const auto c = parseCalibrationSidecar(nullptr, 0);
  EXPECT_EQ(c.stage1.method, StageCalibration::kNone);
  EXPECT_NEAR(c.stage1.plattA, 1.0f, 1e-6);
}

// Only stage1 present: stage2 falls back to identity even with a set method.
TEST(CalibrationSidecar, PartialStagesFallBackToIdentity) {
  const std::string json =
      "{\"calibration\":{\"method\":\"platt\","
      "\"stage1\":{\"a\":2.0,\"b\":0.5,\"temperature\":1.0}}}";
  const auto c = parse(json);
  EXPECT_EQ(c.stage1.method, StageCalibration::kPlatt);
  EXPECT_NEAR(c.stage1.plattA, 2.0f, 1e-6);
  EXPECT_EQ(c.stage2.method, StageCalibration::kNone);  // stage2 absent -> identity
  EXPECT_NEAR(c.stage2.plattA, 1.0f, 1e-6);
}
