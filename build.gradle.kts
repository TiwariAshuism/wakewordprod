// PROJECT AURA — root build script. Intentionally thin: all shared configuration
// lives in build-logic convention plugins (Stage 8 §1 / Stage 9 §9), not here and
// not duplicated across module build files.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
}
