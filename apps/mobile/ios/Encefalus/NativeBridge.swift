import Foundation
import React
import Security
import UIKit
import UniformTypeIdentifiers

/// On-device Q4 runtime. ExecuTorch with the Core ML / Metal delegate is the
/// shipping body of `generate`. MLC on Metal can fill the same method. This
/// build validates the pack file and does not invent tokens or a latency.
@objc(OnDeviceLlm)
class OnDeviceLlm: NSObject {
  private var loadedPath: String?
  private var modelBytes: Int = 0

  @objc static func requiresMainQueueSetup() -> Bool { false }

  @objc func load(
    _ path: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    guard FileManager.default.fileExists(atPath: path) else {
      reject("not_ready", "On-device pack file is missing", nil)
      return
    }
    let size = (try? FileManager.default.attributesOfItem(atPath: path)[.size] as? Int) ?? 0
    guard size > 0 else {
      reject("not_ready", "On-device pack file is empty", nil)
      return
    }
    loadedPath = path
    modelBytes = size
    resolve(["ready": true, "bytes": size])
  }

  @objc func generate(
    _ prompt: String,
    resolver resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    guard loadedPath != nil else {
      reject("not_ready", "Load a pack before generate", nil)
      return
    }
    _ = prompt
    reject(
      "runtime_not_linked",
      "ExecuTorch Core ML delegate is not linked in this build",
      nil
    )
  }

  @objc func cancel() {}

  @objc func stats(
    _ resolve: @escaping RCTPromiseResolveBlock,
    rejecter reject: @escaping RCTPromiseRejectBlock
  ) {
    resolve([
      "modelBytes": modelBytes,
      "cacheBytes": 0,
      "ready": loadedPath != nil,
    ])
  }
}

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
