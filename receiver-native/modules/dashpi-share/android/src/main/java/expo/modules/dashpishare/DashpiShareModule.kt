package expo.modules.dashpishare

import android.content.ClipData
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.Promise
import java.io.File

private const val REQUEST_CODE = 4817
private const val SHARE_CACHE_DIRECTORY = "dashpi-share"

class ShareInProgressException : CodedException("A share sheet is already open.")

class SharePathException(message: String) : CodedException(message)

class DashpiShareModule : Module() {
  private var pendingPromise: Promise? = null
  private var pendingUri: Uri? = null
  private var pendingFile: File? = null

  override fun definition() = ModuleDefinition {
    Name("DashpiShare")

    // Grant read access with FLAG_GRANT_READ_URI_PERMISSION on the send intent and the
    // chooser. Do not query ACTION_SEND activities or call grantUriPermission for each
    // match — that hands the report to every app before the user picks.
    AsyncFunction("shareAsync") { uri: String, mimeType: String, dialogTitle: String, promise: Promise ->
      if (pendingPromise != null) throw ShareInProgressException()
      val file = shareFile(uri)
      val context = appContext.reactContext ?: throw SharePathException("Android context is unavailable.")
      val contentUri = FileProvider.getUriForFile(context, context.packageName + ".dashpi.share", file)
      val send = sendIntent(contentUri, mimeType)
      val chooser = chooserIntent(send, dialogTitle)
      pendingPromise = promise
      pendingUri = contentUri
      pendingFile = file
      try {
        appContext.throwingActivity.startActivityForResult(chooser, REQUEST_CODE)
      } catch (error: Exception) {
        val openedUri = pendingUri
        val openedFile = pendingFile
        clearPending()
        revokeAndDelete(openedUri, openedFile)
        throw SharePathException("Failed to open the share sheet: ${error.message}")
      }
    }

    OnActivityResult { _, (requestCode) ->
      if (requestCode == REQUEST_CODE) finishShare()
    }

    OnDestroy {
      finishShare()
    }
  }

  private fun sendIntent(uri: Uri, mimeType: String): Intent {
    return Intent(Intent.ACTION_SEND).apply {
      type = mimeType
      putExtra(Intent.EXTRA_STREAM, uri)
      clipData = ClipData.newRawUri("DashPi report", uri)
      addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
  }

  private fun chooserIntent(send: Intent, title: String): Intent {
    return Intent.createChooser(send, title).apply {
      clipData = send.clipData
      addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
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
  }
}
