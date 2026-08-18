# RPCS3 iOS — optional Switch Control auto-Start

NeoStation Build 140 removes the experimental RPCS3Core memory-injection / second-pass StikDebug launcher. The stable PS3 launch path is now:

1. NeoStation asks StikDebug to enable JIT for RPCS3 with `universal.js`.
2. RPCS3 opens normally.
3. Without any automation, the user presses **Start / Commencer** and chooses a game in RPCS3.

An optional **device-local** iOS automation can try to press RPCS3's Start button automatically when RPCS3 opens. This is intentionally separate from NeoStation because iOS does not provide third-party apps with a public API to create Switch Control switches, recipes, saved gestures, or Personal Automations.

## Why the automation cannot be pre-bound by NeoStation

The tap coordinate and the Switch Control switch/recipe belong to the user's Accessibility configuration. A shared Shortcut cannot safely create or bind those private device entities for another user. NeoStation therefore opens Apple's official Shortcut editor from its setup service, but the following one-time Accessibility setup must be done on the iPhone.

## 1. Create the Switch Control gesture

On the iPhone:

1. Open **Settings > Accessibility > Switch Control > Switches**.
2. Add a local switch. A convenient test source is **Screen > Full Screen**.
3. Assign a normal action such as **Select Item** for the base switch.
4. Go back to **Switch Control > Recipes**.
5. Create a recipe named **NeoStation RPCS3 Start**.
6. Assign the switch created above to a **Custom Gesture**.
7. Record a single tap at the exact location of RPCS3's **Start / Commencer** button, using the same orientation in which RPCS3 is normally opened.
8. Save the recipe.

If the device exposes **Switch Sets**, a dedicated set named `NeoStation RPCS3` can be created to isolate this switch/recipe from normal Switch Control usage.

## 2. Create the Shortcut

Create a Shortcut named exactly:

`NeoStation+RPCS3+Start`

Recommended actions:

1. **Set Switch Control** -> On.
2. If available on the installed iOS version, **Set Switch Control Switch Set** -> `NeoStation RPCS3`.
3. **Set Switch Control Switch State** -> select the switch used by the recipe and toggle/activate it.
4. **Set Switch Control** -> Off.

If the tap happens before RPCS3 has rendered its Start screen, add the shortest Wait action that is actually required on that device. Do not increase it unless on-device testing shows that RPCS3 is not ready yet.

The important experiment is whether **Set Switch Control Switch State** causes the assigned recipe/custom gesture to execute on the installed iOS build. Apple documents that the action can manipulate configured Switch Control switches, but does not promise that every switch source/recipe combination will synthesize a gesture.

## 3. Create the Personal Automation

In **Shortcuts > Automation**:

1. Create a new Personal Automation.
2. Choose **App**.
3. Select **RPCS3**.
4. Choose **Is Opened**.
5. Select **Run Immediately** when that option is available.
6. Add **Run Shortcut** -> `NeoStation+RPCS3+Start`.

This event-based trigger is preferred over NeoStation timers: the shortcut starts because iOS reports that RPCS3 actually opened.

## Expected outcomes

### Automation works

NeoStation -> StikDebug -> RPCS3 -> Switch Control gesture -> Start screen is pressed automatically.

The user still chooses the game in RPCS3 unless RPCS3 later exposes a supported deep link/App Intent for a specific title.

### Automation does not execute the gesture

Leave the Personal Automation disabled or remove it. NeoStation continues to use the stable standard RPCS3 launch, so the user simply presses Start manually and selects the game. No second-pass injection, RPCS3Core UUID, boot offset, or internal boot call is involved anymore.
