plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

val envVersionCode = System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull() ?: 1
val envVersionName = System.getenv("ANDROID_VERSION_NAME")?.takeIf { it.isNotBlank() } ?: "1.0.0"
val releaseKeystorePath = System.getenv("ANDROID_KEYSTORE_PATH")?.takeIf { it.isNotBlank() }
val releaseStorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: ""
val releaseKeyAlias = System.getenv("ANDROID_KEY_ALIAS")?.takeIf { it.isNotBlank() } ?: "universal"
val releaseKeyPassword = System.getenv("ANDROID_KEY_PASSWORD")?.takeIf { it.isNotBlank() } ?: releaseStorePassword

android {
    namespace = "com.nictunz.universalbacktester"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.nictunz.universalbacktester"
        minSdk = 24
        targetSdk = 35
        versionCode = envVersionCode
        versionName = envVersionName

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        if (releaseKeystorePath != null) {
            create("release") {
                storeFile = file(releaseKeystorePath)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (releaseKeystorePath != null) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            install("numpy>=1.24")
            install("pandas>=2.0")
            install("requests>=2.32")
        }
    }
}

dependencies {
    implementation("androidx.core:core:1.15.0")
    // 0.2.25+ includes Java 24 multi-release classes which older Android Jetifier/ASM
    // cannot read. 0.2.24 avoids class-file major version 68 and still supports
    // modern RSA SHA-2 SSH authentication used by the upload bridge.
    implementation("com.github.mwiede:jsch:0.2.24")
}
