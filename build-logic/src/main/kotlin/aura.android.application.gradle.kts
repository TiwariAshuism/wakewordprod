// PROJECT AURA — convention plugin: Android application module (Stage 9 §9).
// Applied by :apps:android. Same shared SDK/Java/Kotlin config as the library
// convention plugin, for the app target.
import com.android.build.gradle.internal.dsl.BaseAppModuleExtension
import org.gradle.api.JavaVersion
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.getByType
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

private val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
private fun version(alias: String) = libs.findVersion(alias).get().requiredVersion

extensions.configure<BaseAppModuleExtension> {
    compileSdk = version("compileSdk").toInt()
    defaultConfig {
        minSdk = version("minSdk").toInt()
        targetSdk = version("targetSdk").toInt()
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
