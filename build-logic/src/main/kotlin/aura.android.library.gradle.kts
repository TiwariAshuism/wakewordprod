// PROJECT AURA — convention plugin: Android library module (Stage 9 §9).
// Applied by :sdk:kotlin:* modules. Centralizes SDK levels, Java 17, and Kotlin
// jvmTarget so no module hardcodes them. Versions come from the catalog.
import com.android.build.gradle.LibraryExtension
import org.gradle.api.JavaVersion
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.getByType
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

private val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
private fun version(alias: String) = libs.findVersion(alias).get().requiredVersion

extensions.configure<LibraryExtension> {
    compileSdk = version("compileSdk").toInt()
    defaultConfig {
        minSdk = version("minSdk").toInt()
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

extensions.configure<KotlinAndroidProjectExtension> {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}
