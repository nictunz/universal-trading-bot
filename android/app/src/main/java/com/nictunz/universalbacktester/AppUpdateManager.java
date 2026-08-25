package com.nictunz.universalbacktester;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

public final class AppUpdateManager {
    private static final String RELEASES_API =
            "https://api.github.com/repos/nictunz/universal-trading-bot/releases?per_page=20";
    private static final String MANIFEST_ASSET = "android-update.json";
    private static final String APK_MIME = "application/vnd.android.package-archive";

    private AppUpdateManager() {}

    public static final class UpdateInfo {
        public final long currentVersionCode;
        public final long versionCode;
        public final String versionName;
        public final String commit;
        public final String sha256;
        public final String apkUrl;
        public final String packageId;

        UpdateInfo(long currentVersionCode, long versionCode, String versionName,
                   String commit, String sha256, String apkUrl, String packageId) {
            this.currentVersionCode = currentVersionCode;
            this.versionCode = versionCode;
            this.versionName = versionName;
            this.commit = commit;
            this.sha256 = sha256;
            this.apkUrl = apkUrl;
            this.packageId = packageId;
        }

        public boolean updateAvailable() {
            return versionCode > currentVersionCode;
        }
    }

    public static UpdateInfo checkLatest(Context context) throws Exception {
        JSONArray releases = new JSONArray(getText(RELEASES_API));
        JSONObject selected = null;
        for (int r = 0; r < releases.length(); r++) {
            JSONObject release = releases.optJSONObject(r);
            if (release == null || release.optBoolean("draft", false)) continue;
            JSONArray assets = release.optJSONArray("assets");
            if (assets == null) continue;
            if (assetUrl(assets, MANIFEST_ASSET).isEmpty()) continue;
            selected = release;
            break;
        }
        if (selected == null) {
            throw new IllegalStateException("아직 검증된 Android 자동업데이트 릴리스가 없습니다.");
        }

        JSONArray assets = selected.getJSONArray("assets");
        String manifestUrl = assetUrl(assets, MANIFEST_ASSET);
        JSONObject manifest = new JSONObject(getText(manifestUrl));
        if (!manifest.optBoolean("verified", false)) {
            throw new SecurityException("Android 업데이트 manifest가 verified 상태가 아닙니다.");
        }

        String apkName = manifest.optString("apk_name", "UniversalTradingBacktester-Android.apk");
        String apkUrl = assetUrl(assets, apkName);
        if (apkUrl.isEmpty()) throw new IllegalStateException("업데이트 APK 자산을 찾지 못했습니다.");

        String packageId = manifest.optString("package_id", "");
        if (!context.getPackageName().equals(packageId)) {
            throw new SecurityException("업데이트 package id가 현재 앱과 다릅니다.");
        }
        String sha256 = manifest.optString("sha256", "").toLowerCase(Locale.US);
        if (!sha256.matches("[0-9a-f]{64}")) {
            throw new SecurityException("업데이트 SHA-256 정보가 올바르지 않습니다.");
        }

        return new UpdateInfo(
                currentVersionCode(context),
                manifest.getLong("version_code"),
                manifest.optString("version_name", ""),
                manifest.optString("commit", ""),
                sha256,
                apkUrl,
                packageId
        );
    }

    private static String assetUrl(JSONArray assets, String name) {
        for (int i = 0; i < assets.length(); i++) {
            JSONObject asset = assets.optJSONObject(i);
            if (asset != null && name.equals(asset.optString("name"))) {
                return asset.optString("browser_download_url", "");
            }
        }
        return "";
    }

    public static File downloadVerified(Context context, UpdateInfo info) throws Exception {
        File cache = context.getExternalCacheDir();
        if (cache == null) cache = context.getCacheDir();
        File root = new File(cache, "updates");
        if (!root.exists() && !root.mkdirs()) {
            throw new IllegalStateException("업데이트 임시 폴더를 만들 수 없습니다.");
        }
        File target = new File(root, "UniversalTradingBacktester-Android.apk");
        File temp = new File(root, target.getName() + ".downloading");
        if (temp.exists()) temp.delete();

        HttpURLConnection conn = open(info.apkUrl);
        int status = conn.getResponseCode();
        if (status < 200 || status >= 300) {
            String error = readResponse(conn, status);
            conn.disconnect();
            throw new IllegalStateException("APK 다운로드 HTTP " + status + ": " + error);
        }
        try (BufferedInputStream in = new BufferedInputStream(conn.getInputStream());
             FileOutputStream out = new FileOutputStream(temp)) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
        } finally {
            conn.disconnect();
        }

        String actual = sha256(temp);
        if (!actual.equalsIgnoreCase(info.sha256)) {
            temp.delete();
            throw new SecurityException("APK SHA-256 검증 실패");
        }
        if (target.exists() && !target.delete()) {
            temp.delete();
            throw new IllegalStateException("기존 업데이트 파일을 지울 수 없습니다.");
        }
        if (!temp.renameTo(target)) {
            temp.delete();
            throw new IllegalStateException("검증된 APK 파일 이동 실패");
        }
        return target;
    }

    public static boolean requestInstall(Activity activity, File apk) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !activity.getPackageManager().canRequestPackageInstalls()) {
            Intent permission = new Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + activity.getPackageName())
            );
            activity.startActivity(permission);
            return false;
        }

        Uri uri = FileProvider.getUriForFile(
                activity,
                activity.getPackageName() + ".fileprovider",
                apk
        );
        Intent install = new Intent(Intent.ACTION_VIEW);
        install.setDataAndType(uri, APK_MIME);
        install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        activity.startActivity(install);
        return true;
    }

    public static long currentVersionCode(Context context) throws Exception {
        PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? info.getLongVersionCode()
                : info.versionCode;
    }

    public static String currentVersionName(Context context) {
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            return info.versionName == null ? "" : info.versionName;
        } catch (Exception e) {
            return "";
        }
    }

    private static String getText(String url) throws Exception {
        HttpURLConnection conn = open(url);
        int status = conn.getResponseCode();
        String text = readResponse(conn, status);
        conn.disconnect();
        if (status < 200 || status >= 300) {
            throw new IllegalStateException("GitHub 업데이트 확인 HTTP " + status + ": " + text);
        }
        return text;
    }

    private static HttpURLConnection open(String target) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(target).openConnection();
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(30000);
        conn.setInstanceFollowRedirects(true);
        conn.setRequestProperty("Accept", "application/vnd.github+json, application/octet-stream");
        conn.setRequestProperty("User-Agent", "UniversalTradingBot-Android-Updater/1");
        return conn;
    }

    private static String readResponse(HttpURLConnection conn, int status) throws Exception {
        InputStream stream = status >= 200 && status < 300 ? conn.getInputStream() : conn.getErrorStream();
        if (stream == null) return "";
        BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) sb.append(line);
        reader.close();
        return sb.toString();
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (java.io.FileInputStream in = new java.io.FileInputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) digest.update(buffer, 0, n);
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : digest.digest()) sb.append(String.format(Locale.US, "%02x", b));
        return sb.toString();
    }
}
