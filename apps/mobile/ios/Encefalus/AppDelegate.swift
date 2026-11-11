import UIKit
import React
import React_RCTAppDelegate
import ReactAppDependencyProvider

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
  var window: UIWindow?

  var reactNativeDelegate: ReactNativeDelegate?
  var reactNativeFactory: RCTReactNativeFactory?

  func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    let delegate = ReactNativeDelegate()
    let factory = RCTReactNativeFactory(delegate: delegate)
    delegate.dependencyProvider = RCTAppDependencyProvider()

    reactNativeDelegate = delegate
    reactNativeFactory = factory

    window = UIWindow(frame: UIScreen.main.bounds)

    factory.startReactNative(
      withModuleName: "Encefalus",
      in: window,
      launchOptions: launchOptions
    )

    return true
  }
}

class ReactNativeDelegate: RCTDefaultReactNativeFactoryDelegate {
  override func sourceURL(for bridge: RCTBridge) -> URL? {
    self.bundleURL()
  }

  override func bundleURL() -> URL? {
#if DEBUG
    // 8081 belongs to another app. Use Metro on 8088 only when it is actually
    // running; otherwise keep the JavaScript Xcode packed into the app.
    let location = "\(Self.packagerHost()):8088"
    let settings = RCTBundleURLProvider.sharedSettings()
    if RCTBundleURLProvider.isPackagerRunning(location) {
      settings.jsLocation = location
      return RCTBundleURLProvider.jsBundleURL(
        forBundleRoot: "index",
        packagerHost: location,
        enableDev: true,
        enableMinification: false,
        inlineSourceMap: false
      )
    }
    settings.jsLocation = nil
#endif
    return Bundle.main.url(forResource: "main", withExtension: "jsbundle")
  }

  /// The Mac address written into the app at build time, so a physical iPhone
  /// can reach Metro. The simulator uses localhost.
  private static func packagerHost() -> String {
    guard let path = Bundle.main.path(forResource: "ip", ofType: "txt"),
          let ip = try? String(contentsOfFile: path, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines),
          !ip.isEmpty
    else {
      return "localhost"
    }
    return ip
  }
}
