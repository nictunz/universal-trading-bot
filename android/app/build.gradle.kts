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
            install("python-dotenv>=1.0")
            install("pydantic>=2.0")
            install("pydantic-settings>=2.0")
            install("ccxt>=4.0")
            install("paramiko>=3.5")
        }
    }
}

dependencies {
    implementation("com.google.android.material:material:1.12.0")
}
