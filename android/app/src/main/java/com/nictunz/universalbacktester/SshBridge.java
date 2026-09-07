package com.nictunz.universalbacktester;

import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.ChannelSftp;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.KeyPair;
import com.jcraft.jsch.Session;
import com.jcraft.jsch.SftpException;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Properties;
import java.util.TimeZone;
import java.util.Vector;

public final class SshBridge {
    private SshBridge() {}

    public static String ensureKey(String appFilesDir) throws Exception {
        File root = new File(appFilesDir, "ssh");
        if (!root.exists() && !root.mkdirs()) {
            throw new IllegalStateException("SSH 키 폴더를 만들 수 없습니다: " + root);
        }

        File privateFile = new File(root, "android_upload_rsa");
        File publicFile = new File(root, "android_upload_rsa.pub");
        if (!privateFile.exists() || !publicFile.exists()) {
            if (privateFile.exists()) privateFile.delete();
            if (publicFile.exists()) publicFile.delete();

            JSch jsch = new JSch();
            KeyPair pair = KeyPair.genKeyPair(jsch, KeyPair.RSA, 3072);
            try (FileOutputStream out = new FileOutputStream(privateFile)) {
                pair.writePrivateKey(out);
            }
            try (FileOutputStream out = new FileOutputStream(publicFile)) {
                pair.writePublicKey(out, "universal-backtester-android");
            }
            pair.dispose();
        }

        JSONObject obj = new JSONObject();
        obj.put("private_key", privateFile.getAbsolutePath());
        obj.put("public_key", readText(publicFile).trim());
        return obj.toString();
    }

    public static String testConnection(String host, String username, String keyPath) throws Exception {
        Session session = connect(host, username, keyPath);
        try {
            return "SSH_OK " + username + "@" + host;
        } finally {
            session.disconnect();
        }
    }

    public static String inspectServerCache(
            String host,
            String username,
            String remoteDir,
            String keyPath
    ) throws Exception {
        Session session = connect(host, username, keyPath);
        ChannelSftp sftp = null;
        try {
            sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
            @SuppressWarnings("unchecked")
            Vector<ChannelSftp.LsEntry> entries = sftp.ls(remoteDir);
            JSONArray files = new JSONArray();
            for (ChannelSftp.LsEntry entry : entries) {
                String name = entry.getFilename();
                if (".".equals(name) || "..".equals(name) || entry.getAttrs().isDir()) continue;
                boolean relevant = name.endsWith(".db")
                        || (name.startsWith("latest-") && name.endsWith(".json"))
                        || name.endsWith(".upload-manifest.json");
                if (!relevant) continue;
                JSONObject item = new JSONObject();
                item.put("name", name);
                item.put("size", entry.getAttrs().getSize());
                item.put("modified_epoch", entry.getAttrs().getMTime());
                files.put(item);
            }
            JSONObject out = new JSONObject();
            out.put("ok", true);
            out.put("server", username + "@" + host);
            out.put("remote_dir", remoteDir);
            out.put("count", files.length());
            out.put("files", files);
            return out.toString();
        } finally {
            if (sftp != null && sftp.isConnected()) sftp.disconnect();
            session.disconnect();
        }
    }

