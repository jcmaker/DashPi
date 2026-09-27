const path = require('node:path')
const { getDefaultConfig } = require('expo/metro-config')

const config = getDefaultConfig(__dirname)
config.watchFolders = [path.resolve(__dirname, '../web/src/optical')]
config.resolver.resolveRequest = (context, moduleName, platform) => {
  const name = moduleName.endsWith('.ts') ? moduleName.slice(0, -3) : moduleName
  return context.resolveRequest(context, name, platform)
}

module.exports = config
