plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "com.nictunz.universalbacktester"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.nictunz.universalbacktester"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
    // 0.2.25+ includes Java 24 multi-release classes which older Android Jetifier/ASM
    // cannot read. 0.2.24 avoids class-file major version 68 and still supports
    // modern RSA SHA-2 SSH authentication used by the upload bridge.
    implementation("com.github.mwiede:jsch:0.2.24")
}
