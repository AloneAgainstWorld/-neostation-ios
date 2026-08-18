import Flutter
import UIKit
import UniformTypeIdentifiers
import AVFoundation

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
public class ExternalFolderAccessPlugin: NSObject, FlutterPlugin, UIDocumentPickerDelegate,
    UIDocumentInteractionControllerDelegate
{
    private var pendingResult: FlutterResult?
    private var channel: FlutterMethodChannel?

    /// State for the one in-flight delayed launch retry. A second game launch
    /// cancels the previous retry so an old title can never unexpectedly open
    /// after the user has already selected a different one.
    private var delayedRetryWorkItem: DispatchWorkItem?
    private var delayedRetryBackgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var delayedRetryDebugFileName: String?

    /// State for RPCS3's bounded two-pass JIT/title-launch sequence.
    private var twoPassWorkItem: DispatchWorkItem?
    private var twoPassBackgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var twoPassDebugFileName: String?

    /// Bookmarks are stored per-emulator so several external folders can be
    /// linked side by side (RetroArch's, ARMSX2's, ...) instead of the one
    /// global slot this plugin originally had. The historical key is reused
    /// verbatim for the "retroarch" bookmark, so a folder linked before
    /// multi-bookmark support survives the upgrade with no migration step.
    private static let legacyBookmarkDefaultsKey = "external_folder_access.bookmark"
    private static let defaultBookmarkKey = "retroarch"

    /// The bookmark key the in-flight document picker will store under.
    /// Captured when the pick starts because UIDocumentPickerDelegate's
    /// callback carries no context of its own.
    private var pendingBookmarkKey: String = ExternalFolderAccessPlugin.defaultBookmarkKey

    private static func bookmarkDefaultsKey(for key: String) -> String {
        return key == defaultBookmarkKey
            ? legacyBookmarkDefaultsKey
            : "\(legacyBookmarkDefaultsKey).\(key)"
    }

    /// Reads the optional "key" argument, falling back to the default so a
    /// call made without one behaves exactly as it did before.
    private static func bookmarkKey(from call: FlutterMethodCall) -> String {
        guard let args = call.arguments as? [String: Any],
            let key = args["key"] as? String,
            !key.isEmpty
        else {
            return defaultBookmarkKey
        }
        return key
    }

    // Held as a property, not a local var — UIDocumentInteractionController
    // must stay alive for the duration of its menu/preview, and a local
    // variable would be deallocated the moment the calling function returns.
    private var documentInteractionController: UIDocumentInteractionController?

    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "neostation/external_folder_access",
            binaryMessenger: registrar.messenger()
        )
        let instance = ExternalFolderAccessPlugin()
        instance.channel = channel
        registrar.addMethodCallDelegate(instance, channel: channel)
        // Lets this plugin receive application(_:open:options:) callbacks —
        // needed to catch RetroArch calling back into neostation://... See
        // the method below and RetroArchLibraryService on the Dart side.
        registrar.addApplicationDelegate(instance)
    }

    /// Called by iOS when another app (or Safari) opens a URL registered to
    /// this app's CFBundleURLTypes — specifically, RetroArch's library
    /// export protocol calling back via
    /// neostation://retroarch?games=<base64url>. Forwards the URL to Dart
    /// as a method call on the same channel, rather than pulling in the
    /// third-party app_links package for what's otherwise a single simple
    /// callback.
    public func application(
        _ application: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        channel?.invokeMethod("onIncomingUrl", arguments: url.absoluteString)
        return true
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "pickAndBookmarkFolder":
            pickFolder(key: Self.bookmarkKey(from: call), result: result)
        case "resolveBookmarkedFolder":
            resolveBookmarkedFolder(key: Self.bookmarkKey(from: call), result: result)
        case "clearBookmark":
            clearBookmark(key: Self.bookmarkKey(from: call), result: result)
        case "openInMenu":
            openInMenu(call: call, result: result)
        case "openRawUrl":
            openRawUrl(call: call, result: result)
        case "configureAudioSessionForSilentMode":
            configureAudioSessionForSilentMode(result: result)
        case "openUrlWithDelayedRetry":
            openUrlWithDelayedRetry(call: call, result: result)
        case "openUrlAfterJitPreflight":
            openUrlAfterJitPreflight(call: call, result: result)
        case "openAppWithTwoPassJit":
            openAppWithTwoPassJit(call: call, result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Pick

    private func pickFolder(key: String, result: @escaping FlutterResult) {
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
        pendingBookmarkKey = key

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
            UserDefaults.standard.set(
                bookmarkData,
                forKey: Self.bookmarkDefaultsKey(for: pendingBookmarkKey)
            )
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
    private func resolveBookmarkedFolder(key: String, result: @escaping FlutterResult) {
        guard
            let bookmarkData = UserDefaults.standard.data(
                forKey: Self.bookmarkDefaultsKey(for: key)
            )
        else {
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

            // Sideload updates/re-signing can make an otherwise resolvable
            // bookmark stale. Refresh it immediately while the security scope
            // is active so subsequent cold launches keep the same folder grant.
            if isStale {
                do {
                    let refreshedBookmark = try url.bookmarkData(
                        options: [],
                        includingResourceValuesForKeys: nil,
                        relativeTo: nil
                    )
                    UserDefaults.standard.set(
                        refreshedBookmark,
                        forKey: Self.bookmarkDefaultsKey(for: key)
                    )
                } catch {
                    // The currently resolved URL is still usable for this
                    // process. Keep it rather than failing the whole launch;
                    // the next relink can replace the bookmark if necessary.
                    print("ExternalFolderAccess: failed refreshing stale bookmark for \(key): \(error)")
                }
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

    private func clearBookmark(key: String, result: @escaping FlutterResult) {
        UserDefaults.standard.removeObject(forKey: Self.bookmarkDefaultsKey(for: key))
        result(nil)
    }

    // MARK: - iOS audio session

    /// Uses the AVAudioSession category intended for non-primary app audio.
    /// `.ambient` is silenced by the iPhone Ring/Silent switch and mixes with
    /// audio from other apps. NeoStation reapplies this after SoLoud starts,
    /// because the audio backend may activate a different category during init.
    private func configureAudioSessionForSilentMode(result: @escaping FlutterResult) {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)
            result(true)
        } catch {
            result(
                FlutterError(
                    code: "AUDIO_SESSION_FAILED",
                    message: error.localizedDescription,
                    details: nil
                )
            )
        }
    }

    // MARK: - Raw URL opening

    /// Opens a custom URL exactly as supplied by Dart. Unlike constructing a
    /// Dart Uri first, this preserves the original case of the authority/host
    /// text. MeloNX currently dispatches `gameInfo` case-sensitively.
    private func openRawUrl(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
            let raw = args["url"] as? String,
            !raw.isEmpty,
            let url = URL(string: raw)
        else {
            result(
                FlutterError(
                    code: "INVALID_URL",
                    message: "openRawUrl requires a valid 'url' string argument",
                    details: nil
                )
            )
            return
        }

        UIApplication.shared.open(url, options: [:]) { opened in
            result(opened)
        }
    }

    // MARK: - Delayed direct-launch retry

    /// Opens a game deeplink now, then retries the same deeplink after a short
    /// delay. This deliberately does not know anything about StikDebug or the
    /// target emulator's bundle identifier: the first launch is allowed to
    /// trigger the emulator's own JIT flow, while the retry simply asks the
    /// unmodified emulator to launch the selected game again once JIT has had
    /// time to settle.
    ///
    /// A UIApplication background task gives the scheduled retry a short window
    /// to execute after NeoStation leaves the foreground. iOS still controls
    /// background runtime, so every stage is logged to Documents for on-device
    /// validation rather than assuming the delayed open is guaranteed.
    private func openUrlWithDelayedRetry(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let raw = args["url"] as? String,
            !raw.isEmpty,
            let url = URL(string: raw)
        else {
            result(
                FlutterError(
                    code: "INVALID_URL",
                    message: "openUrlWithDelayedRetry requires a valid 'url' string argument",
                    details: nil
                )
            )
            return
        }

        let requestedDelayMs: Int
        if let value = args["delayMs"] as? Int {
            requestedDelayMs = value
        } else if let value = args["delayMs"] as? NSNumber {
            requestedDelayMs = value.intValue
        } else {
            requestedDelayMs = 7000
        }

        // Keep the test range sane even if a malformed value reaches native.
        let delayMs = min(max(requestedDelayMs, 500), 20_000)
        let delaySeconds = Double(delayMs) / 1000.0
        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "jit_launch_debug.txt"
        )

        cancelDelayedRetry(reason: "REPLACED_BY_NEW_LAUNCH")
        delayedRetryDebugFileName = debugFileName
        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: INITIAL_OPEN\nURL: \(raw)\nRetry delay: \(delayMs) ms"
        )

        delayedRetryBackgroundTask = UIApplication.shared.beginBackgroundTask(
            withName: "NeoStation.JITLaunchRetry"
        ) { [weak self] in
            guard let self = self else { return }
            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: BACKGROUND_TASK_EXPIRED"
            )
            self.delayedRetryWorkItem?.cancel()
            self.delayedRetryWorkItem = nil
            self.endDelayedRetryBackgroundTask()
        }

        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: false,
            message: delayedRetryBackgroundTask == .invalid
                ? "STATE: BACKGROUND_TASK_UNAVAILABLE"
                : "STATE: BACKGROUND_TASK_STARTED"
        )

        UIApplication.shared.open(url, options: [:]) { [weak self] opened in
            guard let self = self else {
                result(false)
                return
            }

            guard opened else {
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: INITIAL_OPEN_FAILED"
                )
                self.cancelDelayedRetry(reason: "INITIAL_OPEN_FAILED")
                result(false)
                return
            }

            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: RETRY_SCHEDULED\nDelay: \(delayMs) ms"
            )

            let workItem = DispatchWorkItem { [weak self] in
                guard let self = self else { return }
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: RETRY_ATTEMPT\nApplication state: \(Self.applicationStateName())"
                )

                UIApplication.shared.open(url, options: [:]) { [weak self] retryOpened in
                    guard let self = self else { return }
                    Self.writeLaunchDebug(
                        fileName: debugFileName,
                        replace: false,
                        message: retryOpened ? "STATE: RETRY_OPENED" : "STATE: RETRY_FAILED"
                    )
                    self.delayedRetryWorkItem = nil
                    self.endDelayedRetryBackgroundTask()
                }
            }

            self.delayedRetryWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + delaySeconds, execute: workItem)

            // The Dart caller only needs to know that the first launch succeeded
            // and the native retry was scheduled. Do not keep Flutter waiting
            // while NeoStation is in the background.
            result(true)
        }
    }

    // MARK: - Explicit StikDebug JIT preflight

    /// Opens StikDebug first with the target emulator bundle identifier and
    /// universal JIT script, then opens the actual game deeplink after a short
    /// warm-up window. This avoids asking a demanding game to boot while
    /// StikDebug is still attaching/running its script.
    ///
    /// SideStore/AltStore commonly resign apps by appending the signing Team ID
    /// to the original bundle identifier. We derive the current Team ID from
    /// NeoStation's signed entitlements and only append it to the target when
    /// NeoStation's own installed bundle identifier also has that suffix. This
    /// avoids hard-coding one user's Team ID while preserving direct/ad-hoc
    /// installs that keep the original bundle identifier unchanged.
    private func openUrlAfterJitPreflight(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let targetBaseBundleId = args["targetBaseBundleId"] as? String,
            !targetBaseBundleId.isEmpty
        else {
            result(
                FlutterError(
                    code: "INVALID_ARGS",
                    message: "openUrlAfterJitPreflight requires targetBaseBundleId and a valid launch mode",
                    details: nil
                )
            )
            return
        }

        let requestedDelayMs: Int
        if let value = args["delayMs"] as? Int {
            requestedDelayMs = value
        } else if let value = args["delayMs"] as? NSNumber {
            requestedDelayMs = value.intValue
        } else {
            requestedDelayMs = 8000
        }
        let delayMs = min(max(requestedDelayMs, 1000), 20_000)
        let delaySeconds = Double(delayMs) / 1000.0
        let scriptName = ((args["scriptName"] as? String) ?? "universal.js").trimmingCharacters(in: .whitespacesAndNewlines)
        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "jit_preflight_debug.txt"
        )

        let currentBundleId = Bundle.main.bundleIdentifier ?? ""
        let sideloadSuffix = Self.currentSideloadBundleSuffix()
        let suffixText = sideloadSuffix ?? "none"

        // SideStore/AltStore resigning can append the same signing-specific
        // suffix to every installed app bundle identifier. Rather than reading
        // entitlements through SecTask APIs (not exposed to normal iOS app
        // targets), derive that suffix from NeoStation's own installed bundle
        // identifier. This keeps the unsigned GitHub build generic and lets
        // the final SideStore-resigned installation determine the target ID.
        let targetBundleId: String
        if let sideloadSuffix = sideloadSuffix, !sideloadSuffix.isEmpty {
            targetBundleId = "\(targetBaseBundleId).\(sideloadSuffix)"
        } else {
            targetBundleId = targetBaseBundleId
        }

        let openTargetApp = (args["openTargetApp"] as? Bool) ?? false
        let rawLaunch = (args["launchUrl"] as? String) ?? ""
        let launchURL: URL
        if openTargetApp {
            var launchComponents = URLComponents()
            launchComponents.scheme = "stikjit"
            launchComponents.host = "launch-app"
            launchComponents.queryItems = [
                URLQueryItem(name: "bundle-id", value: targetBundleId)
            ]
            guard let generatedLaunchURL = launchComponents.url else {
                result(
                    FlutterError(
                        code: "INVALID_TARGET_LAUNCH_URL",
                        message: "Could not build StikDebug launch-app URL",
                        details: targetBundleId
                    )
                )
                return
            }
            launchURL = generatedLaunchURL
        } else {
            guard let parsedLaunchURL = URL(string: rawLaunch) else {
                result(
                    FlutterError(
                        code: "INVALID_LAUNCH_URL",
                        message: "The delayed launch URL is missing or invalid",
                        details: rawLaunch
                    )
                )
                return
            }
            launchURL = parsedLaunchURL
        }

        var components = URLComponents()
        components.scheme = "stikjit"
        components.host = "enable-jit"
        components.queryItems = [
            URLQueryItem(name: "bundle-id", value: targetBundleId),
            URLQueryItem(name: "script-name", value: scriptName),
        ]
        if let scriptData = args["scriptData"] as? String,
            !scriptData.isEmpty
        {
            components.queryItems?.append(
                URLQueryItem(name: "script-data", value: scriptData)
            )
        }

        guard let preflightURL = components.url else {
            result(
                FlutterError(
                    code: "INVALID_PREFLIGHT_URL",
                    message: "Could not build StikDebug JIT URL",
                    details: nil
                )
            )
            return
        }

        cancelDelayedRetry(reason: "REPLACED_BY_JIT_PREFLIGHT")
        delayedRetryDebugFileName = debugFileName
        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: PREFLIGHT_REQUESTED\n"
                + "NeoStation bundle: \(currentBundleId)\n"
                + "Detected sideload suffix: \(suffixText)\n"
                + "Target base bundle: \(targetBaseBundleId)\n"
                + "Target effective bundle: \(targetBundleId)\n"
                + "Script: \(scriptName)\n"
                + "Warm-up delay: \(delayMs) ms\n"
                + "StikDebug URL: \(preflightURL.absoluteString)\n"
                + "Delayed URL: \(launchURL.absoluteString)"
        )

        delayedRetryBackgroundTask = UIApplication.shared.beginBackgroundTask(
            withName: "NeoStation.JITPreflightLaunch"
        ) { [weak self] in
            guard let self = self else { return }
            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: BACKGROUND_TASK_EXPIRED"
            )
            self.delayedRetryWorkItem?.cancel()
            self.delayedRetryWorkItem = nil
            self.endDelayedRetryBackgroundTask()
        }

        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: false,
            message: delayedRetryBackgroundTask == .invalid
                ? "STATE: BACKGROUND_TASK_UNAVAILABLE"
                : "STATE: BACKGROUND_TASK_STARTED"
        )

        UIApplication.shared.open(preflightURL, options: [:]) { [weak self] opened in
            guard let self = self else {
                result(false)
                return
            }

            guard opened else {
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: PREFLIGHT_OPEN_FAILED"
                )
                self.cancelDelayedRetry(reason: "PREFLIGHT_OPEN_FAILED")
                result(false)
                return
            }

            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: PREFLIGHT_OPENED\nSTATE: GAME_LAUNCH_SCHEDULED\nDelay: \(delayMs) ms"
            )

            let workItem = DispatchWorkItem { [weak self] in
                guard let self = self else { return }
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: GAME_LAUNCH_ATTEMPT\nApplication state: \(Self.applicationStateName())"
                )

                UIApplication.shared.open(launchURL, options: [:]) { [weak self] gameOpened in
                    guard let self = self else { return }
                    Self.writeLaunchDebug(
                        fileName: debugFileName,
                        replace: false,
                        message: gameOpened ? "STATE: GAME_LAUNCH_OPENED" : "STATE: GAME_LAUNCH_FAILED"
                    )
                    self.delayedRetryWorkItem = nil
                    self.endDelayedRetryBackgroundTask()
                }
            }

            self.delayedRetryWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + delaySeconds, execute: workItem)
            result(true)
        }
    }

    /// Runs Universal JIT, foregrounds RPCS3 for its native Start gate,
    /// reattaches with a direct-title script, then returns to RPCS3.
    private func openAppWithTwoPassJit(
        call: FlutterMethodCall,
        result: @escaping FlutterResult
    ) {
        guard let args = call.arguments as? [String: Any],
            let targetBaseBundleId = args["targetBaseBundleId"] as? String,
            !targetBaseBundleId.isEmpty,
            let secondScriptData = args["secondScriptData"] as? String,
            !secondScriptData.isEmpty
        else {
            result(
                FlutterError(
                    code: "INVALID_TWO_PASS_ARGS",
                    message: "openAppWithTwoPassJit requires a target bundle and second-pass script data",
                    details: nil
                )
            )
            return
        }

        func clampedMilliseconds(
            _ key: String,
            fallback: Int,
            minimum: Int,
            maximum: Int
        ) -> Int {
            let raw: Int
            if let value = args[key] as? Int {
                raw = value
            } else if let value = args[key] as? NSNumber {
                raw = value.intValue
            } else {
                raw = fallback
            }
            return min(max(raw, minimum), maximum)
        }

        let initialDelayMs = clampedMilliseconds(
            "initialDelayMs",
            fallback: 11_000,
            minimum: 5_000,
            maximum: 16_000
        )
        let postLaunchDelayMs = clampedMilliseconds(
            "postLaunchDelayMs",
            fallback: 10_000,
            minimum: 4_000,
            maximum: 14_000
        )
        let returnDelayMs = clampedMilliseconds(
            "returnDelayMs",
            fallback: 6_000,
            minimum: 2_000,
            maximum: 8_000
        )
        let secondScriptName = ((args["secondScriptName"] as? String)
            ?? "neostation-rpcs3-direct.js")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let debugFileName = Self.safeDebugFileName(
            (args["debugFileName"] as? String) ?? "rpcs3_launch_debug.txt"
        )

        let currentBundleId = Bundle.main.bundleIdentifier ?? ""
        let sideloadSuffix = Self.currentSideloadBundleSuffix()
        let targetBundleId: String
        if let sideloadSuffix = sideloadSuffix, !sideloadSuffix.isEmpty {
            targetBundleId = "\(targetBaseBundleId).\(sideloadSuffix)"
        } else {
            targetBundleId = targetBaseBundleId
        }

        func makeURL(host: String, items: [URLQueryItem]) -> URL? {
            var components = URLComponents()
            components.scheme = "stikjit"
            components.host = host
            components.queryItems = items
            return components.url
        }

        guard let firstPreflightURL = makeURL(
            host: "enable-jit",
            items: [
                URLQueryItem(name: "bundle-id", value: targetBundleId),
                URLQueryItem(name: "script-name", value: "universal.js"),
            ]
        ), let launchURL = makeURL(
            host: "launch-app",
            items: [URLQueryItem(name: "bundle-id", value: targetBundleId)]
        ), let secondPreflightURL = makeURL(
            host: "enable-jit",
            items: [
                URLQueryItem(name: "bundle-id", value: targetBundleId),
                URLQueryItem(name: "script-name", value: secondScriptName),
                URLQueryItem(name: "script-data", value: secondScriptData),
            ]
        ) else {
            result(
                FlutterError(
                    code: "INVALID_TWO_PASS_URL",
                    message: "Could not construct the RPCS3 two-pass StikDebug URLs",
                    details: targetBundleId
                )
            )
            return
        }

        cancelTwoPassSequence(reason: "REPLACED_BY_NEW_REQUEST")
        twoPassDebugFileName = debugFileName
        Self.writeLaunchDebug(
            fileName: debugFileName,
            replace: true,
            message: "STATE: TWO_PASS_REQUESTED\n"
                + "NeoStation bundle: \(currentBundleId)\n"
                + "Target base bundle: \(targetBaseBundleId)\n"
                + "Target effective bundle: \(targetBundleId)\n"
                + "Initial JIT delay: \(initialDelayMs) ms\n"
                + "Post-Start delay: \(postLaunchDelayMs) ms\n"
                + "Return delay: \(returnDelayMs) ms\n"
                + "Second script: \(secondScriptName)"
        )

        twoPassBackgroundTask = UIApplication.shared.beginBackgroundTask(
            withName: "NeoStation.RPCS3TwoPassLaunch"
        ) { [weak self] in
            guard let self = self else { return }
            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: TWO_PASS_BACKGROUND_EXPIRED"
            )
            self.cancelTwoPassSequence(reason: "BACKGROUND_EXPIRED")
        }

        UIApplication.shared.open(firstPreflightURL, options: [:]) { [weak self] opened in
            guard let self = self else {
                result(false)
                return
            }
            guard opened else {
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: FIRST_PREFLIGHT_OPEN_FAILED"
                )
                self.cancelTwoPassSequence(reason: "FIRST_PREFLIGHT_OPEN_FAILED")
                result(false)
                return
            }

            Self.writeLaunchDebug(
                fileName: debugFileName,
                replace: false,
                message: "STATE: FIRST_PREFLIGHT_OPENED"
            )
            self.scheduleTwoPassWork(afterMilliseconds: initialDelayMs) { [weak self] in
                guard let self = self else { return }
                Self.writeLaunchDebug(
                    fileName: debugFileName,
                    replace: false,
                    message: "STATE: RPCS3_LAUNCH_ATTEMPT"
                )
                UIApplication.shared.open(launchURL, options: [:]) { [weak self] launched in
                    guard let self = self else { return }
                    Self.writeLaunchDebug(
                        fileName: debugFileName,
                        replace: false,
                        message: launched
                            ? "STATE: RPCS3_LAUNCH_OPENED\nACTION: PRESS_START_NOW"
                            : "STATE: RPCS3_LAUNCH_FAILED"
                    )
                    guard launched else {
                        self.cancelTwoPassSequence(reason: "RPCS3_LAUNCH_FAILED")
                        return
                    }

                    self.scheduleTwoPassWork(afterMilliseconds: postLaunchDelayMs) { [weak self] in
                        guard let self = self else { return }
                        Self.writeLaunchDebug(
                            fileName: debugFileName,
                            replace: false,
                            message: "STATE: SECOND_PREFLIGHT_ATTEMPT"
                        )
                        UIApplication.shared.open(secondPreflightURL, options: [:]) { [weak self] secondOpened in
                            guard let self = self else { return }
                            Self.writeLaunchDebug(
                                fileName: debugFileName,
                                replace: false,
                                message: secondOpened
                                    ? "STATE: SECOND_PREFLIGHT_OPENED"
                                    : "STATE: SECOND_PREFLIGHT_FAILED"
                            )
                            guard secondOpened else {
                                self.cancelTwoPassSequence(reason: "SECOND_PREFLIGHT_FAILED")
                                return
                            }

                            self.scheduleTwoPassWork(afterMilliseconds: returnDelayMs) { [weak self] in
                                guard let self = self else { return }
                                Self.writeLaunchDebug(
                                    fileName: debugFileName,
                                    replace: false,
                                    message: "STATE: RPCS3_RETURN_ATTEMPT"
                                )
                                UIApplication.shared.open(launchURL, options: [:]) { [weak self] returned in
                                    guard let self = self else { return }
                                    Self.writeLaunchDebug(
                                        fileName: debugFileName,
                                        replace: false,
                                        message: returned
                                            ? "STATE: TWO_PASS_COMPLETED"
                                            : "STATE: RPCS3_RETURN_FAILED"
                                    )
                                    self.finishTwoPassSequence()
                                }
                            }
                        }
                    }
                }
            }
            result(true)
        }
    }

    private func scheduleTwoPassWork(
        afterMilliseconds delayMs: Int,
        action: @escaping () -> Void
    ) {
        twoPassWorkItem?.cancel()
        let item = DispatchWorkItem(block: action)
        twoPassWorkItem = item
        DispatchQueue.main.asyncAfter(
            deadline: .now() + (Double(delayMs) / 1000.0),
            execute: item
        )
    }

    private func cancelTwoPassSequence(reason: String) {
        if let fileName = twoPassDebugFileName {
            Self.writeLaunchDebug(
                fileName: fileName,
                replace: false,
                message: "STATE: TWO_PASS_CANCELLED\nReason: \(reason)"
            )
        }
        twoPassWorkItem?.cancel()
        twoPassWorkItem = nil
        finishTwoPassSequence()
    }

    private func finishTwoPassSequence() {
        twoPassWorkItem?.cancel()
        twoPassWorkItem = nil
        if twoPassBackgroundTask != .invalid {
            UIApplication.shared.endBackgroundTask(twoPassBackgroundTask)
            twoPassBackgroundTask = .invalid
        }
        twoPassDebugFileName = nil
    }

    /// Returns the suffix SideStore/AltStore appended to NeoStation's original
    /// bundle identifier, if any. Example:
    ///   com.neogamelab.neostation.ABC123
    /// becomes:
    ///   ABC123
    /// The same suffix can then be applied to the official emulator bundle ID.
    private static func currentSideloadBundleSuffix() -> String? {
        let baseBundleId = "com.neogamelab.neostation"
        guard let currentBundleId = Bundle.main.bundleIdentifier,
            !currentBundleId.isEmpty,
            currentBundleId != baseBundleId
        else {
            return nil
        }

        let prefix = "\(baseBundleId)."
        guard currentBundleId.hasPrefix(prefix) else {
            return nil
        }

        let suffix = String(currentBundleId.dropFirst(prefix.count))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return suffix.isEmpty ? nil : suffix
    }

    private func cancelDelayedRetry(reason: String) {
        if delayedRetryWorkItem != nil,
            let fileName = delayedRetryDebugFileName
        {
            Self.writeLaunchDebug(
                fileName: fileName,
                replace: false,
                message: "STATE: \(reason)"
            )
        }
        delayedRetryWorkItem?.cancel()
        delayedRetryWorkItem = nil
        endDelayedRetryBackgroundTask()
        delayedRetryDebugFileName = nil
    }

    private func endDelayedRetryBackgroundTask() {
        guard delayedRetryBackgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(delayedRetryBackgroundTask)
        delayedRetryBackgroundTask = .invalid
    }

    private static func applicationStateName() -> String {
        switch UIApplication.shared.applicationState {
        case .active:
            return "active"
        case .inactive:
            return "inactive"
        case .background:
            return "background"
        @unknown default:
            return "unknown"
        }
    }

    private static func safeDebugFileName(_ value: String) -> String {
        let candidate = URL(fileURLWithPath: value).lastPathComponent
        return candidate.isEmpty ? "jit_launch_debug.txt" : candidate
    }

    private static func writeLaunchDebug(
        fileName: String,
        replace: Bool,
        message: String
    ) {
        guard let documents = FileManager.default.urls(
            for: .documentDirectory,
            in: .userDomainMask
        ).first else { return }

        let fileURL = documents.appendingPathComponent(fileName)
        let line = "--- \(ISO8601DateFormatter().string(from: Date())) ---\n\(message)\n"
        guard let data = line.data(using: .utf8) else { return }

        do {
            if replace || !FileManager.default.fileExists(atPath: fileURL.path) {
                try data.write(to: fileURL, options: .atomic)
            } else {
                let handle = try FileHandle(forWritingTo: fileURL)
                defer { try? handle.close() }
                try handle.seekToEnd()
                try handle.write(contentsOf: data)
            }
        } catch {
            // Diagnostics must never interfere with launching a game.
        }
    }

    // MARK: - Open In

    /// Presents iOS's genuine "Open In" menu for a file — a different API
    /// from the general Share Sheet (UIActivityViewController, used
    /// elsewhere via the share_plus package). "Open In" specifically hands
    /// the file to an app that declared itself able to *own*/import that
    /// document type, which is the traditional "here's a file, please open
    /// it" flow — distinct from "here's some content, do something with
    /// it" (sharing). Whether RetroArch actually treats these two
    /// differently (e.g. jumping straight into a game it already
    /// recognizes vs. re-importing) is exactly what this exists to test.
    private func openInMenu(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any],
            let filePath = args["path"] as? String
        else {
            result(
                FlutterError(
                    code: "INVALID_ARGS",
                    message: "openInMenu requires a 'path' string argument",
                    details: nil
                )
            )
            return
        }

        guard let rootVC = Self.topViewController(), let view = rootVC.view else {
            result(
                FlutterError(
                    code: "NO_ROOT_VC",
                    message: "No root view controller available to present the menu from",
                    details: nil
                )
            )
            return
        }

        let fileURL = URL(fileURLWithPath: filePath)
        guard FileManager.default.fileExists(atPath: filePath) else {
            result(
                FlutterError(
                    code: "FILE_NOT_FOUND",
                    message: "No file at \(filePath)",
                    details: nil
                )
            )
            return
        }

        let controller = UIDocumentInteractionController(url: fileURL)
        controller.delegate = self
        documentInteractionController = controller

        // Centered rect as a reasonable default anchor for the iPad
        // popover; exact position doesn't affect whether an app can open
        // the file, only where the menu visually appears from.
        let anchorRect = CGRect(
            x: view.bounds.midX - 1,
            y: view.bounds.midY - 1,
            width: 2,
            height: 2
        )

        let didPresent = controller.presentOpenInMenu(
            from: anchorRect,
            in: view,
            animated: true
        )
        result(didPresent)
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
