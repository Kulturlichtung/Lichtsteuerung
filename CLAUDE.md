# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repo contains **Q Light Controller+ (QLC+) workspace files**, split into two folders since
2026-07-24 because QLC+5 isn't available for the Raspberry Pi deployment target yet (see
"Deployment target" below):

- **`qlcplus5/`** — the QLC+5 lineage. `2026-07_kulturlichtung_v2.qxw` is a frozen, stable
  backup (last known-good `Time`-mode Sound-to-Light setup, `TempoType` confirmed
  non-functional on this build — see below). `2026-07_kulturlichtung_v3.qxw` is the active
  QLC+5 file, forked from v2 on 2026-07-23 to prototype an OSC/Cue-List-based beat-sync
  architecture (see "Sound-to-Light wiring" below) — treat v3 as the one to edit going
  forward; only touch v2 again if the v3 experiment needs to be abandoned and reverted from a
  clean baseline.
- **`qlcplus4/`** — a QLC+4.14.4-compatible port, `2026-07_kulturlichtung_v4.qxw`, forked from
  v3 on 2026-07-24. All XML constructs v3 uses (`SoloFrame`, `CueList` incl. external-input
  `Next` binding, `Chaser`/`SpeedModes`, `Monitor`, `BeatGenerator`) were checked against
  `mcallegari/qlcplus` at tag `QLC+_4.14.4` and load unchanged there — only the
  `<Creator><Version>` string differs from v3. Notably, QLC+4.14.4's `Chaser::loadXML` *does*
  implement `<TempoType>` (`engine/src/chaser.cpp`), unlike the installed QLC+5.2.2 (see the
  `TempoType` gotcha below) — unverified at runtime, only against source; re-confirm with a
  real `-d -g` log before relying on it, per the "Version mismatch warning" below.
  `qlcplus4/portable-qlcplus4/` holds a locally downloaded QLC+4 Windows installer for testing
  this port; it's gitignored, not part of the tracked repo content.
- **`qlcplus4/2026-07_kulturlichtung_v5.qxw`** — **not** part of the v2→v3→v4 test/prototype
  lineage above. This is the user's real production/venue rig, built and saved directly in
  QLC+4.14.4 itself (not authored by Claude) — `<Author>reich</Author>` (the user). Confirmed
  2026-07-30 by inspecting its content: real fixtures (`Fun-Generation LED Pot 12x1W QCL RGB WW`
  x4, now 8-channel mode: `0=Master,1=R,2=G,3=B,4=W`, channels 5–7 unused + an Eurolite LED Mini
  Strobe Cluster SMD 48, 3-channel), a real `DMX USB PRO` output (with serial number), and an OSC
  input already wired to `BeatDetector beat_osc.py` (i.e. the external-beat-detector OSC path
  from "Sound-to-Light wiring" above is already live here, not just planned). Treat this file as
  higher-stakes than the others — it's live show content, not a test/prototype file. Discovered
  while diagnosing a `.qxw` file-association issue (see git/session history); it landed in this
  folder from the user's own QLC+4 "Save As", unrelated to the repo's versioning scheme — don't
  assume it follows the same conventions (naming, structure, gotcha-fixes) documented for v2–v4
  above unless re-verified against its actual content.

  **Update 2026-07-30 — v5's actual S2L design is far beyond the single-prototype stage this doc
  used to describe.** Re-inspected v5 in full: the OSC-beat-driven `CueList` Next-Cue pattern
  from "Cue List / OSC prototype (v3)" below isn't a prototype here — it's rolled out to a full
  **3-layer Sound-to-Light system**, all 5 color-combos (Blau-Rosa, Rot-Weiss, Gruen-Gelb,
  Blau-Gelb, Bunt) × 3 layers, each with its own beat-advanced `CueList`:
  - **Fade** — Functions 20/24/28/32/34, 2-color crossfade Chasers (`FadeIn=2000`,
    `Hold=28000`).
  - **Direkt** — Functions 13–17, hard-cut Chasers (the original S2L Chasers, `Hold=30000`).
  - **Alternierend** — Functions 43–47, `Type="Collection"` combining a per-fixture "Checker"
    Chaser (two fixtures show color A, two show color B, alternating — new Scenes 18/19, 22/23,
    26/27, 30/31, 35–38) with a shared Strobo-Takt Chaser (ID 42: 250 ms flash / 30 s off) so
    strobe runs alongside every Alternierend color.

  All Chasers across all 3 layers use `Hold="30000"` per step and are advanced by dedicated
  `CueList` widgets (15 of them, IDs 100–137) whose `<Next><Input Universe="0" Channel="4182"/>`
  all point at the **same** beat-OSC channel — the 30 s hold is just the "never auto-advance on
  its own" safety net documented in "Cue List / OSC prototype" below, actual advance is beat-only.
  All ~20 color/layer buttons are flat children of one `SoloFrame` (ID 90, "Sound to Light") so
  only one Chaser is ever running at a time, matching the single shared beat channel.

  **`qlcplus4/2026-07_kulturlichtung_v6.qxw`** — Claude-authored, forked from v5 on 2026-07-30 to
  add a 4th layer, **"Alternierend mit Aus"**: same color-combos, but alternating each color with
  a full blackout (`Farbe1, Aus, Farbe2, Aus`, looping) instead of the Checker split-fixture
  pattern — reuses the existing `Aus` Scene (ID 9, all-zero incl. master dimmer) and the existing
  Strobo-Takt Chaser (ID 42, same as the Alternierend layer) rather than duplicating either.
  New Functions: Chasers 48–52 (one per combo; Bunt/52 is 7×(color,Aus)=14 steps, others are
  4-step 2-color loops), Collections 53–57 (each = its AltAus-Chaser + Strobo-Takt 42, mirroring
  how 43–47 wrap the Checker-Chasers). New VC: a 4th button row (Frame ID 123 + Buttons 124–128)
  added flat under `SoloFrame` 90 alongside the other 3 layers (same mutual-exclusion pool),
  `SoloFrame` 90's height grown 455→595 to fit it. New CueLists 142–146 (bound to Chasers 48–52,
  *not* the Collections — `CueList`'s `<Chaser>` tag needs an actual Chaser, same constraint the
  existing 15 CueLists already follow) reuse the same shared `Channel="4182"` beat input; no new
  CueList needed for strobe since Chaser 42 already has one (ID 141), shared across layers.
  Virtual Console canvas widened (`Properties/Size` 1920→2260) to fit CueLists 142–146 as a 4th
  column at X=1920. Validated by XML-parsing v6 and diffing Function/widget IDs against v5 for
  collisions — **not yet opened in QLC+ or tested against the real rig**; do that before treating
  v6 as anything but a draft. If it's approved and becomes the new production file, update this
  section (and the "real production/venue rig" framing above) to point at v6 instead of v5.

`beat-detector/beat_osc.py` is the companion Python script (mic → OSC) that drives the Cue List;
see top-level `README.md` for setup/usage (local Windows test + Raspberry Pi deployment
placeholder). It is not a software project with a build pipeline — it's a lighting-control
configuration (XML) for QLC+, driving a DMX rig via a Virtual Console (VC). There is no build,
lint, or test tooling; "correctness" is validated by opening the file in QLC+ (or reasoning about
its XML/engine semantics) and checking the Virtual Console behaves as expected.

**Deployment target:** the finished setup is meant to run standalone on a **Raspberry Pi** with a
USB microphone, unattended (no operator present) — Pi not yet set up as of 2026-07-19, QLC+ version
for it undecided. Everything currently being tested runs on a separate **Windows dev machine**
(below); don't assume Windows-specific findings (especially the `TempoType` gotcha further down)
automatically apply to the Pi's eventual QLC+ install — see the Sound-to-Light section for why.
Because there's no operator on the Pi, any "requires a person to do X live" workaround (e.g. manual
tap-tempo) is a non-solution for the real deployment, even if it works fine for testing on Windows.