    public static String readStrategySettings(
            String host,
            String username,
            String remoteDir,
            String keyPath
    ) throws Exception {
        String root = remoteDir == null ? "" : remoteDir.trim().replaceAll("/+$", "");
        if (root.isEmpty()) throw new IllegalArgumentException("서버 캐시 폴더가 비어 있습니다.");
        String path = root + "/mobile-strategy-settings.json";
        Session session = connect(host, username, keyPath);
        ChannelSftp sftp = null;
        try {
            sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
            try (InputStream in = sftp.get(path);
                 ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) >= 0) out.write(buffer, 0, n);
                String json = out.toString(StandardCharsets.UTF_8.name());
                new JSONObject(json);
                return json;
            }
        } catch (SftpException e) {
            if (e.id == ChannelSftp.SSH_FX_NO_SUCH_FILE) return "{}";
            throw e;
        } finally {
            if (sftp != null && sftp.isConnected()) sftp.disconnect();
            session.disconnect();
        }
    }

    public static final class DashboardTunnel implements AutoCloseable {
        private final Session session;
        private final int localPort;

        private DashboardTunnel(Session session, int localPort) {
            this.session = session;
            this.localPort = localPort;
        }

        public int getLocalPort() {
            return localPort;
        }

        public boolean isConnected() {
            return session.isConnected();
        }

        @Override
        public void close() {
            try {
                if (session.isConnected()) session.disconnect();
            } catch (Exception ignored) {
            }
        }
    }

    public static DashboardTunnel openDashboardTunnel(
            String host,
            String username,
            String keyPath,
            int remotePort
    ) throws Exception {
        Session session = connect(host, username, keyPath);
        session.setServerAliveInterval(15000);
        session.setServerAliveCountMax(3);
        try {
            int localPort = session.setPortForwardingL(0, "127.0.0.1", remotePort);
            return new DashboardTunnel(session, localPort);
        } catch (Exception e) {
            session.disconnect();
            throw e;
        }
    }

    public static final class RelayClient implements AutoCloseable {
        private final Session session;
        private final ChannelSftp sftp;

        public RelayClient(String host, String username, String keyPath) throws Exception {
            session = connect(host, username, keyPath);
            session.setServerAliveInterval(15000);
            session.setServerAliveCountMax(3);
            sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
        }

        public boolean isConnected() {
            return session.isConnected() && sftp.isConnected();
        }

        public synchronized void uploadTextAtomic(String remotePath, String text) throws Exception {
            if (!isConnected()) throw new IllegalStateException("SSH relay channel is disconnected");
            int slash = remotePath.lastIndexOf('/');
            if (slash <= 0) throw new IllegalArgumentException("invalid remote path: " + remotePath);
            String remoteDir = remotePath.substring(0, slash);
            ensureRemoteDir(session, remoteDir);
            String temp = remotePath + ".uploading";
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            try {
                sftp.rm(temp);
            } catch (SftpException ignored) {
            }
            sftp.put(new ByteArrayInputStream(bytes), temp);
            try {
                sftp.rm(remotePath);
            } catch (SftpException e) {
                if (e.id != ChannelSftp.SSH_FX_NO_SUCH_FILE) throw e;
            }
            sftp.rename(temp, remotePath);
        }

        @Override
        public void close() {
            try {
                if (sftp.isConnected()) sftp.disconnect();
            } catch (Exception ignored) {
            }
            try {
                if (session.isConnected()) session.disconnect();
            } catch (Exception ignored) {
            }
        }
    }

    public static String uploadFiles(
            String dbPath,
            String resultPath,
            String host,
            String username,
            String remoteDir,
            String keyPath
    ) throws Exception {
        File database = new File(dbPath);
        File result = new File(resultPath);
        if (!database.isFile()) throw new IllegalArgumentException("캐시 DB가 없습니다: " + dbPath);
        if (database.length() < 4096) throw new IllegalArgumentException("캐시 DB가 너무 작습니다: " + dbPath);
        if (!result.isFile()) throw new IllegalArgumentException("결과 파일이 없습니다: " + resultPath);

        JSONObject resultMeta = new JSONObject(readText(result));
        if (!resultMeta.optBoolean("server_upload_eligible", false)) {
            throw new IllegalStateException("서버 업로드 차단: 완료·검증된 요약 결과만 업로드할 수 있습니다.");
        }

        JSONArray logs = new JSONArray();
        logs.put("SSH 연결: " + username + "@" + host);
        Session session = connect(host, username, keyPath);
        try {
            ensureRemoteDir(session, remoteDir);
            ChannelSftp sftp = (ChannelSftp) session.openChannel("sftp");
            sftp.connect(15000);
            try {
                uploadAtomic(sftp, database, remoteDir, logs);
                uploadAtomic(sftp, result, remoteDir, logs);

                JSONObject manifest = new JSONObject();
                manifest.put("upload_mode", "cache_and_summary");
                manifest.put("database", database.getName());
                manifest.put("database_size_bytes", database.length());
                manifest.put("database_sha256", sha256(database));
                manifest.put("result", result.getName());
                manifest.put("symbol", resultMeta.optString("symbol", ""));
                manifest.put("timeframe", resultMeta.optString("timeframe", ""));
                manifest.put("requested_start", resultMeta.optString("requested_start", ""));
                manifest.put("requested_end", resultMeta.optString("requested_end", ""));
                manifest.put("range_days", resultMeta.optInt("range_days", 0));
                manifest.put("result_sha256", sha256(result));
                manifest.put("uploaded_at", utcNow());

                String manifestName = stripExtension(result.getName()) + ".upload-manifest.json";
                String remoteManifest = joinRemote(remoteDir, manifestName);
                byte[] bytes = (manifest.toString(2) + "\n").getBytes(StandardCharsets.UTF_8);
                sftp.put(new ByteArrayInputStream(bytes), remoteManifest);
                logs.put("완료: " + remoteManifest);
                logs.put("서버 캐시 DB와 검증 요약 업로드 완료.");
            } finally {
                sftp.disconnect();
            }
        } finally {
            session.disconnect();
        }

        JSONObject response = new JSONObject();
        response.put("ok", true);
        response.put("logs", logs);
        return response.toString();
    }

    private static Session connect(String host, String username, String keyPath) throws Exception {
        JSch jsch = new JSch();
        jsch.addIdentity(keyPath);
        Session session = jsch.getSession(username, host, 22);
        Properties config = new Properties();
        config.put("StrictHostKeyChecking", "no");
        config.put("PreferredAuthentications", "publickey");
        session.setConfig(config);
        session.connect(15000);
        return session;
    }

    private static void ensureRemoteDir(Session session, String remoteDir) throws Exception {
        ChannelExec exec = (ChannelExec) session.openChannel("exec");
        exec.setCommand("mkdir -p -- " + shellQuote(remoteDir));
        exec.setInputStream(null);
        exec.connect(10000);
        try {
            long deadline = System.currentTimeMillis() + 10000;
            while (!exec.isClosed() && System.currentTimeMillis() < deadline) {
                Thread.sleep(50);
            }
            if (!exec.isClosed()) throw new IllegalStateException("원격 폴더 생성 명령이 시간 초과되었습니다.");
            if (exec.getExitStatus() != 0) {
                throw new IllegalStateException("원격 폴더 생성 실패: exit=" + exec.getExitStatus());
            }
        } finally {
            exec.disconnect();
        }
    }

    private static void uploadAtomic(ChannelSftp sftp, File local, String remoteDir, JSONArray logs) throws Exception {
        String remote = joinRemote(remoteDir, local.getName());
        String temp = remote + ".uploading";
        logs.put("업로드: " + local.getName());
        try {
            sftp.rm(temp);
        } catch (SftpException ignored) {
        }
        sftp.put(local.getAbsolutePath(), temp);
        try {
            sftp.rm(remote);
        } catch (SftpException e) {
            if (e.id != ChannelSftp.SSH_FX_NO_SUCH_FILE) throw e;
        }
        sftp.rename(temp, remote);
        logs.put("완료: " + remote);
    }

    private static String joinRemote(String dir, String name) {
        String trimmed = dir.endsWith("/") ? dir.substring(0, dir.length() - 1) : dir;
        return trimmed + "/" + name;
    }

    private static String shellQuote(String value) {
        return "'" + value.replace("'", "'\\''") + "'";
    }

    private static String readText(File file) throws Exception {
        try (InputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = in.read(buffer)) >= 0) {
                out.write(buffer, 0, n);
            }
            return out.toString("UTF-8");
        }
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[1024 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) digest.update(buffer, 0, n);
        }
        StringBuilder sb = new StringBuilder();
        for (byte b : digest.digest()) sb.append(String.format(Locale.US, "%02x", b));
        return sb.toString();
    }

    private static String utcNow() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        f.setTimeZone(TimeZone.getTimeZone("UTC"));
        return f.format(new Date());
    }

    private static String stripExtension(String name) {
        int i = name.lastIndexOf('.');
        return i > 0 ? name.substring(0, i) : name;
    }
}
