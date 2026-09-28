// Reapplies the report-WebView sandbox to react-native-webview after npm ci.
// The library does not expose setBlockNetworkLoads or shouldInterceptRequest.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const pkg = join(root, 'node_modules/react-native-webview')
const MARKER = 'DASHPI_REPORT_SANDBOX'

function patch(relativePath, edit) {
  const path = join(pkg, relativePath)
  const original = readFileSync(path, 'utf8')
  if (original.includes(MARKER) && edit.skipIfMarked !== false && original.includes(edit.done)) {
    return
  }
  if (!original.includes(edit.anchor)) {
    throw new Error(`patch-webview-sandbox: anchor missing in ${relativePath}`)
  }
  const next = original.replace(edit.anchor, edit.replacement)
  if (next === original) throw new Error(`patch-webview-sandbox: no change in ${relativePath}`)
  writeFileSync(path, next)
}

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebViewClient.java', {
  done: 'allowsVerifiedDocumentResource',
  anchor: 'import android.webkit.WebViewClient;\n',
  replacement: `import android.webkit.WebViewClient;
import android.net.Uri;
import java.io.ByteArrayInputStream;
import java.util.Collections;
`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebViewClient.java', {
  done: 'mBlockNonDocumentLoads',
  anchor: '    protected boolean mLastLoadFailed = false;\n',
  replacement: `    protected boolean mLastLoadFailed = false;
    // ${MARKER}: set only for the verified-report WebView.
    private volatile boolean mBlockNonDocumentLoads = false;

    public void setBlockNonDocumentLoads(boolean enabled) {
        mBlockNonDocumentLoads = enabled;
    }
`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebViewClient.java', {
  done: 'shouldInterceptRequest(WebView view, WebResourceRequest request)',
  anchor: '    public void setProgressChangedFilter(RNCWebView.ProgressChangedFilter filter) {\n',
  replacement: `    // ${MARKER}: iframes, preloads, and POST hit this before the fetch, including when
    // shouldOverrideUrlLoading allows the load after its 250ms timeout.
    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        if (!mBlockNonDocumentLoads || allowsVerifiedDocumentResource(request.getUrl())) {
            return null;
        }
        return blockedDocumentResponse();
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
        if (!mBlockNonDocumentLoads || allowsVerifiedDocumentResource(Uri.parse(url))) {
            return null;
        }
        return blockedDocumentResponse();
    }

    private static boolean allowsVerifiedDocumentResource(Uri uri) {
        if (uri == null) {
            return true;
        }
        String scheme = uri.getScheme();
        if (scheme == null) {
            return true;
        }
        if ("data".equalsIgnoreCase(scheme)) {
            return true;
        }
        if ("about".equalsIgnoreCase(scheme)) {
            String rest = uri.getSchemeSpecificPart();
            return "blank".equals(rest) || "blank/".equals(rest);
        }
        return false;
    }

    private static WebResourceResponse blockedDocumentResponse() {
        return new WebResourceResponse(
                "text/plain",
                "UTF-8",
                403,
                "Blocked",
                Collections.emptyMap(),
                new ByteArrayInputStream(new byte[0]));
    }

    public void setProgressChangedFilter(RNCWebView.ProgressChangedFilter filter) {
`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebView.java', {
  done: 'setBlockNetworkLoads(true)',
  anchor: '    RNCWebViewClient mRNCWebViewClient;\n',
  replacement: `    RNCWebViewClient mRNCWebViewClient;
    // ${MARKER}
    private boolean mBlockNonDocumentLoads = false;

    public void setBlockNonDocumentLoads(boolean enabled) {
        mBlockNonDocumentLoads = enabled;
        if (enabled) {
            getSettings().setBlockNetworkLoads(true);
        }
        if (mRNCWebViewClient != null) {
            mRNCWebViewClient.setBlockNonDocumentLoads(enabled);
        }
        if (mWebChromeClient instanceof RNCWebChromeClient) {
            ((RNCWebChromeClient) mWebChromeClient).setSuppressFileChooser(enabled);
        }
    }
`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebView.java', {
  done: 'mRNCWebViewClient.setBlockNonDocumentLoads(mBlockNonDocumentLoads)',
  anchor: `            mRNCWebViewClient = (RNCWebViewClient) client;
            mRNCWebViewClient.setProgressChangedFilter(progressChangedFilter);
        }
    }`,
  replacement: `            mRNCWebViewClient = (RNCWebViewClient) client;
            mRNCWebViewClient.setProgressChangedFilter(progressChangedFilter);
            mRNCWebViewClient.setBlockNonDocumentLoads(mBlockNonDocumentLoads);
        }
    }`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebView.java', {
  done: 'setSuppressFileChooser(mBlockNonDocumentLoads)',
  anchor: `            ((RNCWebChromeClient) client).setProgressChangedFilter(progressChangedFilter);
        }
    }`,
  replacement: `            ((RNCWebChromeClient) client).setProgressChangedFilter(progressChangedFilter);
            ((RNCWebChromeClient) client).setSuppressFileChooser(mBlockNonDocumentLoads);
        }
    }`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java', {
  done: 'mSuppressFileChooser',
  anchor: '    protected RNCWebView mWebView;\n',
  replacement: `    protected RNCWebView mWebView;
    // ${MARKER}: report WebView must not open a picker or capture intent.
    private boolean mSuppressFileChooser = false;

    public void setSuppressFileChooser(boolean suppress) {
        mSuppressFileChooser = suppress;
    }
`,
})