**Update 2026-07-30 — Pi is a Raspberry Pi 5 (4GB), hardware chosen.** Full step-by-step setup
guide written (README.md's "Raspberry Pi: Schritt-für-Schritt-Einrichtung" section) + supporting
config template, start scripts, and systemd units in `pi-setup/`: QLC+4.14.4 built from source
(no arm64 package publicly available, checked against the official OBS repo), `overlayroot`
package for a read-only root (not raspi-config's own overlay option, which blanket-locks every
mounted filesystem on Bookworm, including the USB stick — see the "Auto-layer" section's Web
Access research for the overlayroot vs. raspi-config finding), USB stick (exFAT, `nofail` in
fstab) holding the `.qxw` + a `lichtsteuerung.conf` config file so the active project and
boot-time Auto-color are swappable without touching the Pi. **None of this is verified against
real Pi hardware yet** — same "don't trust it until tested live" rule as everywhere else in this
file.

**Update 2026-07-30 — QLC+5 uninstalled, only QLC+4 (classic UI) now present.** The user installed
QLC+4 alongside QLC+5, then uninstalled QLC+5 afterward; `D:\Josef\QLC+5\` no longer exists on
disk (confirmed 2026-07-30). The paragraph below (QML UI, `D:\Josef\QLC+5\`) describes a **past**
setup — kept for history since the `qlcplus5/*.qxw` files and their QML-UI-specific findings
(TempoType, the `-d -g` debug-flag syntax) still exist and would apply again if QLC+5 gets
reinstalled. **Current reality:** the only installed/running QLC+ is `D:\Josef\QLC+4\qlcplus.exe`
— the **classic Qt-Widgets desktop UI** (`ui/src/virtualconsole/*.cpp` in `mcallegari/qlcplus`),
*not* the QML UI. So the "prefer `qmlui/virtualconsole/`" advice below is now backwards: prefer
`ui/src/virtualconsole/` when checking widget XML schema against source, since that's what's
actually running now. The core engine (`engine/src/*.cpp`) is shared between both UIs regardless,
so engine-level behavior (Scene/Chaser timing, HTP/LTP mixing) still applies either way. Also note:
this classic UI's CLI parsing differs from the QML UI's (see "CLI/file-association gotcha" below)
— don't reuse the QML UI's `-d -g` debug-log recipe verbatim against `qlcplus.exe`.

The user previously ran the **QML UI** build (`qlcplus-qml.exe`, on Windows at `D:\Josef\QLC+5\`),
accessed from this WSL environment via `/mnt/d/...` and `/mnt/c/...`. This is a distinct codebase
from the classic Qt-Widgets desktop UI (`ui/src/virtualconsole/*.cpp` in the `mcallegari/qlcplus`
repo) — the QML UI's own VC widget sources live under `qmlui/virtualconsole/*.cpp` and can have
different XML tag support than the classic UI. When checking a widget's XML schema against source,
prefer `qmlui/virtualconsole/` over `ui/src/virtualconsole/` since that's what was actually running
**at the time this paragraph was written** — see the update note above for the current situation.
The core engine (`engine/src/*.cpp` — Function, Chaser, ChaserStep, ChaserRunner, Doc) is shared
between both UIs, so engine-level behavior (Scene/Chaser timing, HTP/LTP mixing) applies regardless
of which UI is used.

**Version mismatch warning — GitHub source, even at a matching tag, is not reliable evidence of
this Windows binary's actual behavior.** *(2026-07-30: this whole warning was written against the
QLC+5.2.2 install, which has since been uninstalled — see the "Update 2026-07-30" note above. Kept
verbatim since it applies again if QLC+5 is reinstalled; the general lesson — verify against a real
`-d -g`/`-d <level> -g` log, don't trust source-diffing alone — applies to QLC+4 too, see the
CLI/file-association gotcha below for a QLC+4-specific example of source-vs-runtime mismatch.)* The
installed app self-reports QLC+ **5.2.2**
(`--version`), and its `.exe` build date (2026-06-13) matches the `QLC+_5.2.2` GitHub tag's release
date almost exactly. Despite that, one feature checked directly against `engine/src/chaser.cpp`
**at that exact tag** (`Chaser`'s `<TempoType>` XML tag, for beat-synced chasers) — confirmed
present in the load dispatch, not just a comment or the save path — turned out to be **absent at
runtime**: the tag was silently logged as unknown and ignored (see the Sound-to-Light section
below). So this specific binary doesn't behave like its own matching tagged source, for unknown
reasons. Conclusion: don't trust GitHub source diffing (even against a version/date-matched tag) as
proof of what this Windows install actually does — only the `-d -g` debug log is authoritative
here. This caveat is specific to the Windows dev machine; it may not apply to whatever QLC+ build
ends up on the Raspberry Pi deployment target (see above) — test fresh there too, don't assume.

## Working with `.qxw` files

- `.qxw` is QLC+'s native XML workspace format (`xmlns="http://www.qlcplus.org/Workspace"`).
- QLC+'s parser is a strict `readNextStartElement` dispatch by exact tag name: any element it
  doesn't recognize is logged as `"Unknown <thing> tag: <name>"` and its **entire subtree is
  skipped** — including any valid, well-formed content nested inside an unrecognized wrapper.
  This is silent unless you're capturing debug output (see below) — no XML error, the file loads
  "successfully," it just quietly has less content than you wrote. Don't introduce a grouping/
  wrapper element that doesn't appear in QLC+'s own exports — check by diffing against a file
  QLC+ itself saved, or against the engine source, before assuming a container tag is fine.
- No CLI validation tool or linter is available in this environment (`qlcplus` is not installed in
  WSL) — verify structural changes by re-reading the diff and cross-checking IDs/references, or by
  capturing real load-time output (see "Diagnosing silently-dropped XML" below).
- **Before editing this file, check whether QLC+ is currently running** — it re-serializes and
  overwrites the whole file on its own save (drops comments, reorders widgets, changes `<Author>`),
  which will stomp on unsaved edits made directly to the file on disk:
  ```
  tasklist.exe 2>/dev/null | grep -i qlc   # process name: qlcplus.exe (classic UI, as of 2026-07-30)
  ```
  If it's running, ask the user to close it first — **always ask before terminating the process**,
  even to escalate from a soft close to `taskkill.exe /F`, rather than assuming standing permission
  from an earlier kill in the same session.

### CLI file-open syntax differs between the two UIs — `.qxw` double-click gotcha (classic UI)

**Found and fixed 2026-07-30.** Double-clicking a `.qxw` file in Explorer opened QLC+ but always
started an empty "New Workspace" — no error, no crash, nothing in the debug log (because plain
double-click doesn't pass `-d -g`, so nothing gets logged at all). Diagnosed by running
`"D:\Josef\QLC+4\qlcplus.exe" --help` directly (GUI-subsystem binary, but `--help`/`-h` prints to
stdout and exits — redirect it to a file from a `.bat`, since WSL→`cmd.exe` quoting for inline
`--help` is unreliable and Explorer double-click doesn't attach a console to read it directly).
Output confirmed: **this classic-UI binary's `QCommandLineParser` has no bare positional
file-open argument at all** — the *only* way to open a file via CLI is `-o`/`--open <file>`:
```
Usage:  qlcplus [options]
  -o or --open <file>          Open the specified workspace file
```
The `.qxw` file association's registered Open command was just `"D:\Josef\QLC+4\qlcplus.exe" "%1"`
(no `-o`) — the classic UI silently ignores the unrecognized positional argument and starts blank.
This is a genuine classic-vs-QML-UI CLI difference (the QML UI *does* appear to accept a bare file
path — the association wasn't touched for it and it worked as originally set up). Also note while
debugging this: `-d`/`--debug` on the classic UI takes a required numeric level (`0-3`), unlike the
QML UI's boolean `-d` flag — so the "Diagnosing silently-dropped XML" recipe just below needs
adjusting for this UI (see its note).

**Fix applied:** rewrote the file association's open command via registry (`HKCU` is enough, no
admin needed — it's read ahead of `HKLM\Software\Classes` in the merged `HKCR` view):
```
reg.exe add "HKCU\Software\Classes\qxw_auto_file\shell\open\command" /ve /t REG_SZ ^
  /d "\"D:\Josef\QLC+4\qlcplus.exe\" -o \"%1\"" /f
```
If QLC+4 ever gets reinstalled/updated (which can rewrite this registry value back to no-`-o`,
since that's what the installer itself wrote originally), re-check this key and re-apply the `-o`
if double-click silently opens a blank workspace again.

### Diagnosing silently-dropped XML (debug log)

The QML UI supports `-d`/`--debug` (install a message handler) and `-g`/`--log` (write it to a
file) together:
```
"D:\Josef\QLC+5\qlcplus-qml.exe" -d -g
```
This writes every `qWarning`/`qDebug` line — including `"Unknown ... tag"` parser warnings and
Function start/preRun/stop traces — to `C:\Users\<user>\QLC+.log`, readable directly from WSL at
`/mnt/c/Users/<user>/QLC+.log`. There is no in-app Error Log / Help menu in the QML UI to check
instead. Launching the exe from `cmd.exe` without these flags does **not** help — it's a GUI-
subsystem binary and the shell prompt returns immediately without showing any output.

**Classic UI (QLC+4, current install) equivalent — different flag syntax, confirmed 2026-07-30:**
`-d` needs a numeric level and `-g` takes no argument (per its own `--help`, see above); to open a
specific file *and* log, `-o`/`--open` is required too (bare positional file args are ignored — see
the gotcha above):
```
"D:\Josef\QLC+4\qlcplus.exe" -o "<file>" -d 3 -g
```
Same log destination (`C:\Users\<user>\QLC+.log`), same "no console output otherwise" caveat.

## File structure (big picture)

The workspace has two top-level sections under `<Workspace>`:

1. **`<Engine>`** — the data/logic layer:
   - `<InputOutputMap>`: DMX universe config (`Universe 1`, ID `0`).
   - `<Fixture>` blocks: 4x "Generic RGBW" fixtures (IDs 0–3), 4 channels each
     (channel order: `0=R, 1=G, 2=B, 3=W`), addressed contiguously at DMX offsets 0/4/8/12.
   - `<Function>` blocks: the actual programmed behaviors, referenced by numeric `ID`.
     - `Type="Scene"` (IDs 2–9, 11, 12): static color looks (Rot, Gruen, Blau, Weiss, Warm,
       Violett, Cyan, Aus, Gelb, Rosa). Each sets all 4 channels on all 4 fixtures via
       `<FixtureVal ID="fixtureID">` strings in `channel,value,channel,value,...` pairs. Scene
       "Aus" (ID 9) is no longer referenced by any VC widget (see AUS button below) but is left
       defined, unused, in case it's wanted again later.
     - `Type="Chaser"` (ID 10, "Farbwechsel"): manual button-triggered cycle through 5 color
       Scenes, fixed `Time`-based timing (2s hold + 0.5s fade per step; see gotchas below — this
       function's `<Step>` elements have broken twice already).
     - `Type="Chaser"` (IDs 13–17, `S2L …`): the "Sound to Light Programme" chasers — 2–7 color
       alternations (Blau-Rosa, Rot-Weiss, Gruen-Gelb, Blau-Gelb, Bunt), selected via the second
       SoloFrame in the VC (see below). Fixed `Time`-mode timing, `Hold="500"` per step (not
       beat-synced — see "Sound-to-Light wiring" below for why).
   - `<Monitor>`: 3D fixture layout positions, cosmetic only.

2. **`<VirtualConsole>`** — the UI layer: a top-level `<Frame>` ("Seite 1") containing:
   - a `<SoloFrame>` ("Farben", ID 80) wrapping the 8 color buttons (ROT/GRUEN/BLAU/WEISS/WARM/
     VIOLETT/CYAN/AUS) — a `SoloFrame` makes its direct children mutually exclusive: pressing one
     `Toggle` button running a Function auto-stops whichever sibling was previously running. This
     is why the color buttons no longer additively mix (e.g. Rot+Gruen no longer stays "Gelb").
   - a second `<SoloFrame>` ("Sound to Light Programme", ID 90) with 5 buttons (BLAU-ROSA,
     ROT-WEISS, GRUEN-GELB, BLAU-GELB, BUNT, IDs 91–95) selecting which `S2L …` Chaser
     (Function 13–17) is currently active — same mutual-exclusion pattern as the color SoloFrame.
   - the `FARBWECHSEL` `<Button>` (Chaser trigger), `Sound to Light` `<AudioTriggers>`, and
     `Master Dimmer` `<Slider>`, all as top-level siblings of the two SoloFrames (intentionally
     *not* inside either — Farbwechsel and the static colors aren't mutually exclusive with each
     other or with whichever S2L program is selected).

   Each function-triggering widget references a Function by numeric `<Function ID="n"/>` +
   `<Action>`. **Function IDs and VC widget `<Function ID>` references must stay in sync** — the
   Engine and VC sections are independent XML trees linked only by these numeric IDs, so
   renumbering a Function without updating every referencing widget silently breaks that button.

Widget-to-Function map:
| VC Button | Action | Function ID | Function |
|---|---|---|---|
| ROT | Toggle | 2 | Scene "Rot" |
| GRUEN | Toggle | 3 | Scene "Gruen" |
| BLAU | Toggle | 4 | Scene "Blau" |
| WEISS | Toggle | 5 | Scene "Weiss" |
| WARM | Toggle | 6 | Scene "Warm" |
| VIOLETT | Toggle | 7 | Scene "Violett" |
| CYAN | Toggle | 8 | Scene "Cyan" |
| AUS | **StopAll** | *(none)* | stops every running Function directly |
| FARBWECHSEL | Toggle | 10 | Chaser cycling Functions 2–8 |

AUS deliberately does **not** reference the "Aus" Scene (ID 9) any more. QLC+ mixes simultaneously-
running Scenes on shared channels via **HTP** (highest value wins per channel) — an "off" Scene
writing all-zero can never outrun an already-running color Scene's nonzero values, so it could
never actually turn anything off while another color was still toggled on. `Action=StopAll`
sidesteps HTP entirely by stopping every running Function outright.

### Sound-to-Light wiring

**Beat-sync was attempted and reverted — doesn't work on the installed QLC+ 5.2.2 build.** The
original plan: give Chasers 13–17 `<TempoType>Beats</TempoType>` so their step timing follows
QLC+'s global beat clock (fed from live audio-input beat detection,
`<InputOutputMap><BeatGenerator BeatType="Audio" BPM="120"/>`), with `Hold="1"` meaning "1 beat."
Confirmed via the `-d -g` debug log that this installed build's `Chaser::loadXML` does **not**
recognize the `<TempoType>` tag at all (`Unknown chaser tag: "TempoType"`, once per affected
Chaser) — it's silently dropped, the Chaser stays on its default `Time` tempo type, and `Hold="1"`
then means "1 millisecond," producing near-continuous flicker. This is why Chasers 13–17 are back
to `Time` mode with a fixed `Hold="500"` (500 ms/color) — a reasonable middle-of-the-road pace, but
**not** actually reactive to the detected tempo. `BeatType="Audio"` is still set in
`<InputOutputMap>` from the earlier attempt but currently has no effect on anything in this file.

**Re-confirmed 2026-07-23** with a clean, isolated re-test (user reasonably doubted the first
finding, since the installed build is 5.2.2 *stable*, not a nightly): only Chaser 13 given
`<TempoType>Beats</TempoType>` + `Hold="1"`, `BeatGenerator` switched to `Internal BPM="100"`.
Same flicker, and a fresh `-d -g` capture showed `Unknown chaser tag: "TempoType"` exactly once,
timestamped at that exact load — confirms the tag is genuinely never parsed here, independent of
BeatGenerator source or BPM value (tempo type is dropped before BPM is ever consulted). Reverted
immediately after.

The `<TempoType>` tag route is a dead end on **this Windows install specifically** — not
necessarily on the Raspberry Pi deployment target, which isn't set up yet and may run a different
QLC+ version. Don't assume it's broken there too; test fresh once the Pi exists (see "Deployment
target" note above). That said, don't wait on the Pi to make progress — see the OSC path below,
which sidesteps the internal beat engine entirely and doesn't depend on that outcome.

**Recommended real path forward: external beat detector + OSC input, not QLC+'s internal
BeatGenerator/TempoType.** Researched 2026-07-23: QLC+'s own internal beat-detection/tempo-following
is fragile across versions generally, not just broken here — e.g. GitHub issue
[mcallegari/qlcplus#1929](https://github.com/mcallegari/qlcplus/issues/1929) shows the `BeatGenerator`
BPM display itself broke in 5.1.0 nightlies (different bug, different code path, but same general
area). The pattern QLC+ users actually rely on for unattended automatic beat-sync is a **separate
external program** that listens to the mic and sends **OSC** messages to QLC+, received as an
"External Input" mapped to VC widgets/functions (OSC input is a mature, well-documented QLC+
feature — Input/Output Manager → OSC profile → VC widget → External Input — unrelated to the buggy
TempoType/BeatGenerator code path). Example:
[scheb/sound-to-light-osc](https://github.com/scheb/sound-to-light-osc) (Python + PyAudio, spectral-
flux beat detection, fully automatic, no tap-tempo, runs fine headless on Raspberry Pi OS — same USB
mic, no extra hardware). This is now the concrete next step to prototype, independent of whatever
the Pi's QLC+ build turns out to support.

### Cue List / OSC prototype (`v3`, started 2026-07-23)

Concrete implementation of the OSC path above, verified against `qmlui/virtualconsole/vccuelist.cpp`,
`vccuelist.h`, `vcwidget.cpp`/`.h`, and `engine/src/universe.h` at the exact `QLC+_5.2.2` tag before
writing any XML (learned from the `TempoType` incident: verify tag/attribute names against source
*and* still treat runtime as the final authority — see "Version mismatch warning" above).

**Architecture:** a `<CueList>` VC widget wraps one Chaser and exposes 5 externally-triggerable
controls (`registerExternalControl` in `vccuelist.cpp`): `0`=Next Cue, `1`=Previous Cue,
`2`=Play/Stop/Pause, `3`=Stop/Pause, `4`=Side Fader. Binding external input `0` ("Next Cue") to an
OSC message means: every time that OSC message arrives, the wrapped Chaser advances one step
*immediately*, regardless of its own internal `Hold` timer. This is how real users do beat-locked
step advances in QLC+ (confirmed via forum threads on OSC-triggered cue lists) — no `TempoType`, no
`BeatGenerator` involved at all, sidesteps that whole broken subsystem.

**Confirmed-safe minimal XML** (base `VCWidget` fields — `ID`/`Caption`/`WindowState` — are the same
`saveXMLCommon()` pattern already used by every other widget in this file; `PlaybackLayout`,
`NextPrevBehavior`, `Crossfade`, `SlidersMode` are all written by `saveXML()` only when they differ
from their constructor defaults, so omitting them is equivalent to explicitly setting the defaults,
not an unknown-tag risk):
```xml
<CueList Caption="..." ID="100">
 <WindowState Visible="True" X="19" Y="580" Width="300" Height="150"/>
 <Chaser>13</Chaser>
</CueList>
```
`<Chaser>13</Chaser>` is the *only* required field beyond the common widget attributes — it's
`chaserID()`, unconditionally written by `VCCueList::saveXML()`.

**Prototype in `v3` (2026-07-23):** added exactly one `CueList` (ID `100`, "S2L Takt (Test:
Blau-Rosa)") wrapping Chaser 13 ("S2L Blau-Rosa") only — deliberately not rolled out to Chasers
14–17 yet, same "prove it on one before scaling to all 5" approach used throughout this project.
Chaser 13's `Hold` was bumped from `500` to `30000` (30s) as a **safety net**: the Chaser still has
its own internal auto-advance timer (Cue List doesn't disable it, it only adds manual override), so
a very long Hold means it will, in practice, never auto-advance on its own within a normal listening
session — only the external "Next Cue" trigger (i.e. the detected beat) will actually cause a step
change. The existing "BLAU-ROSA" SoloFrame button (`Function ID="13"`, `Action=Toggle`) is left
completely as-is for starting/stopping the Chaser; `VCCueList`'s own Next-Cue handler checks
`ch->isRunning()` and acts on the already-running Chaser regardless of what started it, so the two
controls (SoloFrame toggle to start/stop, CueList Next-Cue to advance) don't conflict — **not yet
empirically verified, next thing to test**.

**Deliberately not yet added:** the `<Input ID="0" Universe="…" Channel="…"/>` element that would
bind "Next Cue" to a real OSC channel (`vcwidget.h`: `KXMLQLCVCWidgetInput`/`...InputUniverse`/
`...InputChannel` — confirmed generic schema, same one used for all External Input bindings
platform-wide). Universe/Channel numbers depend on an OSC Input Profile that doesn't exist yet in
this file and shouldn't be hand-guessed — the correct, low-risk way is: open QLC+, Input/Output
Manager → add an OSC input line/profile, run the Python beat-detector so it's sending real OSC
messages, then in the CueList widget's properties use "Auto Detect" against the live signal
(exactly like every other External Input binding in this file was — or would be — done). Do this
live in the GUI rather than writing the binding by hand in XML.

A `VCSpeedDial` widget (tap → `function->setDuration(ms)` directly via `applyFunctionsTime()` in
`qmlui/virtualconsole/vcspeeddial.cpp`, no `TempoType` needed) was considered as a fallback, but
**rejected** — it requires a person to tap the tempo live, which doesn't work for the actual
deployment: the Pi runs standalone/unattended, nobody is there to tap. Don't re-suggest this path
as a real solution; it only works for the Windows testing setup, not the real target.

Separately, `BeatGeneratorType` (`Disabled`/`Internal`/`Plugin`/`Audio`) is only settable from the
Input/Output Manager settings screen, never from a Virtual Console button — confirmed against
`engine/src/inputoutputmap.cpp`, no VC button `Action` exists for it. Not relevant to the current
`Time`-mode Chasers, but keep in mind if `TempoType` support ever does get used (e.g. after a QLC+
upgrade).

The `Sound to Light` `<AudioTriggers>` widget's `<VolumeBar>` independently gates Function 10
(Farbwechsel) on/off by overall loudness (`MinThreshold`/`MaxThreshold`) — unrelated to Chasers
13–17, which the user starts/stops manually via the second SoloFrame.

### Auto-layer: intensity-driven layer selection (`v6`, started 2026-07-30)

New ask: pick a color combo once (e.g. "Auto Blau-Rosa") and have the script auto-switch that
color between the 4 existing layers (Fade → Direkt → Alternierend → Alternierend mit Aus) as
music intensity rises, instead of the human picking a layer manually. Same OSC-input approach as
the beat Cue Lists above, not QLC+'s internal engine — no new load-bearing capability needed
there.

**Key open question, resolved by source-reading before writing any XML (same discipline as the
Cue List prototype above): can QLC+ tell the script which VC button is currently active, so the
script knows which color's "Auto" flag is on and which layer is currently running?** Confirmed
yes — checked `ui/src/virtualconsole/vcbutton.cpp` and `vcwidget.cpp` and
`plugins/osc/osccontroller.cpp` at the `QLC+_4.14.4` tag: `VCButton::setState()` (called on
*every* state change — manual mouse click, external OSC trigger, or a `SoloFrame` sibling
auto-stopping it) calls `updateFeedback()` → `VCWidget::sendFeedback()` →
`InputOutputMap::sendFeedBack()` → `OSCController::sendFeedback()`, which echoes the value back
out on the *same* OSC address the button's own External Input was bound to, to
`OSCController`'s default feedback target (`127.0.0.1:9000` for Universe 0, i.e. `9000 +
universe` — confirmed in `osccontroller.cpp`, unset unless the Input/Output Manager's OSC
feedback fields were changed). This is a *requirement*, not optional: a button only sends
feedback if it has a valid External Input source configured at all (`inputSource()` check in
`updateFeedback()`) — a button with no `<Input>` binding stays silent. Unlike the `TempoType`
tag, this isn't a per-format tag that can be silently dropped by a mismatched build — it's core
widget/Function-signal wiring, present since old QLC+ — still, treat as unverified-at-runtime
until tested live with `-d -g`, per the "Version mismatch warning" above; don't assume the
source-reading alone is proof.

**Design (implemented in `v6`'s XML, 2026-07-30):**
- 5 new no-op Scenes, `Function` IDs 66–70 ("S2L Auto-Flag <Farbe>", one per color combo) — each
  just `<Speed FadeIn="0" FadeOut="0" Duration="0"/>`, zero `FixtureVal` children. Confirmed
  against `engine/src/scene.cpp`'s `Scene::loadXML` that zero `FixtureVal` is legal (no minimum-
  count check) — these Scenes exist purely as an on/off flag Function for a button to toggle,
  with deliberately zero DMX effect (can't ever fight anything else via HTP).
- New `SoloFrame` "Auto" (widget ID 147, `Frame` label 153, `Button`s 148–152, one per color) —
  added as a **sibling** of the existing "Sound to Light" `SoloFrame` 90, *not* nested inside it.
  This is deliberate: all 20 existing layer buttons are flat children of `SoloFrame` 90's single
  mutual-exclusion pool, and the script will be toggling those same layer buttons externally
  (via OSC) whenever the active intensity band changes. If the Auto-flag buttons were in that
  same pool, every layer switch the script sends would auto-stop the Auto-flag Scene too
  (`SoloFrame` stops *all* other running siblings when one starts) — killing the "auto is
  engaged" flag the instant it becomes useful. Keeping "Auto" as its own `SoloFrame` means: the
  5 Auto buttons are mutually exclusive with *each other* (picking Auto for a new color turns off
  Auto for the previous one — sensible), but independent of the real layer buttons underneath.
  Trade-off accepted: a human manually clicking a real layer button while Auto is engaged for
  that color does **not** auto-disable Auto (they're different `SoloFrame`s) — the script will
  keep fighting the manual click until Auto is toggled off by hand. Not solved yet; acceptable
  for now, same "prove the core mechanism first" spirit as the original Cue List prototype only
  covering Chaser 13.
- Canvas grown (`Properties/Size` height 1080→1180) and `SoloFrame` 90 left untouched — the new
  "Auto" `SoloFrame` sits directly below it (Y=985), not inside it.
- **No `<Input>` bindings written for any of this yet** — same reasoning as the original Cue List
  prototype's "deliberately not yet added" note: channel numbers are OSC-profile-assigned at
  Auto-Detect time in the GUI and shouldn't be hand-guessed. This applies to all 5 new Auto
  buttons *and* all 20 existing layer buttons (they need External Input added too now, both so
  the script can trigger a layer switch and so their state changes produce feedback).

**`beat-detector/beat_osc.py` extended** (same file, still one script, still no build/lint
tooling — see top-level README):
- `IntensityClassifier`: RMS per audio chunk, smoothed via a fast EMA (`--intensity-ema-alpha`,
  default 0.15) and compared in dB against a *much slower* baseline EMA (`--baseline-seconds`,
  default 120s) — **not** a single short rolling window's own mean/stddev the way the existing
  beat-flux threshold works. Tried the short-window approach first and it doesn't work for this:
  confirmed with a synthetic quiet→loud test (module logic extracted and driven directly, no
  hardware needed) that once a sustained loud section fills most of a short window, that
  window's own mean/std shift up to match it, so "loud" reads as average relative to itself and
  the classified band never leaves 0. A baseline slow enough that a normal-length loud section
  (order of the existing 30s Chaser `Hold`, or longer) can't drag it up avoids that trap — the
  same synthetic-test approach (fake advancing clock, no real mic needed) also confirmed the
  dwell-time hysteresis (`--band-hold-ms`, default 2000) suppresses flapping even under a
  worst-case every-chunk loud/quiet alternation.
- `FeedbackState` + an `OSCController`-facing OSC *server* thread (`--feedback-port`, default
  9000, matching the confirmed default above) tracks which Auto button and which of the 20 layer
  buttons are currently active, purely from QLC+'s own feedback — the script never assumes state
  the GUI doesn't agree with; a manual click updates it too.
- `--auto`: when enabled, on every intensity band change the script sends an OSC press to the
  *real* layer button (not the Auto-flag Scene) matching the new band, for whichever color's
  Auto-flag feedback currently reads on. `SoloFrame` 90's existing mutual exclusion handles
  stopping the previous layer.
- `--wire-wizard`: walks through all 25 new External Input bindings one at a time (prints the
  OSC address, waits for Enter, sends 5 pulses ~300ms apart) so the Auto-Detect step in QLC+ has
  something live to catch — replaces hand-guessing channel numbers, same principle as how the
  original `/beat` binding was set up.

**Not yet done / next steps:** run `--wire-wizard` against a running QLC+ (with `-d -g` logging)
to Auto-Detect all 25 bindings and get real confirmation the feedback path works as the source
reading predicts — this is the one part of the whole design that's still unverified at runtime.
Until that's done, `v6`'s Auto row is a structurally-valid but functionally-untested draft, same
status as the rest of `v6` per the note in "Repository purpose" above.

**Bug found and fixed 2026-07-30 (real-world test): a zero-`FixtureVal` Scene self-stops on its
very first tick.** User reported the 5 Auto buttons "flash then immediately snap back to
Inactive" — reproduced identically via manual mouse click *and* via a direct OSC press, ruling
out anything OSC/wiring-specific. `-d -g` logging turned out to be a dead end for this one (it
only captures load-time parser warnings, e.g. the `TempoType` find — confirmed by testing it
against the known-good ROT button too, which also produced zero runtime log lines, since
`Function::start()` has no `qDebug` call at all, only `Function::stop()` does). The real
diagnosis came from re-reading `engine/src/scene.cpp`, specifically `Scene::write()` (**not**
`writeDMX()`/`postRun()`/`loadXML()`, which is all I'd checked when first designing the no-op
Scenes — a gap in my own verification, not just QLC+'s):
```cpp
void Scene::write(MasterTimer *timer, QList<Universe*> ua)
{
    if (m_values.count() == 0 && m_palettes.count() == 0)
    {
        stop(FunctionParent::master());
        return;
    }
    ...
```
A Scene with *zero* `FixtureVal` entries calls `stop()` on itself the instant `MasterTimer` ticks
it — i.e. milliseconds after starting. This directly contradicts what `Scene::loadXML` alone
implies (no minimum-`FixtureVal` check at load time — confirmed genuinely legal to *load*) —
loading fine and running fine are different questions, and I only checked the former. Same
"XML valid, runtime wrong" shape as the `TempoType` and `<Steps>`-wrapper gotchas elsewhere in
this file, different mechanism.

**Fix:** each of the 5 "S2L Auto-Flag `<Farbe>`" Scenes (Function IDs 66–70) now carries exactly
one `<FixtureVal ID="0">0,0</FixtureVal>` (Fixture 0, channel 0 = Master dimmer, value 0). Value
0 is HTP-safe by the same logic already established for the "Aus" Scene (ID 9) elsewhere in this
file — HTP takes the max value per channel across all running Functions, so a Function holding a
channel at 0 can never outrank or visibly affect anything else legitimately driving that channel
positive. This keeps `m_values.count() >= 1` (satisfying the guard above) while remaining a true
no-op on the actual light output, preserving the original design intent.

**Confirmed live 2026-07-30, post-fix:** user re-tested in the running app — Auto button now
latches and stays Active on click, zero light effect (as designed), and no other button/layer
gets activated as a side effect (confirms the separate-`SoloFrame` isolation from `SoloFrame` 90
holds up in practice, not just on paper). Toggle mechanism is solid now.

**OSC feedback path abandoned 2026-07-30 — root cause never found, not worth the time spent.**
Spent a long live-debugging session trying to get QLC+'s OSC feedback (needed for
`beat_osc.py --auto` to read which Auto/layer button is active, so a manual click in QLC+ would
be picked up) actually arrive at `osc_sniff.py` (a minimal raw OSC listener written for this
purpose). Every prerequisite checked out and still zero packets ever arrived:
- External Input bound correctly (confirmed: OSC message *does* trigger the button, so the
  Input direction works).
- `InputOutputMap::sendFeedBack()` requires `Universe::feedbackPatch()` to be non-null — found
  the Input/Output Manager has a separate **"Feedback" checkbox column** (Mapping tab, per
  Plugin/Device row) that must be checked in addition to "Input", undocumented anywhere in this
  file until now. Checked it, saved, confirmed the `.qxw` now has `<Feedback Plugin="OSC"
  UID="127.0.0.1" Line="0"/>` under `<Universe>` — the setting genuinely persisted.
- Windows Firewall: the popup had already been accepted for `python.exe`.
- `netstat -an | findstr 9000` confirmed a real UDP listener bound on the sniffer's port — so
  not a receive-side/binding problem either.
- Still nothing. The `-d -g` debug log turned out to be a dead end for chasing this further: it
  only captures a fixed early slice of startup (verified by grepping for `setFeedbackPatch` and
  `sendFeedBack` across 4 separate app launches, spanning before/after every fix attempt above —
  identical ~4-line block every time, always for the unused Universes 1–3, never once for
  Universe 0, even after the file was resaved with the Feedback patch present) — the log simply
  stops getting new content partway through loading, regardless of what happens afterward in the
  running app. (Also worth noting for its own sake: `Function::start()` has no `qDebug` call at
  all, only `Function::stop()` does — so testing "does this log capture button clicks" with a
  single click on a known-good button, like the ROT scene, is not a valid test; needs an actual
  stop to say anything either way. Wasted a round-trip on this before catching it.)

First reaction to burning that much time on a state-sync convenience: redesigned `--auto` to pick
the active color via a **terminal keypress** instead, with the script tracking its own last-sent
layer per color and never asking QLC+ anything. **Wrong call, corrected same day** — user caught
it immediately: the deployment target is the unattended Pi, operated via a tablet pointed at
QLC+'s own Web Access, not a keyboard at the Pi itself (see "Deployment target" above — this is
exactly the "requires a person to do X live [at the machine]" trap that section already warns
about). A terminal keypress doesn't fit that at all.

**Actual fix: use QLC+ Web Access's own WebSocket protocol instead of OSC for this whole
feature.** Web Access (the tablet-facing HTTP/WebSocket UI, `webaccess/src/webaccess.cpp` +
`webaccess/res/websocket.js` in `mcallegari/qlcplus`, confirmed at the `QLC+_4.14.4` tag) is a
first-class, everyday-used QLC+ feature — every Web Access tablet depends on this exact
mechanism working, unlike the comparatively obscure OSC-feedback path that never panned out
above. It's the objectively "clean solution" the user asked for, not a workaround:
- Default endpoint `ws://<host>:9999/qlcplusWS` (port from `-w`/`--web` + `-wp`/`--web-port`,
  `9999` is `DEFAULT_PORT_NUMBER` in `webaccessbase.cpp` if unset).
- **Press a button:** send the plain text message `"<widgetID>|1"` then `"<widgetID>|0"` —
  routes straight to `VCButton::pressFunction()`/`releaseFunction()`, the *exact* code path a
  mouse click or tablet tap takes. No OSC External Input, no Auto-Detect wizard, no channel
  numbers, no Feedback checkbox — addressing is the widget's own numeric ID straight from the
  `.qxw`, nothing negotiated at runtime.
- **State broadcast:** every connected client (tablet included) receives
  `"<widgetID>|BUTTON|255"` (Active) / `"127"` (Monitoring) / `"0"` (Inactive) whenever
  `VCButton::stateChanged` fires, from *any* cause — mouse click, tablet tap, this script's own
  press, or a `SoloFrame` sibling stopping it. Confirmed via `WebAccess::slotButtonStateChanged`
  (the broadcast) and `slotHandleWebSocketRequest`'s generic widget-ID dispatch (the incoming
  press handler) in `webaccess.cpp`.

`beat_osc.py` now connects as a plain WebSocket client (`websocket-client` PyPI package, added to
`requirements.txt`) to that same endpoint — literally another "tablet" from QLC+'s point of view.
`WebAccessState` tracks Auto-button and layer-button state purely from these broadcasts (dict
keyed by the known widget IDs — see `AUTO_BUTTON_ID`/`LAYER_BUTTON_ID` in the script, taken
directly from `v6.qxw`'s Button IDs 148–152 and the 20 layer buttons under `SoloFrame` 90).
`QLCWebSocket` reconnects on drop (1s retry, mirroring `websocket.js`'s own reconnect loop) since
this needs to survive unattended for a whole event on the Pi.

Confirmed correct with a synthetic test simulating realistic broadcast sequences (including the
OFF-broadcast a stopped sibling sends, which a naive test can forget to simulate and get a false
read from): no send with no color's Auto button active, no duplicate send for an unchanged band,
switching the active color resets per-color layer tracking, and — the one trade-off from the
original design that this now actually *fixes* rather than just accepting — a human manually
tapping a different layer button on the tablet **is** noticed (the broadcast updates
`WebAccessState` same as anything else), and the script simply reasserts its own intended layer
on the next tick. Still ends up "fighting" a manual override every intensity-band change, but at
least it's a correctly-informed fight now, not a blind one.

No External Input / Auto-Detect wiring needed for any of this any more — `--wire-wizard` and the
whole 20-or-25-bindings GUI chore from the original design are gone entirely. The only remaining
OSC wiring in this file is the original, already-working `/beat` → Cue List "Next Cue" binding,
unrelated to this feature. `osc_sniff.py` (the raw OSC listener written while chasing the
feedback dead end) is no longer needed for this but left in place as a generic diagnostic tool.

### `beat_osc.py --list-devices` on the Pi: empty output while `beat-osc.service` is running

**Found and confirmed 2026-07-31.** Running `./venv/bin/python3 beat_osc.py --list-devices` on the
Pi while `beat-osc.service` was active printed the usual ALSA/JACK probe-noise (harmless — see
below) but **zero** `[N] <device name> ...` lines, even though `arecord -l` showed the USB mic
present as ALSA card 2. Stopping the service first (`sudo systemctl stop beat-osc.service`),
re-running the exact same command, immediately showed `[0] USB AUDIO DEVICE: Audio (hw:2,0) (in: 2,
default sr: 44100)`. Restarting the service afterward (`sudo systemctl start beat-osc.service`)
returned to normal.

Root cause is **not** a permissions issue (first guess, ruled out) — it's that PyAudio/PortAudio's
device enumeration (`list_devices()` in `beat_osc.py`, `pa.get_device_info_by_index()`) briefly
opens each ALSA device to query its capabilities (supported sample rates etc.) as part of building
that info struct. If the device is already held open exclusively by another process (here:
`beat-osc.service`'s own running `beat_osc.py`), that probe-open fails and PortAudio silently
omits the device from enumeration — no error, no placeholder entry, it just doesn't appear. This
looks identical to a permissions problem (empty list, no crash) but has a completely different
fix: stop whatever's already holding the mic, don't touch group membership.

**Practical rule: to run `--list-devices` (or anything else that opens the mic) on the Pi, stop
`beat-osc.service` first, run it, then restart the service** — same pattern as the "check
`tasklist.exe`, don't edit `.qxw` while QLC+ is running" caution elsewhere in this file, same
underlying shape (a process silently holding a resource open causes another tool to misbehave in a
way that looks like a different bug).

The ALSA (`Unknown PCM ...`, `snd_func_refer` "Unable to find definition") and JACK ("jack server is
not running") lines that print before the device list are unrelated startup-probe noise from
PortAudio checking for optional ALSA plugins/JACK that this Pi doesn't have configured — they
print every single run, service or standalone, list-devices or normal operation, and are not
diagnostic of anything being wrong. Don't chase them; only the presence/absence of the actual
`[N] ...` device line(s) after that noise block is meaningful.

Once listed, the device index matters: `lichtsteuerung.conf`'s `MIC_DEVICE` must match PyAudio's
own index from this list, **not** the ALSA card number from `arecord -l` (they're different
numbering schemes — confirmed here: ALSA card 2, PyAudio index 0, since it's the only capture-
capable device PyAudio sees). On this Pi, `MIC_DEVICE="0"` already matched correctly.

### `journalctl -u beat-osc.service -f` showing nothing but ALSA/JACK noise, even while it's working

**Found and fixed 2026-07-31**, same session as the `--list-devices` finding above. With
`MIC_DEVICE` confirmed correct, following the live log with `journalctl -u beat-osc.service -f`
still showed only the startup ALSA/JACK probe-noise block and nothing after — not even the
script's own `"Listening (device=..., sending OSC ...)"` line it unconditionally prints right at
startup (`beat_osc.py`, just before the capture loop), let alone `beat  flux=...` lines while
making noise at the mic. Looked identical to "detector isn't hearing anything."

Root cause: **stdout buffering, not detection failure.** Python fully block-buffers `stdout` when
it isn't attached to a TTY (true for a systemd service, which captures stdout via a pipe) — `print()`
calls queue up in that buffer and only reach `journalctl` once the buffer fills or the process
exits, regardless of how quickly the events they describe are actually happening. The ALSA/JACK
lines appear immediately because they're `stderr` (unbuffered), which made it look like the script
started and then went silent, when actually its own stdout output (startup line, every beat, every
intensity-band change) was queued up invisibly the whole time.

**Fix:** run the interpreter with `-u` (unbuffered stdout/stderr) in `run-beat-osc.sh`'s `exec`
line — `python3 -u beat_osc.py --auto ...` instead of `python3 beat_osc.py --auto ...`. After
pulling this change to the Pi, `sudo systemctl restart beat-osc.service` and re-running
`journalctl -u beat-osc.service -f` should show the `"Listening ..."` line immediately, then live
`beat` / `[intensity]` / `[state]` lines as sound hits the mic — **not yet re-verified live on the
Pi**, next thing to confirm once this fix is deployed there.

### Beat detection silently hanging mid-session on the Pi (found 2026-07-31, recurred 2026-08-02 -- see update below)

**Symptom:** `beat_osc.py` would work correctly for anywhere from ~1 to ~36 seconds after
starting — real `beat` lines with sensible `flux`/`threshold` values, reacting to actual claps —
then go completely silent: no more `beat` lines even while clapping directly at the mic, no
crash, no traceback, `beat-osc.service` still reported `active (running)`. `[state]`/`[auto]`
lines (driven by the separate daemon WebSocket thread, see "Auto-layer" above) kept arriving fine,
which is what made this initially look WebSocket-related rather than audio-related — the two
threads are independent, and only the audio-processing one had actually died.

**Diagnosis path (each step ruled something out):**
- `top -p <pid>` on a hung process: `0.0 %CPU`, state `S` (sleeping), `TIME+` not increasing —
  genuinely blocked, not slow/busy.
- `sudo cat /proc/<pid>/task/*/syscall`: one thread in `epoll_pwait` (the WebSocket thread's
  normal idle wait — fine), the other in `ppoll` waiting on exactly **one** fd — consistent with
  PortAudio's ALSA backend blocking inside its own internal `poll()` while waiting for the next
  capture buffer, i.e. the audio thread was the one stuck, not the network thread.
- `dmesg -T | grep -iE "usb|audio"` around the hang timestamps: nothing — no disconnect, no reset,
  no error. Physically unplugging/replugging the USB mic didn't fix it either. Ruled out a
  flaky/failing microphone.
- Stopped `pipewire`/`wireplumber` (present on this Pi image, `fuser /dev/snd/*` showed both
  holding `/dev/snd/controlC2` and `/dev/snd/seq`) in case its session/idle-suspend management was
  interfering with the directly-opened `hw:` device underneath. No change. Ruled out.
- Decisive test: stopped `beat-osc.service` (frees the exclusive-access device — this card has no
  `dmix`, confirmed by the recurring `unable to open slave` ALSA spam, so only one opener at a
  time) and ran plain `arecord -D hw:2,0 -f S16_LE -r 44100 -c 2 -d 15 /tmp/test.wav` directly —
  completed cleanly every time, correct file size (`2646044` bytes for 15s/44100Hz/stereo/16-bit).
  **Raw ALSA capture in the device's native format never hung, at any duration tested.** This
  isolated the bug to the PyAudio/Python layer specifically, not ALSA, the kernel driver, or the
  hardware.

**Root cause:** `beat_osc.py` was opening the stream as `CHANNELS=1` (mono), `FORMAT=paFloat32`,
but `arecord -l`/the successful raw test showed the device's actual native capture format is
**16-bit stereo** — confirmed by `--list-devices`' own probe (`(in: 2, ...)`) and by `arecord`
only working reliably with `-c 2`. Since this card has no software mixing/conversion plugin (no
`dmix`, `hw:` opened directly, not `plughw:`), PortAudio itself has to do the mono-downmix and
float conversion in software when the app requests a format that doesn't match the hardware's
native one — and that software conversion path is the one that would eventually leave its
internal `poll()` never signaling ready again, with no error surfaced anywhere. The exact trigger
condition (why it happened after anywhere from ~1 to ~36 seconds, not deterministically) was never
pinned down beyond "some conversion/buffering edge case" — not needed to, since the fix removes
the software conversion path entirely rather than working around a specific trigger.

**Fix:** open the stream in the hardware's actual native format (`CHANNELS=2`,
`FORMAT=pyaudio.paInt16`) and do the stereo→mono downmix and int16→float normalization in Python
with numpy instead (`beat_osc.py`, top of the capture loop): `stereo.mean(axis=1) / 32768.0`. All
downstream logic (spectral-flux beat detection, `IntensityClassifier`) only ever compares relative
values (self-adapting thresholds, dB relative to a rolling baseline — see `IntensityClassifier`'s
own docstring) so the exact normalization scale doesn't matter, only that it's consistent frame to
frame, which it is. **Not yet re-verified over a long unattended run** — confirmed the hang
symptom and its exact repro conditions before applying this fix, next step is a real extended
listening session (ideally the length of an actual event) to confirm it's actually gone and not
just less frequent.

**Update 2026-08-02 — recurred despite the S16/native-format fix; root cause still open.** Live
on the real Pi, with the fix already deployed and confirmed present (`grep` showed `CHANNELS=2`,
`FORMAT=pyaudio.paInt16`), the exact same symptom happened again: `beat`/`[intensity]` lines
stopped cold mid-session, no crash, `systemctl status` still `active (running)`. Re-ran the same
diagnosis as the original find: `top -p <pid> -H` showed all 3 threads (audio, WebSocket,
sender — the sender thread is new since the WebSocket-freeze fix below) `0.0% CPU`, sleeping.
`sudo cat /proc/<pid>/task/*/syscall` — note this Pi is aarch64, **different syscall numbers
than the x86_64 table implied by the original find** — showed: `73` (`ppoll`, aarch64) on the
audio thread, `22` (`epoll_pwait`, aarch64) on the WebSocket thread (idle, as before), `98`
(`futex`, aarch64) on the new sender thread (idle, blocked on an empty queue — expected, no Auto
button had been pressed this time, ruling out any connection to the WebSocket-send fix below).
Same exact shape as the original find: audio thread stuck in a blocking poll inside the ALSA
read, everything else fine.

Conclusion: the 2026-07-31 fix (native format, no PortAudio software conversion) did not
eliminate this hang, only possibly reduced its frequency — consistent with that section's own
"not yet re-verified" caveat turning out to matter. The actual root cause (something inside
PortAudio's ALSA host API itself, still poorly understood) remains unfixed and is being pursued
separately, without blocking the rest of the system on finding it (same "mitigate now, keep
digging separately" split as the OSC-feedback dead end above). Next diagnostic angles to try,
not yet attempted: `cat /proc/asound/card2/stream0` at the moment of a hang (distinguishes a
stalled hardware ring buffer, state `XRUN`, from a purely software-side stall, state still
`RUNNING`); an extended (hour-scale) raw `arecord` soak test as a control, since the original
`arecord` test only ran 15s and a rare/slow-onset ALSA-level issue wouldn't necessarily show up
in that short a window; `vcgencmd get_throttled` at hang time, to rule out under-voltage/thermal
throttling as a Pi-specific contributor that wouldn't exist on the Windows dev machine.

**Mitigation added 2026-08-02 (does not fix the root cause, only its unattended-deployment
impact):** `beat-osc.service` now runs as `Type=notify` with `WatchdogSec=15`
(`pi-setup/beat-osc.service`); `beat_osc.py` sends `sd_notify("READY=1")` once at startup and
`sd_notify("WATCHDOG=1")` every ~2s from inside the main capture loop, right after
`stream.read()` returns (stdlib `socket.AF_UNIX`/`SOCK_DGRAM` to `$NOTIFY_SOCKET`, no new pip
dependency). Since the hang is specifically the read call itself blocking forever, the heartbeat
naturally stops the instant that happens, and systemd's watchdog timeout kills and restarts the
unit (`Restart=on-failure` already covers watchdog-triggered restarts per `systemd.service(5)`)
— a several-second beat-detection gap on each occurrence instead of a silent multi-hour outage
with nobody there to notice. This is explicitly a safety net, not a fix — the underlying
PortAudio/ALSA stall is still unexplained and worth continuing to chase per the diagnostic angles
above, this just bounds the blast radius while that's ongoing.

**Deployment pitfall found 2026-08-02: the watchdog didn't fire on its first real test —
because the new unit file was never actually installed, not because the mechanism is broken.**
`/proc/asound/card2/stream0` at the time of the (still ongoing) hang showed `Capture: Status:
Running` at a normal `44100 Hz` — the ALSA ring buffer was genuinely still live, conclusively
ruling out hardware/driver/USB and confirming (again) that the stall is purely on the
PyAudio/PortAudio side above ALSA. `vcgencmd get_throttled` (`0x0`) and `measure_temp` (`56.0'C`)
ruled out under-voltage/thermal throttling as a Pi-specific contributor too. But the service sat
hung for over 4 minutes with the *same* PID and no restart at all -- `systemctl show
beat-osc.service` showed `WatchdogUSec=0`, i.e. the watchdog was never actually configured on the
live unit.

Root cause of *that*: `pi-setup/beat-osc.service` is a template in the repo -- the actually
*loaded* copy lives at `/etc/systemd/system/beat-osc.service`, installed once during initial
setup via `sed ... | sudo tee ...` (README step 6). `git pull` only updates the repo's copy; nothing
re-copies it to `/etc/systemd/system/` automatically. Same overlayroot trap as the earlier
`git pull`-doesn't-persist issue, just one directory over -- `/etc` is under the same
overlay-protected root as `/opt`, so the fix needs the same `overlayroot-chroot` + reboot
dance, now documented in the README's update section alongside the code-update instructions.
Extra gotcha specific to this file: `$(whoami)` *inside* an `overlayroot-chroot` session
resolves to `root` (that shell's actual login), not the real service user -- the username has to
be supplied literally, from outside the chroot, or the re-copied unit file silently gets `User=
root`/`Group=root` instead of the intended account.

Net effect: the watchdog mechanism itself (sd_notify heartbeat, `Type=notify`, `WatchdogSec=15`)
never got a real chance to prove itself on its first test, since the unit that was actually
running the whole time didn't have it configured. After redeploying the corrected unit file,
`systemctl show beat-osc.service` confirmed `WatchdogUSec=15s` is now genuinely active
(2026-08-02) -- config-level verification done.

**Confirmed working live, same session, 2026-08-02:** `journalctl` caught two real
watchdog-triggered restarts back to back: last beat at 18:53:07, `Watchdog timeout (limit 15s)!`
at 18:53:22, `SIGABRT`, clean restart with `Listening...` again by 18:53:26; then last beat at
18:54:22, timeout at 18:54:38, restarted by 18:54:41. Self-healing mechanism fully verified end
to end -- process hangs, systemd notices within 15s, kills and restarts it automatically, no
manual intervention.

Also notable from this same evidence: **the hang is currently recurring far more often** than
the original "anywhere from ~1 to ~36 seconds after starting, then silent for the rest of the
session" description suggested -- here it recurred roughly every 30-100 seconds, twice within
about two minutes. Whatever's wrong seems to have gotten more frequent (or the original
description undersold how bad it can get), which is bad for actual usability (the watchdog
bounds each individual outage to ~15-20s, but back-to-back like this it's a very choppy listening
experience) but good for root-causing it: a bug this reproducible is actually easy to bisect now.
Makes the previously-proposed `pyalsaaudio` swap test (bypass PortAudio's ALSA host API
entirely, talk to ALSA directly like the never-hanging `arecord` control does) much more
attractive to try soon -- a result either way (hangs just as often / doesn't hang at all) would
come back within minutes instead of requiring an hours-long soak test.

**Bisection tool added 2026-08-02:** `beat_osc.py --audio-backend alsaaudio` (default remains
`pyaudio`, unchanged behavior) swaps the capture path to `pyalsaaudio`'s `alsaaudio.PCM(...)`
instead of `pa.open(...)` -- same `S16_LE`/stereo/44100Hz/`CHUNK`-sized reads, but talking to
ALSA directly with no PortAudio layer in between, structurally much closer to the raw `arecord`
control that has never hung than to the PyAudio path that keeps hanging. `read_chunk()` is now
an abstraction selected once at startup based on `--audio-backend`, used by the main loop instead
of a hardcoded `stream.read()`; the alsaaudio branch drops (returns `None`, skips the chunk
rather than risking a shape mismatch against `band_mask`) any read that doesn't return exactly
`CHUNK` frames, since `PCM_NORMAL` mode is expected to always deliver a full period but a
defensive check costs nothing. Needs `--alsa-device` (an ALSA `hw:X,Y` string from `arecord -l`,
a *different* numbering scheme than `--device`/`--list-devices`'s PyAudio index -- see the
"MIC_DEVICE" note elsewhere in this doc for why those two numberings differ). `pyalsaaudio` is
deliberately not in `requirements.txt` as a hard dependency (only a comment pointing at it) since
the default backend doesn't need it and it requires `libasound2-dev` via apt to build.

**Not yet run** -- next step is deploying this to the Pi (where the hang is now reproducible
within ~30-100s per the frequency finding above) and running `--audio-backend alsaaudio` for a
few minutes: if it hangs just as often, the bug isn't specific to PortAudio after all (points
back at something ALSA/kernel/driver-level despite the earlier evidence, or something in this
script's own processing); if it runs clean, that's strong confirmation the bug is inside
PortAudio's ALSA host API specifically, and switching the default backend permanently becomes the
real fix (not just the watchdog mitigation).

**Second bug found and fixed 2026-08-02, same debugging session: the layer button often stayed
inactive right after Auto was enabled** (reproduced right after boot with `--startup-auto-color`,
and again right after a watchdog-triggered restart). Root cause: `run_auto_layer_step` runs every
audio-loop tick (~23ms) and re-fires a press whenever the *confirmed* layer (from
`WebAccessState`, which only updates once QLC+ Web Access's broadcast round-trip completes --
much slower than one tick) doesn't yet match the desired one. That meant several presses could go
out for the same transition before the first confirmation ever arrived. The layer buttons are all
`Action=Toggle` (confirmed in `v6.qxw`, e.g. widget 115) -- each extra press flips the button
again, so an even number of presses before confirmation catches up leaves it back off, an odd
number leaves it on, pure timing-dependent parity. Live log evidence of exactly this: three
consecutive `[auto] blau-rosa: None -> fade` attempts logged for one single intended transition,
with the confirmed state bouncing `ON -> off -> ON` in between.

**Fix:** `run_auto_layer_step` now takes a `last_command` dict (`{color: (desired_layer,
monotonic_time)}`, threaded through from `main()`, mutated in place across calls) and skips
re-sending a press for the same already-in-flight target until either it's confirmed or
`LAYER_PRESS_COOLDOWN_S` (1.0s -- comfortably longer than a normal Web Access round trip, short
enough to retry if a press was genuinely dropped) has passed. Still reacts immediately to an
actually new desired layer, or to a human's own tablet tap changing the confirmed state to
something else -- only the same-target repeat-fire is suppressed. Not yet re-verified live after
this fix (next boot / next watchdog restart should show a single `[auto]` line per transition,
no more flapping).

## Known gotchas: Chaser (`Type="Chaser"`) authoring

Two independent issues have hit the "Farbwechsel" Chaser; both are now fixed in this file, but
watch for regressions if this Function is touched again:

1. **`<Step>` elements must be direct children of `<Function>` — no `<Steps>` wrapper.** Unlike
   most nested QLC+ structures, `Chaser::loadXML` (`engine/src/chaser.cpp`) does not recognize a
   grouping `<Steps>` tag at all. Wrapping the `<Step>` list in one (as one might expect by
   analogy with other list-like XML in this format) causes QLC+ to log
   `Unknown chaser tag: "Steps"` and skip the *entire* wrapped subtree — the Chaser silently loads
   with zero steps, which is not a load error, just an empty Function. Symptom: the button
   flashes running-then-immediately-stopped (`Function start()` → `preRun` → `Function stop()`
   within the same tick, source `4294967295` = automatic, not user-triggered) because
   `ChaserRunner::write()` bails out on `stepsCount() == 0`. Confirmed via the `-d -g` debug log
   (see above) — this is exactly how it was found and is worth re-checking that log if this ever
   recurs.
2. **`<SpeedModes FadeIn="PerStep" FadeOut="PerStep" Duration="PerStep"/>` must be present** as a
   direct child of the `<Function Type="Chaser">` block. Without it, `Chaser`'s duration mode
   defaults to `Common` (`Chaser::Chaser()` constructor, `chaser.cpp`), which makes the engine use
   the Function's own top-level `<Speed Duration="…">` for every step's timing instead of each
   `<Step Hold="…" FadeIn="…">`'s own values. Here that top-level `Duration` is intentionally `0`
   (since steps carry their own timing), so without `SpeedModes` every step would advance near-
   instantly — the Chaser would *run* (unlike gotcha #1) but look like nothing is happening.

3. **`<TempoType>Beats</TempoType>` is not supported by the installed QLC+ 5.2.2 build — don't
   re-add it.** It's a real tag in newer `mcallegari/qlcplus` source (`Chaser::loadXML` dispatches
   on it, and when present it changes step timing from milliseconds to beat-counts, compared via
   `step->m_elapsedBeats` in `chaserrunner.cpp`). But it was tried here for Chasers 13–17 and the
   `-d -g` debug log showed `Unknown chaser tag: "TempoType"` — this build's `Chaser::loadXML`
   doesn't have that branch. The tag gets silently dropped, tempo type stays `Time` (the
   `Function` default), and any `Hold`/`Duration` value written assuming beat-count units gets
   read as milliseconds instead — with `Hold="1"` that means a ~1ms hold, i.e. runaway flicker.
   **Re-confirmed 2026-07-23** with an isolated single-Chaser re-test (Internal BeatGenerator,
   100 BPM) — identical result, same log warning, once, at that exact load. Not a fluke, not tied
   to BeatGenerator source. Stick to `Time`-mode Chasers (real ms values) throughout this file; see
   the "Sound-to-Light wiring" section above for the OSC-based external-detector approach instead.

Both gotchas are silent: no XML error, file "loads fine," only the runtime behavior is wrong.
