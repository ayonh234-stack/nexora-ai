package com.socialgrowthlab.nexora;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.Manifest;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

/** Nexora AI: a thin, fast WebView shell around the Nexora AI web app (URL is configurable). */
public class MainActivity extends Activity {
    private static final String PREFS = "nexora";
    private static final String KEY_URL = "server_url";
    private static final String SETUP = "file:///android_asset/setup.html";
    private static final int FILE_REQ = 42;
    private static final int MIC_REQ = 43;
    private PermissionRequest pendingMic;

    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private volatile boolean onLocalPage = false;
    private String appHost = "";

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setBackgroundColor(0xFF0B0B14);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // chat history in localStorage
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setUserAgentString(s.getUserAgentString() + " NexoraApp/1.1");
        CookieManager.getInstance().setAcceptCookie(true);

        web.addJavascriptInterface(new Bridge(), "NexoraAndroid");
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener((url, ua, cd, mime, len) -> download(url, cd, mime));

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            loadApp();
        }
    }

    private SharedPreferences prefs() { return getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    private String serverUrl() {
        String u = prefs().getString(KEY_URL, "");
        if (u == null || u.trim().isEmpty()) u = BuildConfig.DEFAULT_URL;
        return u == null ? "" : u.trim();
    }

    private void loadApp() {
        String u = serverUrl();
        if (u.isEmpty()) { web.loadUrl(SETUP); return; }
        appHost = Uri.parse(u).getHost() == null ? "" : Uri.parse(u).getHost();
        web.loadUrl(u);
    }

    private void download(String url, String contentDisposition, String mime) {
        try {
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            String name = URLUtil.guessFileName(url, contentDisposition, mime);
            r.setMimeType(mime);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "Nexora-" + name);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(this, "Downloading… / ডাউনলোড হচ্ছে…", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            openExternal(url);
        }
    }

    private void openExternal(String url) {
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
        catch (ActivityNotFoundException ignored) { }
    }

    /** JS bridge. saveUrl only works from the bundled setup/offline page. */
    private class Bridge {
        @JavascriptInterface public String getUrl() { return serverUrl(); }

        @JavascriptInterface public void saveUrl(String url) {
            if (!onLocalPage) return;
            String u = url == null ? "" : url.trim();
            if (!u.isEmpty() && !u.startsWith("http://") && !u.startsWith("https://")) u = "https://" + u;
            while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
            prefs().edit().putString(KEY_URL, u).apply();
            final String fu = u;
            runOnUiThread(() -> { web.clearHistory(); if (fu.isEmpty()) web.loadUrl(SETUP); else loadApp(); });
        }

        @JavascriptInterface public void retry() { runOnUiThread(MainActivity.this::loadApp); }

        @JavascriptInterface public void openSetup() { runOnUiThread(() -> web.loadUrl(SETUP)); }
    }

    private class Client extends WebViewClient {
        @Override public void onPageStarted(WebView view, String url, Bitmap favicon) {
            onLocalPage = url != null && url.startsWith("file:///android_asset/");
        }

        @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
            Uri u = req.getUrl();
            String scheme = u.getScheme() == null ? "" : u.getScheme();
            if (scheme.equals("file")) return false;
            if ((scheme.equals("http") || scheme.equals("https")) && u.getHost() != null && u.getHost().equals(appHost)) return false;
            openExternal(u.toString());   // other sites, mailto:, tel:, whatsapp: etc.
            return true;
        }

        @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
            if (req.isForMainFrame()) view.loadUrl(SETUP + "?offline=1");
        }
    }

    private class Chrome extends WebChromeClient {
        @Override public void onPermissionRequest(final PermissionRequest request) {
            runOnUiThread(() -> {
                boolean wantsMic = false;
                for (String r : request.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) wantsMic = true;
                }
                Uri origin = request.getOrigin();
                String host = origin != null && origin.getHost() != null ? origin.getHost() : "";
                // Only our own Nexora server may use the microphone.
                if (!wantsMic || appHost.isEmpty() || !host.equalsIgnoreCase(appHost)) {
                    request.deny();
                    return;
                }
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                } else {
                    if (pendingMic != null) pendingMic.deny();
                    pendingMic = request;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MIC_REQ);
                }
            });
        }

        @Override public void onPermissionRequestCanceled(PermissionRequest request) {
            if (pendingMic == request) pendingMic = null;
        }

        @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> cb, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = cb;
            Intent i = new Intent(Intent.ACTION_GET_CONTENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("image/*");
            try {
                startActivityForResult(Intent.createChooser(i, "Photo / ছবি"), FILE_REQ);
            } catch (ActivityNotFoundException e) {
                fileCallback = null;
                return false;
            }
            return true;
        }
    }

    @Override public void onRequestPermissionsResult(int req, String[] perms, int[] results) {
        if (req == MIC_REQ) {
            PermissionRequest p = pendingMic;
            pendingMic = null;
            if (p != null) {
                if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                    p.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                } else {
                    p.deny();
                    Toast.makeText(this, "Microphone permission needed for voice / ভয়েসের জন্য মাইক্রোফোন অনুমতি দিন", Toast.LENGTH_LONG).show();
                }
            }
            return;
        }
        super.onRequestPermissionsResult(req, perms, results);
    }

    @Override protected void onActivityResult(int req, int result, Intent data) {
        if (req == FILE_REQ && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            fileCallback = null;
            return;
        }
        super.onActivityResult(req, result, data);
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override protected void onPause() { super.onPause(); web.onPause(); CookieManager.getInstance().flush(); }
    @Override protected void onResume() { super.onResume(); web.onResume(); }
}
