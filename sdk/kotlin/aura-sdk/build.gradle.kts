// PROJECT AURA — :sdk:kotlin:aura-sdk (idiomatic Kotlin wrapper, Stage 9 §9).
// Hand-written ergonomics layer over the generated/hand-written binding layer.
// This is where language-appropriate API (Flow<DetectionEvent>) lives; it depends
// on :aura-core-bindings and never on core/ or third_party/ directly (Stage 7 §2).
plugins {
    id("aura.android.library")
}

android {
    namespace = "com.getnyx.aura.sdk"
}

dependencies {
    api(project(":sdk:kotlin:aura-core-bindings"))
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)
}
