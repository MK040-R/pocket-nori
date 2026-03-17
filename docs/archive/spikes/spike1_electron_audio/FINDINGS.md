# FINDINGS.md — Spike 1: Electron Audio Capture

**FAR-46 deliverable** | Date: 2026-03-09 | Status: COMPLETE (pending FAR-45 human test)

---

## Research Summary (FAR-41)

### Can Electron capture system/tab audio on macOS?

**Yes — with important caveats.**

Electron wraps Chromium's `desktopCapturer` API, which on macOS uses the
ScreenCaptureKit framework (macOS 12.3+) and the legacy CGWindowList API as
a fallback. Audio capture behaviour:

| Scenario | Captured? | Notes |
|----------|-----------|-------|
| Screen source (entire display) audio | Yes, macOS 13+ | Requires Screen Recording permission; `loopback:true` constraint routes system audio mix |
| Individual window audio | Partial | ScreenCaptureKit can capture per-window audio on macOS 14+; older macOS may return silence |
| Browser tab (Google Meet) audio | Yes (via screen capture) | Selecting "Entire Screen" captures all audio including browser tabs |
| Microphone | Yes | Standard `getUserMedia`, separate permission flow |

### What macOS permissions are required?

1. **Screen Recording** — mandatory for any `desktopCapturer` call. Must be
   granted for the host process (terminal or Electron app) in:
   System Settings → Privacy & Security → Screen Recording.
   The app must be relaunched after granting.

2. **Microphone** — may be requested by Chromium depending on which internal
   capture path it selects. Grant in:
   System Settings → Privacy & Security → Microphone.

No entitlements or notarisation are needed for local development (unsigned app).
For distribution, `com.apple.security.device.audio-input` and
`com.apple.security.device.camera` entitlements are required.

### Does `desktopCapturer` support audio from a Google Meet tab?

**Yes, indirectly.** The approach that reliably works:

1. Select the "Entire Screen" (screen:0:0) source — this captures the full
   system audio mix, which includes whatever the browser tab is playing.
2. Alternatively, on macOS 14+ with Electron 28+, select the Chrome/Safari
   window directly — ScreenCaptureKit will capture that window's audio stream.

**What does NOT work:** Selecting a specific Chrome tab directly via
`desktopCapturer` — tab-level sources appear in the source list but their
audio track is typically silent because Chromium's tab audio routes through
the renderer process, not a capturable audio device.

The recommended capture strategy for Pocket Nori Phase 1:
- Capture "Entire Screen" audio (catches Meet + any other app audio).
- Apply speaker diarisation / VAD post-capture to isolate speech.

### `loopback: true` constraint

This is a non-standard Chromium extension to the `getUserMedia` audio
constraints. It instructs the audio capture backend to use a loopback device
(i.e., the output mix being sent to speakers). Behaviour:

- macOS 13 Ventura + Electron 24+: works when Screen Recording permission is
  granted and the source is a screen (not a window).
- macOS 12 and below: silently ignored; stream may return silence.
- The constraint is passed as an opaque object extension; TypeScript requires
  a cast to `any` since it is not in the `MediaTrackConstraints` type definition.

---

## Implementation Notes (FAR-43 / FAR-44)

### Audio pipeline

```
desktopCapturer.getSources()
       │
       ▼
navigator.mediaDevices.getUserMedia({ chromeMediaSource: 'desktop', ... })
       │
       ▼  MediaStream (audio + minimal video track)
AudioContext (16 kHz)
       │
       ▼  MediaStreamAudioSourceNode
ScriptProcessorNode (4096 frame buffer)
       │  onaudioprocess → Float32 frames
       ▼
float32ToInt16() → Int16Array chunks accumulated in-memory
       │
       ▼  on Stop (IPC: save-wav)
wav-writer.ts (main process) → RIFF/WAV file → disk
```

### Format achieved

| Property | Value |
|----------|-------|
| Sample rate | 16 000 Hz |
| Channels | 1 (mono — downmixed from source) |
| Bit depth | 16-bit signed PCM |
| Container | RIFF/WAV |

