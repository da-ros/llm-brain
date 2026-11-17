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
class EncefalusSandbox: RCTEventEmitter {
  private var transfer: PackTransfer?

  override func supportedEvents() -> [String]! {
    ["EncefalusPackProgress"]
  }

  @objc override static func requiresMainQueueSetup() -> Bool { false }

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
    if transfer != nil {
      reject("pack", "A download is already running.", nil)
      return
    }
    var request = URLRequest(url: url)
    request.timeoutInterval = 30 * 60
    if !token.isEmpty {
      request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
    let dir = documents().appendingPathComponent("packs", isDirectory: true)
    do {
      try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    } catch {
      reject("pack", "Unable to store the pack", error)
      return
    }
    let config = URLSessionConfiguration.default
    config.timeoutIntervalForRequest = 30 * 60
    config.timeoutIntervalForResource = 6 * 60 * 60
    config.waitsForConnectivity = true
    let transfer = PackTransfer(
      destination: dir.appendingPathComponent(safeName),
      resolve: resolve,
      reject: reject,
      emit: { [weak self] received, total in
        self?.sendEvent(withName: "EncefalusPackProgress", body: ["received": received, "total": total])
      },
      finished: { [weak self] in
        self?.transfer = nil
      }
    )
    self.transfer = transfer
    let session = URLSession(configuration: config, delegate: transfer, delegateQueue: nil)
    transfer.session = session
    session.downloadTask(with: request).resume()
  }

  static func sha256File(_ url: URL) throws -> String {
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

/// Keeps the URLSession alive and reports bytes while the GGUF is written.
private final class PackTransfer: NSObject, URLSessionDownloadDelegate {
  var session: URLSession?
  private let destination: URL
  private let resolve: RCTPromiseResolveBlock
  private let reject: RCTPromiseRejectBlock
  private let emit: (Int64, Int64) -> Void
  private let finished: () -> Void
  private var partial: URL?
  private var lastEmit = Date.distantPast
  private var settled = false

  init(
    destination: URL,
    resolve: @escaping RCTPromiseResolveBlock,
    reject: @escaping RCTPromiseRejectBlock,
    emit: @escaping (Int64, Int64) -> Void,
    finished: @escaping () -> Void
  ) {
    self.destination = destination
    self.resolve = resolve
    self.reject = reject
    self.emit = emit
    self.finished = finished
  }

  func urlSession(
    _ session: URLSession,
    downloadTask: URLSessionDownloadTask,
    didWriteData bytesWritten: Int64,
    totalBytesWritten: Int64,
    totalBytesExpectedToWrite: Int64
  ) {
    let now = Date()
    let done = totalBytesExpectedToWrite > 0 && totalBytesWritten >= totalBytesExpectedToWrite
    if !done && now.timeIntervalSince(lastEmit) < 0.25 {
      return
    }
    lastEmit = now
    let total = totalBytesExpectedToWrite > 0 ? totalBytesExpectedToWrite : 0
    DispatchQueue.main.async {
      self.emit(totalBytesWritten, total)
    }
  }

  func urlSession(
    _ session: URLSession,
    downloadTask: URLSessionDownloadTask,
    didFinishDownloadingTo location: URL
  ) {
    let partial = destination.deletingLastPathComponent().appendingPathComponent(".\(destination.lastPathComponent).partial")
    do {
      if FileManager.default.fileExists(atPath: partial.path) {
        try FileManager.default.removeItem(at: partial)
      }
      try FileManager.default.moveItem(at: location, to: partial)
      self.partial = partial
    } catch {
      self.partial = nil
    }
  }

  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    session.finishTasksAndInvalidate()
    DispatchQueue.main.async {
      self.settle(task: task, error: error)
    }
  }

  private func settle(task: URLSessionTask, error: Error?) {
    if settled {
      return
    }
    settled = true
    defer { finished() }
    if let error {
      removePartial()
      reject("pack", "The download failed. The installed pack was kept.", error)
      return
    }
    guard let http = task.response as? HTTPURLResponse, (200 ... 299).contains(http.statusCode), let partial else {
      removePartial()
      let code = (task.response as? HTTPURLResponse)?.statusCode ?? 0
      reject("pack", "The download failed (\(code)). The installed pack was kept.", nil)
      return
    }
    do {
      let digest = try EncefalusSandbox.sha256File(partial)
      if FileManager.default.fileExists(atPath: destination.path) {
        try FileManager.default.removeItem(at: destination)
      }
      try FileManager.default.moveItem(at: partial, to: destination)
      let size = (try? FileManager.default.attributesOfItem(atPath: destination.path)[.size] as? NSNumber)?.int64Value ?? 0
      resolve(["path": destination.path, "bytes": size, "sha256": digest])
    } catch {
      removePartial()
      reject("pack", "Unable to store the pack", error)
    }
  }

  private func removePartial() {
    if let partial, FileManager.default.fileExists(atPath: partial.path) {
      try? FileManager.default.removeItem(at: partial)
    }
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
