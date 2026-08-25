package com.nictunz.universalbacktester;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.security.MessageDigest;
import java.util.Locale;

public final class AppUpdateManager {
    private static final String APK_MIME = "application/vnd.android.package-archive";

    private AppUpdateManager() {}

    public static final class UpdateInfo {
        public final long currentVersionCode;
        public final long versionCode;
        public final String versionName;
        public final String commit;
        public final String sha256;
        public final String apkName;
        public final String packageId;

        UpdateInfo(
                long currentVersionCode,
                long versionCode,
                String versionName,
                String commit,
                String sha256,
                String apkName,
                String packageId
        ) {
            this.currentVersionCode = currentVersionCode;
            this.versionCode = versionCode;
            this.versionName = versionName;
            this.commit = commit;
            this.sha256 = sha256;
            this.apkName = apkName;
            this.packageId = packageId;
        }

        public boolean updateAvailable() {
            return versionCode > currentVersionCode;
        }
    }

    /** Parse an update manifest fetched from the user's server over SSH/SFTP.
     * The private GitHub repository token is never stored on the phone.
     */
    public static UpdateInfo fromManifest(Context context, String manifestText) throws Exception {
        JSONObject manifest = new JSONObject(manifestText);
        if (manifest.optInt("schema_version", 0) != 1 || !manifest.optBoolean("verified", false)) {
            throw new SecurityException("업데이트 manifest 검증 플래그가 올바르지 않습니다.");
        }

        String packageId = manifest.optString("package_id", "");
        if (!context.getPackageName().equals(packageId)) {
            throw new SecurityException("업데이트 package id가 현재 앱과 다릅니다.");
        }

        String sha256 = manifest.optString("sha256", "").toLowerCase(Locale.US);
        if (!sha256.matches("[0-9a-f]{64}")) {
            throw new SecurityException("업데이트 SHA-256 정보가 올바르지 않습니다.");
        }

        String apkName = manifest.optString("apk_name", "");
        if (apkName.isEmpty() || apkName.contains("/") || apkName.contains("\\") || !apkName.endsWith(".apk")) {
            throw new SecurityException("업데이트 APK 파일명이 올바르지 않습니다.");
        }

        long versionCode = manifest.getLong("version_code");
        if (versionCode <= 0) throw new SecurityException("업데이트 version code가 올바르지 않습니다.");

        return new UpdateInfo(
                currentVersionCode(context),
                versionCode,
                manifest.optString("version_name", ""),
                manifest.optString("commit", ""),
                sha256,
                apkName,
                packageId
        );
    }

    public static void verifyDownloaded(UpdateInfo info, File apk) throws Exception {
        if (apk == null || !apk.isFile() || apk.length() <= 0) {
            throw new IllegalStateException("다운로드된 APK 파일이 없습니다.");
        }
        String actual = sha256(apk);
        if (!actual.equalsIgnoreCase(info.sha256)) {
            if (apk.exists()) apk.delete();
            throw new SecurityException("APK SHA-256 검증 실패");
        }
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

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) digest.update(buffer, 0, n);
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : digest.digest()) sb.append(String.format(Locale.US, "%02x", b));
        return sb.toString();
    }
}
