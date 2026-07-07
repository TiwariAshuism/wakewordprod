// PROJECT AURA — Gradle settings (Stage 8 §1). Includes every module in the
// production structure; build-logic is a separate included build supplying the
// convention plugins.
pluginManagement {
    includeBuild("build-logic")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "aura"

// Two-layer Kotlin SDK (Stage 9 §9) + reference app.
include(":sdk:kotlin:aura-core-bindings")
include(":sdk:kotlin:aura-sdk")
include(":apps:android")

project(":sdk:kotlin:aura-core-bindings").projectDir = file("sdk/kotlin/aura-core-bindings")
project(":sdk:kotlin:aura-sdk").projectDir = file("sdk/kotlin/aura-sdk")
project(":apps:android").projectDir = file("apps/android")