This is the optimal format for Deepgram Nova-2 (no server-side resampling needed).

### Limitations discovered

1. **ScriptProcessorNode is deprecated.** The Web Audio spec recommends
   `AudioWorkletNode`. For the spike this is acceptable; production code should
   migrate. The deprecation does not affect functionality in Electron 28.

2. **Video track overhead.** `getUserMedia` with `chromeMediaSource:'desktop'`
   requires a video constraint even when only audio is needed. We constrain
   it to 1×1 px at 1 fps to minimise overhead, but the track is still opened.
   ScreenCaptureKit on macOS opens a display stream regardless.

3. **Context bridge serialisation.** `Int16Array` is not reliably transferred
   across Electron's context bridge in all versions. The implementation
   converts to a plain `number[]` via `Array.from()` before IPC, then
   reconstructs in the main process. This is memory-inefficient for long
   recordings; production should use `SharedArrayBuffer` or write chunks
   incrementally via IPC streaming.

4. **No real-time level meter.** The spike UI shows a timer only. A VU meter
   would help confirm audio is actually being captured (especially on macOS
   where `loopback` may silently fail).

5. **Output file is overwritten.** Each capture run overwrites `output.wav`.
   Production should timestamp filenames or stream directly to the indexing
   pipeline.

---

## FAR-45 — Human Testing Required

> BLOCKED — requires human to run the Electron app against a live Google Meet session.

**Instructions for tester:**

1. `cd spikes/spike1_electron_audio && npm install && npm start`
2. Grant Screen Recording permission if prompted (then relaunch with `npm start`).
3. Open Google Meet in Chrome and join/start a meeting.
4. In the Pocket Nori app, click Refresh Sources, then select "Entire Screen" (or the Chrome window).
5. Click **Start Capture**.
6. Speak for 10–30 seconds; have another participant speak if possible.
7. Click **Stop & Save**.
8. Open `output.wav` in QuickTime or run `afplay output.wav`.
9. Report:
   - Is audio audible? (voices, not silence)
   - Is the recording clean (no dropout, distortion)?
   - File size reasonable? (~1 MB/min at 16 kHz mono 16-bit)
   - Any macOS permission dialogs that were unexpected?

---

## Go / No-Go Decision

### DECISION: **GO** (conditional)

Electron is viable for system audio capture on macOS with the following
conditions:

| Condition | Status |
|-----------|--------|
| macOS 13 Ventura or later on target machines | Required — document as system requirement |
| Screen Recording permission granted by user | Required — app must guide user through grant flow |
| Capture via "Entire Screen" source (not per-tab) | Confirmed working in research; FAR-45 validates in practice |
| `loopback:true` audio routing | Works macOS 13+; add version check and user-facing warning for older OS |
| FAR-45 live test passes | PENDING — blocking for final go decision |

### Alternative if FAR-45 fails

If Google Meet audio is not captured (e.g., Chromium sandboxes its renderer
audio from ScreenCaptureKit), the fallback is:

**Option A — BlackHole / virtual audio device:** Install BlackHole (open source)
as a virtual audio loopback device; route Meet output through it; capture
BlackHole as a microphone input. Works reliably on all macOS versions but
requires user installation of a third-party kernel extension.

**Option B — Native Swift/Objective-C helper process:** Write a small macOS
helper using `AVCaptureScreenInput` + `AVAssetWriter` or the ScreenCaptureKit
`SCStreamDelegate` API for high-quality per-app audio capture. Electron calls
it via `child_process`. More complex but removes Chromium limitations.

**Option C — Browser extension approach:** Capture tab audio from within the
browser using a Chrome extension with `chrome.tabCapture` API, then POST PCM
chunks to the local Pocket Nori backend over localhost. No Electron needed.

### Recommendation

Proceed with the Electron approach (this spike) pending FAR-45 confirmation.
If the live test shows silence on Google Meet audio, implement Option C
(Chrome extension) as it targets exactly the use case and avoids all OS-level
permission complexity.
