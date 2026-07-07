// PROJECT AURA — :sdk:kotlin:aura-core-bindings (the JNI binding layer, Stage 9 §9).
// Hand-written for v0 (no codegen tool exists yet — ADR-Binding "specific tool
// Deferred"); kept thin/mechanical so generated code can replace it later without
// touching :aura-sdk (flagged in REPORT.md). Drives the core/ CMake build via
// externalNativeBuild (Stage 8 §1) and consumes Oboe + ONNX Runtime as Prefab AARs.
plugins {
    id("aura.android.library")
}

android {
    namespace = "com.getnyx.aura.bindings"
    ndkVersion = libs.versions.ndk.get()

    defaultConfig {
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DAURA_PLATFORM=android",
                    "-DAURA_ENABLE_ONNXRUNTIME=ON",
                    "-DAURA_BUILD_TESTS=OFF",
                    "-DAURA_ENABLE_DEBUG_LOCK_INSTRUMENTATION=ON",
                    // Oboe's Prefab AAR requires the shared libc++ (else CXX1212). Match it.
                    "-DANDROID_STL=c++_shared",
                )
                cppFlags += "-std=c++20"
                targets += "aura_jni"
            }
            ndk {
                // arm64-v8a only: the target devices (e.g. Realme 8 / RMX3085) are arm64, and the
                // Oboe Prefab AAR has no compatible x86_64 library. Re-add "x86_64" for the emulator
                // only if a matching Oboe x86_64 prefab is available (Stage 9 §8.1).
                abiFilters += listOf("arm64-v8a")
            }
        }
    }

    externalNativeBuild {
        cmake {
            // Single CMake source of truth at the repo root (Stage 8 §1).
            path = file("../../../CMakeLists.txt")
            version = libs.versions.cmake.get()
        }
    }

    buildFeatures {
        prefab = true  // exposes Oboe + ONNX Runtime headers/.so to CMake find_package
    }
}

dependencies {
    implementation(libs.oboe)
    implementation(libs.onnxruntime.android)
}
