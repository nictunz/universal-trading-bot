package com.nictunz.universalbacktester;

import com.jcraft.jsch.ChannelSftp;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.Session;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

/** Private-repo-safe Android update transport.
 *
 * The phone never stores a GitHub token. GitHub Actions copies only a verified,
 * stable-signed APK plus android-update.json to the user's server. The app reads
 * those files with the same phone SSH key already used by the market relay.
 */
public final class ServerUpdateBridge {
    private ServerUpdateBridge() {}

    public static String readManifest(
            String host,
            String username,
            String remoteDir,
            String keyPath
    ) throws Exception {
        String path = updateRoot(remoteDir) + "/android-update.json";
        Session session = connect(host, username, keyPath);
        ChannelSftp sftp = null;
        try {
            sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
            try (InputStream in = sftp.get(path); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
                return out.toString(StandardCharsets.UTF_8.name());
            }
        } finally {
            if (sftp != null && sftp.isConnected()) sftp.disconnect();
            session.disconnect();
        }
    }

    public static String downloadApk(
            String host,
            String username,
            String remoteDir,
            String apkName,
            String localCacheDir,
            String keyPath
    ) throws Exception {
        validateApkName(apkName);
        File root = new File(localCacheDir, "updates");
        if (!root.exists() && !root.mkdirs()) {
            throw new IllegalStateException("업데이트 캐시 폴더를 만들 수 없습니다.");
        }
        File target = new File(root, apkName);
        File temp = new File(root, apkName + ".downloading");
        if (temp.exists()) temp.delete();

        String remote = updateRoot(remoteDir) + "/" + apkName;
        Session session = connect(host, username, keyPath);
        ChannelSftp sftp = null;
        try {
            sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
            try (InputStream in = sftp.get(remote); FileOutputStream out = new FileOutputStream(temp)) {
                byte[] buffer = new byte[64 * 1024];
                int n;
                while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
            }
        } catch (Exception e) {
            temp.delete();
            throw e;
        } finally {
            if (sftp != null && sftp.isConnected()) sftp.disconnect();
            session.disconnect();
        }

        if (target.exists() && !target.delete()) {
            temp.delete();
            throw new IllegalStateException("기존 업데이트 APK를 지울 수 없습니다.");
        }
        if (!temp.renameTo(target)) {
            temp.delete();
            throw new IllegalStateException("업데이트 APK 파일 이동 실패");
        }
        return target.getAbsolutePath();
    }

    private static Session connect(String host, String username, String keyPath) throws Exception {
        if (host == null || host.trim().isEmpty()) throw new IllegalArgumentException("서버 주소가 비어 있습니다.");
        if (username == null || username.trim().isEmpty()) throw new IllegalArgumentException("서버 사용자가 비어 있습니다.");
        File key = new File(keyPath == null ? "" : keyPath);
        if (!key.isFile()) throw new IllegalStateException("휴대폰 SSH 키가 없습니다. 먼저 SSH 키 준비를 실행하세요.");

        JSch jsch = new JSch();
        jsch.addIdentity(key.getAbsolutePath());
        Session session = jsch.getSession(username.trim(), host.trim(), 22);
        Properties config = new Properties();
        config.put("StrictHostKeyChecking", "no");
        config.put("PreferredAuthentications", "publickey");
        session.setConfig(config);
        session.connect(15000);
        return session;
    }

    private static String updateRoot(String remoteDir) {
        String root = remoteDir == null ? "" : remoteDir.trim();
        if (root.isEmpty()) throw new IllegalArgumentException("서버 캐시 폴더가 비어 있습니다.");
        while (root.endsWith("/")) root = root.substring(0, root.length() - 1);
        return root + "/android-updates";
    }

    private static void validateApkName(String apkName) {
        if (apkName == null || apkName.isEmpty()
                || apkName.contains("/") || apkName.contains("\\")
                || !apkName.endsWith(".apk")) {
            throw new IllegalArgumentException("업데이트 APK 파일명이 올바르지 않습니다.");
        }
    }
}
