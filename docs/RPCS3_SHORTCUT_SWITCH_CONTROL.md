# RPCS3 iOS — Switch Control auto-Start

NeoStation keeps the experimental RPCS3Core memory-injection / second-pass StikDebug launcher retired. The stable PS3 launch path is:

1. NeoStation starts StikDebug Universal JIT for RPCS3 with `universal.js`.
2. The native iOS preflight helper waits about 8 seconds for the JIT warm-up.
3. NeoStation asks StikDebug to foreground RPCS3 with its `launch-app` URL.
4. iOS sees RPCS3 open and triggers the device-local Personal Automation.
5. The automation runs the exact Shortcut `NeoStation+RPCS3+Start`.
6. The Shortcut selects the `NeoStation RPCS3` Switch Control set and activates the configured `Full Screen` switch.
7. The Switch Control recipe/macro runs its custom gesture and taps RPCS3's **Start / Commencer** button.

This intentionally does **not** try to launch the Shortcut from NeoStation after NeoStation has entered the background. The previous direct handoff could be rejected by iOS even though the Shortcuts URL itself was valid.

The Accessibility configuration and Personal Automation are device-local. iOS does not give NeoStation a public API to create the user's Switch Control switch, switch set, recipe/macro, custom tap gesture, or Personal Automation, so those pieces must be configured once on the iPhone.

## 1. Configure Switch Control

On the iPhone:

1. Open **Settings > Accessibility > Switch Control > Switches**.
2. Add **Screen > Full Screen** and use a normal base action such as **Select Item**.
3. Create a recipe/macro named **NeoStation RPCS3 Start**.
4. Assign **Full Screen** to a **Custom Gesture**.
5. Record a single tap at the exact position of RPCS3's **Start / Commencer** button, using the same device orientation in which RPCS3 opens.
6. Create a Switch Control set named **NeoStation RPCS3** and keep the configured Full Screen switch/recipe in that set.

The exact labels can vary slightly by iOS language/version. On the iOS 27 setup used for NeoStation testing, the switch set, `Full Screen` switch state, and recipe/macro are exposed directly.

## 2. Create the Shortcut

Create a Shortcut named exactly:

`NeoStation+RPCS3+Start`

Use these actions in this order:

1. **Set Switch Control Switch Set** -> `NeoStation RPCS3`.
2. **Set Switch Control Switch State** -> activate `Full Screen`.
3. **Wait** -> 1 second.
4. **Set Switch Control Switch State** -> deactivate `Full Screen`.

Do **not** add **Open App -> RPCS3** at the top of this Shortcut when using the Personal Automation described below. RPCS3 is already foregrounded before the automation runs. Re-opening it from the Shortcut can retrigger the same app-open automation and cause a loop or duplicate execution.

The 1-second wait keeps the switch active briefly enough for the configured recipe/gesture to run. Adjust it only if on-device testing shows that a different delay is required.

## 3. Create and enable the Personal Automation

In **Shortcuts > Automation**:

1. Create a Personal Automation for **App**.
2. Select **RPCS3**.
3. Choose **Is Opened / Est ouverte**.
4. Set it to **Run Immediately / Exécuter immédiatement** when that option is available.
5. Add **Run Shortcut / Exécuter le raccourci** -> `NeoStation+RPCS3+Start`.
6. Make sure the automation itself is enabled.

The automation may be named something like `RPCS3 Auto Start`; its display name is not used by NeoStation. The exact Shortcut name `NeoStation+RPCS3+Start` is the important part.

## Expected path

`NeoStation -> StikDebug / universal.js -> RPCS3 opens -> Personal Automation -> NeoStation+RPCS3+Start -> Switch Control -> Start / Commencer`

If the automation does not fire, first verify that the Personal Automation is enabled and configured to run immediately. If it fires but the gesture misses the button, adjust only the Switch Control gesture or its short wait; do not add a second RPCS3 app-open action to the Shortcut.

No RPCS3Core UUID, boot offset, internal boot call, or second-pass injection is used by this flow.
