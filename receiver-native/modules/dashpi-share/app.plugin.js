const { AndroidConfig, withAndroidManifest } = require('expo/config-plugins')

const AUTHORITY = '${applicationId}.dashpi.share'

function withDashpiShare(config) {
  return withAndroidManifest(config, (modConfig) => {
    const app = AndroidConfig.Manifest.getMainApplicationOrThrow(modConfig.modResults)
    const providers = app.provider ? (Array.isArray(app.provider) ? app.provider : [app.provider]) : []
    if (providers.some((provider) => provider.$?.['android:authorities'] === AUTHORITY)) {
      app.provider = providers
      return modConfig
    }
    app.provider = [
      ...providers,
      {
        $: {
          'android:name': 'expo.modules.dashpishare.DashpiShareFileProvider',
          'android:authorities': AUTHORITY,
          'android:exported': 'false',
          'android:grantUriPermissions': 'true',
        },
        'meta-data': [
          {
            $: {
              'android:name': 'android.support.FILE_PROVIDER_PATHS',
              'android:resource': '@xml/dashpi_share_paths',
            },
          },
        ],
      },
    ]
    return modConfig
  })
}

module.exports = withDashpiShare
