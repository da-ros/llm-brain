import CryptoKit
import Foundation
import React
import Security
import UIKit
import UniformTypeIdentifiers

@objc(EncefalusKeychain)
class EncefalusKeychain: NSObject {
  private let service = "encefalus"

  @objc static func requiresMainQueueSetup() -> Bool { false }

  @objc func get(
    _ resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: "session",
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    guard status == errSecSuccess, let data = item as? Data, let text = String(data: data, encoding: .utf8) else {
      resolve("")
      return
    }
    resolve(text)
  }

  @objc func set(
    _ value: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: "session",
    ]
    SecItemDelete(query as CFDictionary)
    var add = query
    add[kSecValueData as String] = Data(value.utf8)
    let status = SecItemAdd(add as CFDictionary, nil)
    if status == errSecSuccess {
      resolve(true)
    } else {
      reject("keychain", "Unable to store the session", nil)
    }
  }

  @objc func clear(
    _ resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: "session",
    ]
    SecItemDelete(query as CFDictionary)
    resolve(true)
  }
}

@objc(EncefalusSandbox)
class EncefalusSandbox: NSObject {
  @objc static func requiresMainQueueSetup() -> Bool { false }

  private func documents() -> URL {
    FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
  }

  @objc func load(
    _ resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    let url = documents().appendingPathComponent("encefalus-sandbox.json")
    resolve((try? String(contentsOf: url, encoding: .utf8)) ?? "")
  }

  @objc func save(
    _ json: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    let url = documents().appendingPathComponent("encefalus-sandbox.json")
    do {
      try json.write(to: url, atomically: true, encoding: .utf8)
      resolve(true)
    } catch {
      reject("sandbox", "Unable to save local data", error)
    }
  }

  @objc func writePack(
    _ filename: String,
    base64: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    guard let data = Data(base64Encoded: base64) else {
      reject("pack", "Pack bytes were not valid", nil)
      return
    }
    let dir = documents().appendingPathComponent("packs", isDirectory: true)
    do {
      try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
      let url = dir.appendingPathComponent(filename)
      try data.write(to: url)
      resolve(url.path)
    } catch {
      reject("pack", "Unable to write the pack", error)
    }
  }

  @objc func remove(
    _ path: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    if FileManager.default.fileExists(atPath: path) {
      try? FileManager.default.removeItem(atPath: path)
    }
    resolve(true)
  }

  /// Stream a GGUF to Documents/packs. A JS buffer cannot hold the Q4 file.
  @objc func downloadPack(
    _ urlString: String,
    filename: String,
    token: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    guard let url = URL(string: urlString), url.host?.isEmpty == false else {
      reject("pack", "Pack URL was not valid", nil)
      return
    }
    let safeName = (filename as NSString).lastPathComponent
    guard !safeName.isEmpty, safeName != ".", safeName != ".." else {
      reject("pack", "Pack filename was not valid", nil)
      return
    }
    var request = URLRequest(url: url)
    if !token.isEmpty {
      request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
    let config = URLSessionConfiguration.ephemeral
    config.timeoutIntervalForRequest = 120
    config.timeoutIntervalForResource = 6 * 60 * 60
    let session = URLSession(configuration: config)
    let task = session.downloadTask(with: request) { temp, response, error in
      session.finishTasksAndInvalidate()
      if let error {
        reject("pack", "The download failed. The installed pack was kept.", error)
        return
      }
      guard let http = response as? HTTPURLResponse, (200 ... 299).contains(http.statusCode), let temp else {
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        reject("pack", "The download failed (\(code)). The installed pack was kept.", nil)
        return
      }
      do {
        let digest = try Self.sha256File(temp)
        let dir = self.documents().appendingPathComponent("packs", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let dest = dir.appendingPathComponent(safeName)
        if FileManager.default.fileExists(atPath: dest.path) {
          try FileManager.default.removeItem(at: dest)
        }
        try FileManager.default.moveItem(at: temp, to: dest)
        let size = (try? FileManager.default.attributesOfItem(atPath: dest.path)[.size] as? NSNumber)?.intValue ?? 0
        resolve(["path": dest.path, "bytes": size, "sha256": digest])
      } catch {
        reject("pack", "Unable to store the pack", error)
      }
    }
    task.resume()
  }

  private static func sha256File(_ url: URL) throws -> String {
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }
    var hasher = SHA256()
    while true {
      let chunk = try handle.read(upToCount: 1024 * 1024) ?? Data()
      if chunk.isEmpty {
        break
      }
      hasher.update(data: chunk)
    }
    return hasher.finalize().map { String(format: "%02x", $0) }.joined()
  }
}

@objc(EncefalusPicker)
class EncefalusPicker: NSObject, UIDocumentPickerDelegate {
  private var resolve: RCTPromiseResolveBlock?

  @objc static func requiresMainQueueSetup() -> Bool { true }

  @objc func pick(
    _ kind: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    DispatchQueue.main.async {
      self.resolve = resolve
      let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.item], asCopy: true)
      picker.delegate = self
      picker.allowsMultipleSelection = false
      guard let controller = Self.topController() else {
        resolve([:])
        return
      }
      controller.present(picker, animated: true)
      _ = kind
    }
  }

  func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
    guard let url = urls.first, let data = try? Data(contentsOf: url) else {
      resolve?([:])
      resolve = nil
      return
    }
    resolve?([
      "filename": url.lastPathComponent,
      "mime": "application/octet-stream",
      "base64": data.base64EncodedString(),
    ])
    resolve = nil
  }

  func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
    resolve?([:])
    resolve = nil
  }

  private static func topController() -> UIViewController? {
    let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
    return scene?.windows.first { $0.isKeyWindow }?.rootViewController
  }
}