const chooserGuard = `        if (mSuppressFileChooser) {
            filePathCallback.onReceiveValue(null);
            return;
        }
`

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java', {
  done: 'openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType) {\n        if (mSuppressFileChooser)',
  anchor: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType) {
      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, acceptType);
    }`,
  replacement: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType) {
${chooserGuard}      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, acceptType);
    }`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java', {
  done: 'openFileChooser(ValueCallback<Uri> filePathCallback) {\n        if (mSuppressFileChooser)',
  anchor: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback) {
      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, "");
    }`,
  replacement: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback) {
${chooserGuard}      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, "");
    }`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java', {
  done: 'openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType, String capture) {\n        if (mSuppressFileChooser)',
  anchor: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType, String capture) {
      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, acceptType);
    }`,
  replacement: `    protected void openFileChooser(ValueCallback<Uri> filePathCallback, String acceptType, String capture) {
${chooserGuard}      this.mWebView.getThemedReactContext().getNativeModule(RNCWebViewModule.class).startPhotoPickerIntent(filePathCallback, acceptType);
    }`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebChromeClient.java', {
  done: 'filePathCallback.onReceiveValue(null);\n            return true;',
  anchor: `    public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
        String[] acceptTypes = fileChooserParams.getAcceptTypes();`,
  replacement: `    public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
        if (mSuppressFileChooser) {
            filePathCallback.onReceiveValue(null);
            return true;
        }
        String[] acceptTypes = fileChooserParams.getAcceptTypes();`,
})

const managerAnchor = `    @ReactProp(name = "javaScriptEnabled")
    public void setJavaScriptEnabled(RNCWebViewWrapper view, boolean enabled) {
        mRNCWebViewManagerImpl.setJavaScriptEnabled(view, enabled);
    }
`

patch('android/src/newarch/com/reactnativecommunity/webview/RNCWebViewManager.java', {
  done: 'name = "blockNonDocumentLoads"',
  anchor: managerAnchor,
  replacement: `    @Override
    @ReactProp(name = "blockNonDocumentLoads")
    public void setBlockNonDocumentLoads(RNCWebViewWrapper view, boolean value) {
        mRNCWebViewManagerImpl.setBlockNonDocumentLoads(view, value);
    }

${managerAnchor}`,
})

patch('android/src/oldarch/com/reactnativecommunity/webview/RNCWebViewManager.java', {
  done: 'name = "blockNonDocumentLoads"',
  anchor: managerAnchor,
  replacement: `    @ReactProp(name = "blockNonDocumentLoads")
    public void setBlockNonDocumentLoads(RNCWebViewWrapper view, boolean value) {
        mRNCWebViewManagerImpl.setBlockNonDocumentLoads(view, value);
    }

${managerAnchor}`,
})

patch('android/src/main/java/com/reactnativecommunity/webview/RNCWebViewManagerImpl.kt', {
  done: 'fun setBlockNonDocumentLoads',
  anchor: `    fun setJavaScriptEnabled(viewWrapper: RNCWebViewWrapper, enabled: Boolean) {
        val view = viewWrapper.webView
        view.settings.javaScriptEnabled = enabled
    }
`,
  replacement: `    fun setBlockNonDocumentLoads(viewWrapper: RNCWebViewWrapper, enabled: Boolean) {
        // ${MARKER}
        viewWrapper.webView.setBlockNonDocumentLoads(enabled)
    }

    fun setJavaScriptEnabled(viewWrapper: RNCWebViewWrapper, enabled: Boolean) {
        val view = viewWrapper.webView
        view.settings.javaScriptEnabled = enabled
    }
`,
})

patch('src/RNCWebViewNativeComponent.ts', {
  done: 'blockNonDocumentLoads?',
  anchor: '  setSupportMultipleWindows?: WithDefault<boolean, true>;\n',
  replacement: `  setSupportMultipleWindows?: WithDefault<boolean, true>;
  // ${MARKER}: Android-only. Gates setBlockNetworkLoads and shouldInterceptRequest.
  blockNonDocumentLoads?: WithDefault<boolean, false>;
`,
})

patch('src/WebViewTypes.ts', {
  done: 'blockNonDocumentLoads?',
  anchor: '  setSupportMultipleWindows?: boolean;\n',
  replacement: `  setSupportMultipleWindows?: boolean;

  /**
   * Android report sandbox. Blocks non-document loads before they fetch and
   * ignores the file chooser. The display CSP is not this boundary.
   * @platform android
   */
  blockNonDocumentLoads?: boolean;
`,
})
