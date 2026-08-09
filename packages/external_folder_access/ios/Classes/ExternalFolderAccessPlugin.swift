import Flutter
import UIKit
import UniformTypeIdentifiers

/// Lets NeoStation pick a folder exposed by another app (e.g. RetroArch,
/// which shows up under "On My iPhone > RetroArch" in the Files app) via
/// the system document picker, and keeps that access valid across app
/// relaunches using a security-scoped bookmark.
///
/// Why this exists: iOS sandboxes every app from every other app's storage.
/// A path picked via UIDocumentPickerViewController is only guaranteed
/// accessible for the picking session unless you persist a *security-scoped
/// bookmark* and re-resolve + re-activate it (startAccessingSecurityScopedResource)
/// on every subsequent launch. That's exactly what this plugin does, so
/// NeoStation can scan RetroArch's own ROM folder in place instead of
/// copying files into its own sandbox.
public class ExternalFolderAccessPlugin: NSObject, FlutterPlugin, UIDocumentPickerDelegate {
    private var pendingResult: FlutterResult?
    private static let bookmarkDefaultsKey = "external_folder_access.bookmark"

    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "neostation/external_folder_access",
            binaryMessenger: registrar.messenger()
        )
        let instance = ExternalFolderAccessPlugin()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "pickAndBookmarkFolder":
            pickFolder(result: result)
        case "resolveBookmarkedFolder":
            resolveBookmarkedFolder(result: result)
        case "clearBookmark":
            clearBookmark(result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Pick

    private func pickFolder(result: @escaping FlutterResult) {
        guard let rootVC = Self.topViewController() else {
            result(
                FlutterError(
                    code: "NO_ROOT_VC",
                    message: "No root view controller available to present the picker from",
                    details: nil
                )
            )
            return
        }

        // A previous pick that never got a callback (e.g. the app was
        // killed mid-pick) shouldn't leak a dangling result — just drop it
        // rather than trying to call it twice.
        pendingResult = result

        let picker: UIDocumentPickerViewController
        if #available(iOS 14.0, *) {
            picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder])
        } else {
            picker = UIDocumentPickerViewController(documentTypes: ["public.folder"], in: .open)
        }
        picker.delegate = self
        picker.allowsMultipleSelection = false

        rootVC.present(picker, animated: true, completion: nil)
    }

    public func documentPicker(
        _ controller: UIDocumentPickerViewController,
        didPickDocumentsAt urls: [URL]
    ) {
        guard let url = urls.first else {
            pendingResult?(nil)
            pendingResult = nil
            return
        }

        // Bookmark creation itself needs the resource to be accessible;
        // wrap it in a matched start/stop pair even though the picker's
        // returned URL is already scoped for this immediate callback.
        let didStart = url.startAccessingSecurityScopedResource()
        defer {
            if didStart { url.stopAccessingSecurityScopedResource() }
        }

        do {
            let bookmarkData = try url.bookmarkData(
                options: [],
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )
            UserDefaults.standard.set(bookmarkData, forKey: Self.bookmarkDefaultsKey)
            pendingResult?(url.path)
        } catch {
            pendingResult?(
                FlutterError(
                    code: "BOOKMARK_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
        pendingResult = nil
    }

    public func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        pendingResult?(nil)
        pendingResult = nil
    }

    // MARK: - Resolve / clear

    /// Resolves the previously-bookmarked folder (if any) and starts
    /// security-scoped access for the remainder of this app session.
    /// Deliberately never calls stopAccessingSecurityScopedResource() here —
    /// NeoStation needs the folder readable for as long as the app runs, and
    /// iOS releases the scope automatically when the process exits.
    private func resolveBookmarkedFolder(result: @escaping FlutterResult) {
        guard let bookmarkData = UserDefaults.standard.data(forKey: Self.bookmarkDefaultsKey) else {
            result(nil)
            return
        }

        var isStale = false
        do {
            let url = try URL(
                resolvingBookmarkData: bookmarkData,
                options: [],
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            )
            guard url.startAccessingSecurityScopedResource() else {
                result(
                    FlutterError(
                        code: "ACCESS_DENIED",
                        message: "startAccessingSecurityScopedResource returned false",
                        details: nil
                    )
                )
                return
            }
            result(url.path)
        } catch {
            result(
                FlutterError(
                    code: "RESOLVE_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
    }

    private func clearBookmark(result: @escaping FlutterResult) {
        UserDefaults.standard.removeObject(forKey: Self.bookmarkDefaultsKey)
        result(nil)
    }

    // MARK: - Helpers

    private static func topViewController() -> UIViewController? {
        let keyWindow = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow }

        var top = keyWindow?.rootViewController
        while let presented = top?.presentedViewController {
            top = presented
        }
        return top
    }
}
