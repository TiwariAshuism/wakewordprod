// PROJECT AURA — tests/support/test_framework.h
//
// The project's tests are written against the GoogleTest API (Stage 9 §5 uses
// TEST()/ASSERT_EQ/EXPECT_EQ). In CI they compile against real GoogleTest
// (FetchContent in CMake). For dependency-free host verification (e.g. a plain
// g++ invocation with no gtest installed), define AURA_USE_MICROGTEST to get a
// minimal drop-in shim implementing just the macros these tests use.
#ifndef AURA_TESTS_SUPPORT_TEST_FRAMEWORK_H
#define AURA_TESTS_SUPPORT_TEST_FRAMEWORK_H

#if defined(AURA_USE_MICROGTEST)

#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

namespace microgtest
{

  struct TestCase
  {
    std::string suite;
    std::string name;
    std::function<void(bool &)> fn;
  };

  inline std::vector<TestCase> &registry()
  {
    static std::vector<TestCase> r;
    return r;
  }

  struct Registrar
  {
    Registrar(const char *suite, const char *name, std::function<void(bool &)> fn)
    {
      registry().push_back({suite, name, std::move(fn)});
    }
  };

  inline int runAll()
  {
    int failed = 0;
    for (auto &tc : registry())
    {
      bool ok = true;
      std::printf("[ RUN      ] %s.%s\n", tc.suite.c_str(), tc.name.c_str());
      tc.fn(ok);
      if (ok)
      {
        std::printf("[       OK ] %s.%s\n", tc.suite.c_str(), tc.name.c_str());
      }
      else
      {
        std::printf("[  FAILED  ] %s.%s\n", tc.suite.c_str(), tc.name.c_str());
        ++failed;
      }
    }
    std::printf("[==========] %zu tests, %d failed\n", registry().size(), failed);
    return failed == 0 ? 0 : 1;
  }

} // namespace microgtest

#define TEST(suite, name)                                            \
  static void suite##_##name##_body(bool &_aura_ok);                 \
  static microgtest::Registrar suite##_##name##_reg(                 \
      #suite, #name, [](bool &_ok) { suite##_##name##_body(_ok); }); \
  static void suite##_##name##_body([[maybe_unused]] bool &_aura_ok)

#define AURA_FAIL_(msg)                                           \
  do                                                              \
  {                                                               \
    std::printf("    FAIL %s:%d: %s\n", __FILE__, __LINE__, msg); \
    _aura_ok = false;                                             \
  } while (0)

#define EXPECT_TRUE(c)                   \
  do                                     \
  {                                      \
    if (!(c))                            \
      AURA_FAIL_("EXPECT_TRUE(" #c ")"); \
  } while (0)
#define EXPECT_FALSE(c)                   \
  do                                      \
  {                                       \
    if ((c))                              \
      AURA_FAIL_("EXPECT_FALSE(" #c ")"); \
  } while (0)
#define EXPECT_EQ(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) == (b)))                         \
      AURA_FAIL_("EXPECT_EQ(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_NE(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) != (b)))                         \
      AURA_FAIL_("EXPECT_NE(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_GE(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) >= (b)))                         \
      AURA_FAIL_("EXPECT_GE(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_GT(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) > (b)))                          \
      AURA_FAIL_("EXPECT_GT(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_LE(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) <= (b)))                         \
      AURA_FAIL_("EXPECT_LE(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_LT(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) < (b)))                          \
      AURA_FAIL_("EXPECT_LT(" #a ", " #b ")"); \
  } while (0)
#define EXPECT_NEAR(a, b, tol)                                \
  do                                                          \
  {                                                           \
    if (std::fabs((double)(a) - (double)(b)) > (double)(tol)) \
      AURA_FAIL_("EXPECT_NEAR(" #a ", " #b ")");              \
  } while (0)

#define ASSERT_TRUE(c)                   \
  do                                     \
  {                                      \
    if (!(c))                            \
    {                                    \
      AURA_FAIL_("ASSERT_TRUE(" #c ")"); \
      return;                            \
    }                                    \
  } while (0)
#define ASSERT_FALSE(c)                   \
  do                                      \
  {                                       \
    if ((c))                              \
    {                                     \
      AURA_FAIL_("ASSERT_FALSE(" #c ")"); \
      return;                             \
    }                                     \
  } while (0)
#define ASSERT_EQ(a, b)                        \
  do                                           \
  {                                            \
    if (!((a) == (b)))                         \
    {                                          \
      AURA_FAIL_("ASSERT_EQ(" #a ", " #b ")"); \
      return;                                  \
    }                                          \
  } while (0)

#if defined(AURA_MICROGTEST_MAIN)
int main() { return microgtest::runAll(); }
#endif

#else // real GoogleTest
#include <gtest/gtest.h>
#endif

#endif // AURA_TESTS_SUPPORT_TEST_FRAMEWORK_H
