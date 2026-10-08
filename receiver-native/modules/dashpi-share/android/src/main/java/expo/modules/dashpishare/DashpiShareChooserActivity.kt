package expo.modules.dashpishare

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ResolveInfo
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ListView

/**
 * Lists ACTION_SEND targets. It does not receive the report URI and does not call
 * grantUriPermission. The module starts only the activity the user picks.
 */
class DashpiShareChooserActivity : Activity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    val mimeType = intent.getStringExtra(EXTRA_MIME_TYPE) ?: "*/*"
    val targets = shareTargets(mimeType)
    val canSave = mimeType == "application/pdf"
    if (targets.isEmpty() && !canSave) {
      setResult(RESULT_CANCELED)
      finish()
      return
    }

    title = intent.getStringExtra(EXTRA_TITLE)
    val labels = (if (canSave) listOf("PDF 파일 저장") else emptyList()) +
      targets.map { it.loadLabel(packageManager).toString() }
    val list = ListView(this)
    list.adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, labels)
    list.setOnItemClickListener { _, _, which, _ ->
      if (canSave && which == 0) {
        setResult(RESULT_OK, Intent().putExtra(EXTRA_SAVE_PDF, true))
        finish()
        return@setOnItemClickListener
      }
      val activityInfo = targets[which - if (canSave) 1 else 0].activityInfo
      setResult(
        RESULT_OK,
        Intent().apply {
          putExtra(EXTRA_PACKAGE, activityInfo.packageName)
          putExtra(EXTRA_CLASS, activityInfo.name)
        },
      )
      finish()
    }
    setContentView(list)
  }

  @Deprecated("Activity.onBackPressed")
  @Suppress("DEPRECATION")
  override fun onBackPressed() {
    setResult(RESULT_CANCELED)
    finish()
  }

  private fun shareTargets(mimeType: String): List<ResolveInfo> {
    val probe = Intent(Intent.ACTION_SEND).apply { type = mimeType }
    return packageManager
      .queryIntentActivities(probe, PackageManager.MATCH_DEFAULT_ONLY)
      .filter { it.activityInfo.exported && it.activityInfo.packageName != packageName }
  }

  companion object {
    const val EXTRA_SAVE_PDF = "expo.modules.dashpishare.SAVE_PDF"
    const val EXTRA_MIME_TYPE = "expo.modules.dashpishare.MIME_TYPE"
    const val EXTRA_TITLE = "expo.modules.dashpishare.TITLE"
    const val EXTRA_PACKAGE = "expo.modules.dashpishare.PACKAGE"
    const val EXTRA_CLASS = "expo.modules.dashpishare.CLASS"
  }
}
