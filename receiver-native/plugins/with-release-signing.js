// Signs `assembleRelease` with the DashPi upload key when CI provides it through env vars,
// so every released APK has the same signature and Android accepts it as an update.
// Without the env vars (local builds) release builds keep Expo's default debug signing.
const { withAppBuildGradle } = require('expo/config-plugins')

const RELEASE_SIGNING = `
        release {
            if (System.getenv('DASHPI_UPLOAD_STORE_FILE')) {
                storeFile file(System.getenv('DASHPI_UPLOAD_STORE_FILE'))
                storePassword System.getenv('DASHPI_UPLOAD_STORE_PASSWORD')
                keyAlias System.getenv('DASHPI_UPLOAD_KEY_ALIAS')
                keyPassword System.getenv('DASHPI_UPLOAD_KEY_PASSWORD')
            }
        }`

function withReleaseSigning(config) {
  return withAppBuildGradle(config, (modConfig) => {
    let gradle = modConfig.modResults.contents
    if (gradle.includes('DASHPI_UPLOAD_STORE_FILE')) return modConfig
    const debugConfig = /(signingConfigs \{\s*debug \{[^}]*\})/
    const releaseUsesDebug = /(buildTypes \{[\s\S]*?release \{[\s\S]*?)signingConfig signingConfigs\.debug/
    if (!debugConfig.test(gradle) || !releaseUsesDebug.test(gradle)) {
      throw new Error('with-release-signing: app/build.gradle layout changed; update the plugin')
    }
    gradle = gradle.replace(debugConfig, `$1${RELEASE_SIGNING}`)
    gradle = gradle.replace(
      releaseUsesDebug,
      "$1signingConfig System.getenv('DASHPI_UPLOAD_STORE_FILE') ? signingConfigs.release : signingConfigs.debug",
    )
    modConfig.modResults.contents = gradle
    return modConfig
  })
}

module.exports = withReleaseSigning
