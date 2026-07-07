// PROJECT AURA — :apps:android (reference/demo app, Stage 7 §1 apps/android).
// Thin shell over :sdk:kotlin:aura-sdk — NOT the SDK release artifact. Depends only
// on the SDK wrapper, never on the bindings or core/ directly (Stage 7 §2).
plugins {
    id("aura.android.application")
}

android {
    namespace = "com.getnyx.aura.app"

    defaultConfig {
        applicationId = "com.getnyx.aura.app"
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }
}

dependencies {
    implementation(project(":sdk:kotlin:aura-sdk"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
}
