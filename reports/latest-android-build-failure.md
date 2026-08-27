# Latest Android build failure

- Source commit: 9c1c488f8213ee50c07abfea179aea37e2e59c20
- Run: https://github.com/nictunz/universal-trading-bot/actions/runs/33059411498

~~~text
Starting a Gradle Daemon (subsequent builds will be faster)
> Task :app:preBuild UP-TO-DATE
> Task :app:preDebugBuild UP-TO-DATE
> Task :app:mergeDebugNativeDebugMetadata NO-SOURCE
> Task :app:extractDebugPythonBuildPackages

> Task :app:installDebugPythonRequirements
Chaquopy: Installing for arm64-v8a
Looking in indexes: https://pypi.org/simple, https://chaquo.com/pypi-13.1
Collecting numpy>=1.24
  Downloading https://chaquo.com/pypi-13.1/numpy/numpy-1.26.2-0-cp311-cp311-android_21_arm64_v8a.whl (5.0 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5.0/5.0 MB 4.1 MB/s  0:00:01
Collecting pandas>=2.0
  Downloading https://chaquo.com/pypi-13.1/pandas/pandas-2.1.3-1-cp311-cp311-android_24_arm64_v8a.whl (11.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 11.3/11.3 MB 25.1 MB/s  0:00:00
Collecting requests>=2.32
  Using cached requests-2.34.2-py3-none-any.whl.metadata (4.8 kB)
Collecting chaquopy-openblas>=0.2.20 (from numpy>=1.24)
  Downloading https://chaquo.com/pypi-13.1/chaquopy-openblas/chaquopy_openblas-0.2.20-5-py3-none-android_21_arm64_v8a.whl (4.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.3/4.3 MB 35.3 MB/s  0:00:00
Collecting chaquopy-libcxx>=11000 (from numpy>=1.24)
  Downloading https://chaquo.com/pypi-13.1/chaquopy-libcxx/chaquopy_libcxx-180000-0-py3-none-android_24_arm64_v8a.whl (413 kB)
Collecting python-dateutil>=2.8.2 (from pandas>=2.0)
  Using cached python_dateutil-2.9.0.post0-py2.py3-none-any.whl.metadata (8.4 kB)
Collecting pytz>=2020.1 (from pandas>=2.0)
  Using cached pytz-2026.3.post1-py2.py3-none-any.whl.metadata (22 kB)
Collecting tzdata>=2022.1 (from pandas>=2.0)
  Downloading tzdata-2026.3-py2.py3-none-any.whl.metadata (1.4 kB)
Collecting charset_normalizer<4,>=2 (from requests>=2.32)
  Downloading charset_normalizer-3.5.1-py3-none-any.whl.metadata (45 kB)
Collecting idna<4,>=2.5 (from requests>=2.32)
  Downloading idna-3.19-py3-none-any.whl.metadata (9.2 kB)
Collecting urllib3<3,>=1.26 (from requests>=2.32)
  Using cached urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
Collecting certifi>=2023.5.7 (from requests>=2.32)
  Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
Collecting chaquopy-libgfortran>=4.9 (from chaquopy-openblas>=0.2.20->numpy>=1.24)
  Downloading https://chaquo.com/pypi-13.1/chaquopy-libgfortran/chaquopy_libgfortran-4.9-0-py3-none-android_21_arm64_v8a.whl (495 kB)
Collecting six>=1.5 (from python-dateutil>=2.8.2->pandas>=2.0)
  Using cached six-1.17.0-py2.py3-none-any.whl.metadata (1.7 kB)
Using cached requests-2.34.2-py3-none-any.whl (73 kB)
Downloading charset_normalizer-3.5.1-py3-none-any.whl (68 kB)
Downloading idna-3.19-py3-none-any.whl (68 kB)
Using cached urllib3-2.7.0-py3-none-any.whl (131 kB)
Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
Using cached python_dateutil-2.9.0.post0-py2.py3-none-any.whl (229 kB)
Using cached pytz-2026.3.post1-py2.py3-none-any.whl (508 kB)
Using cached six-1.17.0-py2.py3-none-any.whl (11 kB)
Downloading tzdata-2026.3-py2.py3-none-any.whl (348 kB)
Installing collected packages: pytz, chaquopy-libgfortran, chaquopy-libcxx, urllib3, tzdata, six, idna, charset_normalizer, chaquopy-openblas, certifi, requests, python-dateutil, numpy, pandas

Successfully installed certifi-2026.7.22 chaquopy-libcxx-180000 chaquopy-libgfortran-4.9 chaquopy-openblas-0.2.20 charset_normalizer-3.5.1 idna-3.19 numpy-1.26.2 pandas-2.1.3 python-dateutil-2.9.0.post0 pytz-2026.3.post1 requests-2.34.2 six-1.17.0 tzdata-2026.3 urllib3-2.7.0

> Task :app:mergeDebugPythonSources
> Task :app:generateDebugPythonProxies
> Task :app:javaPreCompileDebug
> Task :app:generateDebugResValues
> Task :app:checkDebugAarMetadata
> Task :app:mapDebugSourceSetPaths
> Task :app:generateDebugResources
> Task :app:createDebugCompatibleScreenManifests
> Task :app:extractDeepLinksDebug
> Task :app:mergeDebugResources
> Task :app:processDebugMainManifest
> Task :app:packageDebugResources
> Task :app:parseDebugLocalResources
> Task :app:processDebugManifest
> Task :app:mergeDebugShaders
> Task :app:processDebugManifestForPackage
> Task :app:compileDebugShaders NO-SOURCE
> Task :app:generateDebugAssets UP-TO-DATE
> Task :app:processDebugResources
> Task :app:generateDebugPythonMiscAssets

> Task :app:compileDebugJavaWithJavac
Note: Some input files use or override a deprecated API.
Note: Recompile with -Xlint:deprecation for details.

> Task :app:generateDebugPythonRequirementsAssets
> Task :app:generateDebugPythonSourceAssets
> Task :app:generateDebugPythonBuildAssets
> Task :app:mergeDebugAssets
> Task :app:compressDebugAssets
> Task :app:desugarDebugFileDependencies
> Task :app:dexBuilderDebug
> Task :app:processDebugJavaRes NO-SOURCE
> Task :app:mergeDebugGlobalSynthetics
> Task :app:checkDebugDuplicateClasses
> Task :app:mergeDebugJavaResource
> Task :app:mergeExtDexDebug
> Task :app:mergeLibDexDebug
> Task :app:mergeProjectDexDebug
> Task :app:generateDebugPythonJniLibs
> Task :app:mergeDebugJniLibFolders
> Task :app:mergeDebugNativeLibs
> Task :app:validateSigningDebug
> Task :app:writeDebugAppMetadata
> Task :app:writeDebugSigningConfigVersions

> Task :app:stripDebugDebugSymbols
Unable to strip the following libraries, packaging them as they are: libchaquopy_java.so, libcrypto_chaquopy.so, libcrypto_python.so, libpython3.11.so, libsqlite3_chaquopy.so, libsqlite3_python.so, libssl_chaquopy.so, libssl_python.so.

> Task :app:packageDebug
> Task :app:createDebugApkListingFileRedirect
> Task :app:assembleDebug
gradle/actions: Writing build results to /home/runner/work/_temp/.gradle-actions/build-results/__run_5-1787823527693.json
[Incubating] Problems report is available at: file:///home/runner/work/universal-trading-bot/universal-trading-bot/android/build/reports/problems/problems-report.html

BUILD SUCCESSFUL in 53s
43 actionable tasks: 43 executed
~~~
