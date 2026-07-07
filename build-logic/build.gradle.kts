// PROJECT AURA — build-logic module. Precompiled Kotlin-DSL convention plugins
// (aura.android.library / aura.android.application) shared by every module so
// Android/Kotlin config is defined once, not duplicated per module (Stage 9 §9).
plugins {
    `kotlin-dsl`
}

dependencies {
    // Make the AGP + Kotlin plugin markers available so the convention plugins can
    // apply `com.android.library` / `org.jetbrains.kotlin.android` by id.
    implementation(libs.android.gradlePlugin)
    implementation(libs.kotlin.gradlePlugin)
}
