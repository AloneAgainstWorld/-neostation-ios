# RPCS3 iOS — stable basic launch

NeoStation currently uses the conservative RPCS3 path on iOS:

1. NeoStation asks StikDebug to enable Universal JIT for RPCS3 with `universal.js`.
2. RPCS3 opens through its normal flow.
3. RPCS3 handles Start and game selection.

NeoStation does not currently try to press **Start / Commencer** automatically and does not depend on an iOS Personal Automation, Switch Control recipe, saved gesture, delayed foreground handoff, or Apple Shortcut for the stable RPCS3 path.

The `NeoStation+RPCS3+Start` Shortcut experiment and its Personal Automation were tested on iOS 27 but were not reliable enough to ship as part of the normal launch flow. Any existing RPCS3 automation can therefore be **disabled or removed** without affecting NeoStation's standard RPCS3 launch.

## Why NeoStation stops at the RPCS3 start screen

The currently integrated RPCS3 build does not expose a supported NeoStation-facing deep link, App Intent, or equivalent public direct-launch interface for selecting a specific PS3 title. Trying to reproduce a tap through device-local accessibility automation added more failure points than value.

Until RPCS3, another iOS PS3 emulator, or a future compatible build exposes a reliable deep link/direct-launch mechanism, the stable behavior is intentionally:

`NeoStation -> StikDebug / universal.js -> RPCS3 -> user presses Start -> user chooses the game`

This keeps JIT launching reliable while avoiding fragile UI automation.
