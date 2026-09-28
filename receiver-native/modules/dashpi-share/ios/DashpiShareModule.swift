import ExpoModulesCore
import UIKit

internal final class SharePathException: Exception {
  override var reason: String {
    "Only a file in the DashPi share cache can be shared."
  }
}

private final class ReportShareItem: NSObject, UIActivityItemSource {
  private let url: URL
  private let typeIdentifier: String

  init(url: URL, mediaType: String) {
    self.url = url
    self.typeIdentifier = mediaType == "text/html" ? "public.html" : "public.data"
    super.init()
  }

  func activityViewControllerPlaceholderItem(_ activityViewController: UIActivityViewController) -> Any {
    url
  }

  func activityViewController(
    _ activityViewController: UIActivityViewController,
    itemForActivityType activityType: UIActivity.ActivityType?
  ) -> Any? {
    url
  }

  func activityViewController(
    _ activityViewController: UIActivityViewController,
    dataTypeIdentifierForActivityType activityType: UIActivity.ActivityType?
  ) -> String {
    typeIdentifier
  }
}

public final class DashpiShareModule: Module {
  private var currentItem: ReportShareItem?

  public func definition() -> ModuleDefinition {
    Name("DashpiShare")

    AsyncFunction("shareAsync") { (uri: String, mimeType: String, dialogTitle: String, promise: Promise) in
      let cacheRoot = appContext?.config.cacheDirectory
        ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
      let fileURL = try shareFileURL(uri, cacheRoot: cacheRoot)
      let item = ReportShareItem(url: fileURL, mediaType: mimeType)
      self.currentItem = item
      let controller = UIActivityViewController(activityItems: [item], applicationActivities: nil)
      controller.title = dialogTitle
      controller.completionWithItemsHandler = { [weak self] _, _, _, _ in
        self?.currentItem = nil
        promise.resolve(nil)
      }

      guard let viewController = self.appContext?.utilities?.currentViewController() else {
        self.currentItem = nil
        throw SharePathException()
      }

      if UIDevice.current.userInterfaceIdiom == .pad {
        controller.popoverPresentationController?.sourceView = viewController.view
        controller.popoverPresentationController?.sourceRect = CGRect(
          x: viewController.view.bounds.midX,
          y: viewController.view.bounds.maxY,
          width: 0,
          height: 0
        )
        controller.modalPresentationStyle = .pageSheet
      }

      viewController.present(controller, animated: true)
    }.runOnQueue(.main)
  }
}

private func shareFileURL(_ uri: String, cacheRoot: URL) throws -> URL {
  guard let url = URL(string: uri), url.isFileURL else {
    throw SharePathException()
  }
  let fileURL = url.standardizedFileURL
  let shareRoot = cacheRoot
    .appendingPathComponent("dashpi-share", isDirectory: true)
    .standardizedFileURL
  let root = shareRoot.path.hasSuffix("/") ? shareRoot.path : shareRoot.path + "/"
  guard fileURL.path.hasPrefix(root), FileManager.default.fileExists(atPath: fileURL.path) else {
    throw SharePathException()
  }
  return fileURL
}
