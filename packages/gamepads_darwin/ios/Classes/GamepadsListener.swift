import Foundation
import GameController

class GamepadsListener {
    var gamepads: [GCExtendedGamepad] = []
    var listener: ((Int, GCExtendedGamepad, GCControllerElement) -> Void)?

    init() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(joystickDidConnect),
            name: .GCControllerDidConnect,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(joystickDidDisconnect),
            name: .GCControllerDidDisconnect,
            object: nil
        )

        // A controller may already be connected before Flutter registers this
        // plugin. GCControllerDidConnect is not replayed for those devices, so
        // relying on notifications alone leaves the app with an empty list and
        // no valueChangedHandler until the user disconnects/reconnects the pad.
        // Register the controllers iOS already knows about immediately.
        for controller in GCController.controllers() {
            register(controller)
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func joystickDidConnect(notification: NSNotification) {
        guard let controller = notification.object as? GCController else { return }
        register(controller)
    }

    @objc private func joystickDidDisconnect(notification: NSNotification) {
        guard let controller = notification.object as? GCController,
              let disconnected = controller.extendedGamepad else { return }

        gamepads.removeAll(where: { $0 == disconnected })
        refreshPlayerIndices()
    }

    private func register(_ controller: GCController) {
        guard let gamepad = controller.extendedGamepad else { return }
        guard !gamepads.contains(where: { $0 == gamepad }) else { return }

        gamepads.append(gamepad)
        refreshPlayerIndices()

        // Resolve the index at event time instead of capturing the connection
        // index forever. If controller 1 disconnects, the remaining controllers
        // are re-indexed and continue reporting the same IDs as listGamepads().
        gamepad.valueChangedHandler = { [weak self] gamepad, element in
            guard let self,
                  let gamepadId = self.gamepads.firstIndex(of: gamepad) else {
                return
            }
            self.listener?(gamepadId, gamepad, element)
        }
    }

    private func refreshPlayerIndices() {
        for (index, gamepad) in gamepads.enumerated() {
            gamepad.controller?.playerIndex = toPlayerIndex(index: index)
        }
    }

    private func toPlayerIndex(index: Int) -> GCControllerPlayerIndex {
        switch index {
        case 0:
            return GCControllerPlayerIndex.index1
        case 1:
            return GCControllerPlayerIndex.index2
        case 2:
            return GCControllerPlayerIndex.index3
        case 3:
            return GCControllerPlayerIndex.index4
        default:
            return GCControllerPlayerIndex.indexUnset
        }
    }
}
