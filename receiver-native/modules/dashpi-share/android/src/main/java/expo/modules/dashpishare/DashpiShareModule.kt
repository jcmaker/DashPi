package expo.modules.dashpishare

import android.app.Activity
import android.content.ClipData
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.Promise
import java.io.File

private const val CHOOSER_REQUEST = 4817
private const val TARGET_REQUEST = 4818
private const val SHARE_CACHE_DIRECTORY = "dashpi-share"

class ShareInProgressException : CodedException("A share sheet is already open.")

class SharePathException(message: String) : CodedException(message)

class DashpiShareModule : Module() {
  private var pendingPromise: Promise? = null
  private var pendingUri: Uri? = null
  private var pendingFile: File? = null
  private var pendingMime: String? = null
  private var chosenActivityOpen = false

  override fun definition() = ModuleDefinition {
    Name("DashpiShare")

    // The in-app chooser only returns the component the user picked. Read access is
    // granted by starting that activity with FLAG_GRANT_READ_URI_PERMISSION and ClipData.
    AsyncFunction("shareAsync") { uri: String, mimeType: String, dialogTitle: String, promise: Promise ->
      if (pendingPromise != null) throw ShareInProgressException()
      val file = shareFile(uri)
      val context = appContext.reactContext ?: throw SharePathException("Android context is unavailable.")
      val contentUri = FileProvider.getUriForFile(context, context.packageName + ".dashpi.share", file)
      pendingPromise = promise
      pendingUri = contentUri
      pendingFile = file
      pendingMime = mimeType
      chosenActivityOpen = false
      try {
        val chooser = Intent(context, DashpiShareChooserActivity::class.java).apply {
          putExtra(DashpiShareChooserActivity.EXTRA_MIME_TYPE, mimeType)
          putExtra(DashpiShareChooserActivity.EXTRA_TITLE, dialogTitle)
        }
        appContext.throwingActivity.startActivityForResult(chooser, CHOOSER_REQUEST)
      } catch (error: Exception) {
        failShare("Failed to open the share sheet: ${error.message}")
      }
    }.runOnQueue(Queues.MAIN)

    OnActivityResult { _, payload ->
      when (payload.requestCode) {
        CHOOSER_REQUEST -> onChooserResult(payload.resultCode, payload.data)
        TARGET_REQUEST -> onChosenActivityResult()
      }
    }

    OnDestroy {
      if (!chosenActivityOpen) finishShare()
    }
  }

  private fun onChooserResult(resultCode: Int, data: Intent?) {
    if (pendingPromise == null) return
    val packageName = data?.getStringExtra(DashpiShareChooserActivity.EXTRA_PACKAGE)
    val className = data?.getStringExtra(DashpiShareChooserActivity.EXTRA_CLASS)
    val uri = pendingUri
    val mimeType = pendingMime
    val targetSelected = resultCode == Activity.RESULT_OK &&
      !packageName.isNullOrEmpty() &&
      !className.isNullOrEmpty() &&
      uri != null &&
      mimeType != null
    if (!targetSelected || packageName == null || className == null || uri == null || mimeType == null) {
      finishShare()
      return
    }
    chosenActivityOpen = true
    try {
      val target = sendIntent(uri, mimeType, ComponentName(packageName, className))
      appContext.throwingActivity.startActivityForResult(target, TARGET_REQUEST)
    } catch (error: Exception) {
      chosenActivityOpen = false
      failShare("Failed to open the selected app: ${error.message}")
    }
  }

  private fun onChosenActivityResult() {
    if (!chosenActivityOpen && pendingPromise == null) return
    chosenActivityOpen = false
    finishShare()
  }

  private fun sendIntent(uri: Uri, mimeType: String, component: ComponentName): Intent {
    return Intent(Intent.ACTION_SEND).apply {
      type = mimeType
      putExtra(Intent.EXTRA_STREAM, uri)
      clipData = ClipData.newRawUri("DashPi report", uri)
      addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
      this.component = component
    }
  }

  private fun shareFile(uriString: String): File {
    val uri = Uri.parse(uriString)
    if (uri.scheme != "file") throw SharePathException("Only a file URI can be shared.")
    val path = uri.path ?: throw SharePathException("Share URI is missing a path.")
    val file = File(path).canonicalFile
    val root = File(appContext.cacheDirectory, SHARE_CACHE_DIRECTORY).canonicalFile
    val prefix = root.path + File.separator
    if (!file.path.startsWith(prefix) || !file.isFile) {
      throw SharePathException("Refusing to share a file outside the share cache.")
    }
    return file
  }

  private fun finishShare() {
    val uri = pendingUri
    val file = pendingFile
    val promise = pendingPromise
    clearPending()
    revokeAndDelete(uri, file)
    promise?.resolve(null)
  }

  private fun failShare(message: String) {
    val uri = pendingUri
    val file = pendingFile
    val promise = pendingPromise
    clearPending()
    revokeAndDelete(uri, file)
    promise?.reject("ERR_SHARE_FAILED", message, null)
  }

  private fun revokeAndDelete(uri: Uri?, file: File?) {
    val context = appContext.reactContext
    if (uri != null && context != null) {
      runCatching { context.revokeUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
    }
    if (file != null && file.exists()) file.delete()
  }

  private fun clearPending() {
    pendingPromise = null
    pendingUri = null
    pendingFile = null
    pendingMime = null
    chosenActivityOpen = false
  }
}
