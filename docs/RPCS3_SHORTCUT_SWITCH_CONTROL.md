# RPCS3 iOS — Switch Control auto-Start

NeoStation keeps the experimental RPCS3Core memory-injection / second-pass StikDebug launcher retired. The current PS3 launch path is intentionally simpler:

1. NeoStation starts the normal StikDebug Universal JIT flow for RPCS3 with `universal.js`.
2. The native iOS preflight helper keeps a short background task alive and waits about 8 seconds for the JIT/RPCS3 foreground transition.
3. NeoStation then opens Apple's `shortcuts://run-shortcut` URL for the exact helper named `NeoStation+RPCS3+Start`.
4. The Shortcut selects the `NeoStation RPCS3` Switch Control set and activates the configured `Full Screen` switch.
5. The Switch Control recipe/macro runs its custom gesture and taps RPCS3's **Start / Commencer** button.

The Accessibility configuration is still device-local. iOS does not give NeoStation a public API to create the user's Switch Control switch, switch set, recipe/macro, or custom tap gesture, so those pieces must be configured once on the iPhone.

## 1. Configure Switch Control

On the iPhone:

1. Open **Settings > Accessibility > Switch Control > Switches**.
2. Add **Screen > Full Screen** and use a normal base action such as **Select Item**.
3. Create a recipe/macro named **NeoStation RPCS3 Start**.
4. Assign **Full Screen** to a **Custom Gesture**.
5. Record a single tap at the exact position of RPCS3's **Start / Commencer** button, using the same device orientation in which RPCS3 opens.
6. Create a Switch Control set named **NeoStation RPCS3** and keep the configured Full Screen switch/recipe in that set.

The exact labels can vary slightly by iOS language/version. On iOS 27, the configuration observed during NeoStation testing exposes the switch set, `Full Screen` switch state, and recipe/macro directly.

## 2. Create the Shortcut

Create a Shortcut named exactly:

`NeoStation+RPCS3+Start`

For the current iOS 27 setup, use these actions in this order:

1. **Set Switch Control Switch Set** -> `NeoStation RPCS3`.
2. **Set Switch Control Switch State** -> activate `Full Screen`.
3. **Wait** -> 1 second.
4. **Set Switch Control Switch State** -> deactivate `Full Screen`.

The 1-second wait is only there to keep the switch active briefly enough for the configured recipe/gesture to run. Adjust it only if on-device testing proves that a different delay is required.

## 3. Personal Automation is not required

Older NeoStation builds relied on a **Personal Automation** triggered when RPCS3 opened. Builds containing the direct Shortcut handoff now invoke `NeoStation+RPCS3+Start` themselves after the JIT warm-up, so that Personal Automation is **not required**.

If an old Personal Automation such as **When RPCS3 is opened -> Run NeoStation+RPCS3+Start** is still enabled, disable it before testing the direct NeoStation path. Otherwise the Shortcut can run twice.

## Expected path

`NeoStation -> StikDebug / universal.js -> RPCS3 -> NeoStation+RPCS3+Start -> Switch Control -> Start / Commencer`

The selected RPCS3 Title ID is also passed to the Shortcut as optional text input for diagnostics/future revisions. The current Switch Control helper does not need to consume that input.

## On-device fallback

The final foreground behavior of Apple's Shortcuts URL scheme can vary by iOS release. If on-device testing shows that running the Shortcut leaves the Shortcuts app in the foreground when the custom gesture fires, add an **Open App -> RPCS3** action immediately before activating `Full Screen`, then test again. If that still does not behave reliably, the previous Personal Automation remains a valid fallback while NeoStation keeps the stable Universal JIT launch path.

No RPCS3Core UUID, boot offset, internal boot call, or second-pass injection is used by this flow.
