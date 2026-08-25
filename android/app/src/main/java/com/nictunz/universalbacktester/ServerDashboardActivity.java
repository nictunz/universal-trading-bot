package com.nictunz.universalbacktester;

import android.annotation.SuppressLint;
import android.graphics.Color;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ServerDashboardActivity extends android.app.Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private WebView webView;
    private TextView status;
    private ProgressBar progress;
    private SshBridge.DashboardTunnel tunnel;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(11, 18, 32));

        status = new TextView(this);
        status.setText("SSH로 서버 관리 대시보드에 연결 중...");
        status.setTextColor(Color.rgb(226, 232, 240));
        status.setTextSize(13);
        status.setPadding(dp(14), dp(12), dp(14), dp(8));
        root.addView(status);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setIndeterminate(true);
        root.addView(progress, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(3)
        ));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(11, 18, 32));
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.getSettings().setMixedContentMode(
                android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        );
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setIndeterminate(false);
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String host = request.getUrl().getHost();
                return host != null
                        && !host.equals("127.0.0.1")
                        && !host.equals("localhost");
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                status.setText("서버 대시보드 연결됨 · SSH 암호화 터널");
            }
        });
        root.addView(webView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));
        setContentView(root);
        connect();
    }

    private void connect() {
        executor.execute(() -> {
            try {
                android.content.SharedPreferences prefs =
                        getSharedPreferences("universal_bot", MODE_PRIVATE);
                String host = prefs.getString("relay_host", "34.132.172.40").trim();
                String user = prefs.getString("relay_user", "kpj3669").trim();
                JSONObject key = new JSONObject(
                        SshBridge.ensureKey(getFilesDir().getAbsolutePath())
                );
                String keyPath = key.getString("private_key");
                tunnel = SshBridge.openDashboardTunnel(host, user, keyPath, 8000);
                String url = "http://127.0.0.1:" + tunnel.getLocalPort() + "/";
                runOnUiThread(() -> {
                    status.setText("서버 인증 화면 여는 중...");
                    webView.loadUrl(url);
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    progress.setVisibility(View.GONE);
                    status.setText(
                            "서버 대시보드 연결 실패: "
                                    + e.getClass().getSimpleName()
                                    + ": "
                                    + String.valueOf(e.getMessage())
                    );
                });
            }
        });
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        if (tunnel != null) tunnel.close();
        executor.shutdownNow();
        super.onDestroy();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
