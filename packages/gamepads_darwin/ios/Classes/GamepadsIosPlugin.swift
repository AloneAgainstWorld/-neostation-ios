// iOS gamepad bridge for NeoStation.
//
// The GameController framework exposes stable logical elements (buttonA,
// dpad, leftThumbstick, ...). Do not use sfSymbolsName as an input protocol:
// those strings are presentation metadata and are not the names understood by
// NeoStation's cross-platform translator. Emit the same canonical logical names
// used by the Windows GameInput backend instead.
import UIKit
import GameController
import Flutter

public class GamepadsIosPlugin: NSObject, FlutterPlugin {
    let channel: FlutterMethodChannel
    let gamepads = GamepadsListener()

    init(channel: FlutterMethodChannel) {
        self.channel = channel
        super.init()

        self.gamepads.listener = onGamepadEvent

        // Keep physical MFi/Bluetooth controllers monitored consistently when
        // NeoStation temporarily loses the foreground during emulator launches.
        if #available(iOS 14.5, *) {
            GCController.shouldMonitorBackgroundEvents = true
        }
    }

    public static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "xyz.luan/gamepads",
            binaryMessenger: registrar.messenger()
        )
        let instance = GamepadsIosPlugin(channel: channel)
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "listGamepads":
            result(listGamepads())
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    private func onGamepadEvent(
        gamepadId: Int,
        gamepad: GCExtendedGamepad,
        element: GCControllerElement
    ) {
        for (key, value) in getValues(gamepad: gamepad, element: element) {
            let arguments: [String: Any] = [
                "gamepadId": String(gamepadId),
                "time": Int(getTimestamp(gamepad: gamepad)),
                "type": element.isAnalog ? "analog" : "button",
                "key": key,
                "value": value,
            ]
            channel.invokeMethod("onGamepadEvent", arguments: arguments)
        }
    }

    /// Converts GameController elements into a stable vocabulary shared with
    /// NeoStation's Dart input translator. Values stay in GameController's
    /// native ranges: digital buttons [0, 1], sticks [-1, 1], triggers [0, 1].
    private func getValues(
        gamepad: GCExtendedGamepad,
        element: GCControllerElement
    ) -> [(String, Float)] {
        // Face buttons.
        if element === gamepad.buttonA { return [("a", gamepad.buttonA.value)] }
        if element === gamepad.buttonB { return [("b", gamepad.buttonB.value)] }
        if element === gamepad.buttonX { return [("x", gamepad.buttonX.value)] }
        if element === gamepad.buttonY { return [("y", gamepad.buttonY.value)] }

        // Shoulders and triggers.
        if element === gamepad.leftShoulder {
            return [("leftshoulder", gamepad.leftShoulder.value)]
        }
        if element === gamepad.rightShoulder {
            return [("rightshoulder", gamepad.rightShoulder.value)]
        }
        if element === gamepad.leftTrigger {
            return [("lefttrigger", gamepad.leftTrigger.value)]
        }
        if element === gamepad.rightTrigger {
            return [("righttrigger", gamepad.rightTrigger.value)]
        }

        // Menu/system buttons.
        if element === gamepad.buttonMenu {
            return [("menu", gamepad.buttonMenu.value)]
        }
        if let options = gamepad.buttonOptions, element === options {
            return [("view", options.value)]
        }
        if let home = gamepad.buttonHome, element === home {
            return [("home", home.value)]
        }
        if let leftStickButton = gamepad.leftThumbstickButton,
           element === leftStickButton {
            return [("leftthumbstick", leftStickButton.value)]
        }
        if let rightStickButton = gamepad.rightThumbstickButton,
           element === rightStickButton {
            return [("rightthumbstick", rightStickButton.value)]
        }

        // D-pad. Emit four digital directions so press/release state is
        // explicit, including diagonals.
        if element === gamepad.dpad ||
            element === gamepad.dpad.xAxis ||
            element === gamepad.dpad.yAxis {
            let x = gamepad.dpad.xAxis.value
            let y = gamepad.dpad.yAxis.value
            return [
                ("dpadleft", max(0.0, -x)),
                ("dpadright", max(0.0, x)),
                ("dpadup", max(0.0, y)),
                ("dpaddown", max(0.0, -y)),
            ]
        }

        // Left thumbstick.
        if element === gamepad.leftThumbstick ||
            element === gamepad.leftThumbstick.xAxis ||
            element === gamepad.leftThumbstick.yAxis {
            return [
                ("leftthumbstickx", gamepad.leftThumbstick.xAxis.value),
                ("leftthumbsticky", gamepad.leftThumbstick.yAxis.value),
            ]
        }

        // Right thumbstick.
        if element === gamepad.rightThumbstick ||
            element === gamepad.rightThumbstick.xAxis ||
            element === gamepad.rightThumbstick.yAxis {
            return [
                ("rightthumbstickx", gamepad.rightThumbstick.xAxis.value),
                ("rightthumbsticky", gamepad.rightThumbstick.yAxis.value),
            ]
        }

        return []
    }

    private func getTimestamp(gamepad: GCExtendedGamepad) -> TimeInterval {
        if #available(iOS 14.0, *) {
            return gamepad.lastEventTimestamp
        } else {
            return Date().timeIntervalSince1970
        }
    }

    private func getName(gamepad: GCExtendedGamepad) -> String {
        if #available(iOS 14.0, *) {
            let device = gamepad.device
            return maybeConcat(device?.vendorName, device?.productCategory)
                ?? "Unknown device"
        } else {
            return "Unknown device"
        }
    }

    private func listGamepads() -> [[String: Any?]] {
        return gamepads.gamepads.enumerated().map { (index, gamepad) in
            ["id": String(index), "name": getName(gamepad: gamepad)]
        }
    }

    private func maybeConcat(_ strings: String?...) -> String? {
        let nonNull = strings.compactMap { $0 }
        if nonNull.isEmpty { return nil }
        return nonNull.joined(separator: " - ")
    }
}
