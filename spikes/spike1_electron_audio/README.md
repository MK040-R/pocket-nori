# Spike 1 — Electron Audio Capture

Minimal Electron + TypeScript app that captures system/tab audio on macOS
and writes a 16 kHz mono 16-bit PCM `.wav` file to disk.

**Linear:** FAR-5 (parent), FAR-41 through FAR-46 (sub-tasks)

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 20 LTS+ |
| npm | 10+ |
| macOS | 13 Ventura+ (for loopback audio support) |

> **macOS permissions required**
>
> - Screen Recording — required for `desktopCapturer` (System Settings → Privacy & Security → Screen Recording → enable for your terminal / Electron app)
> - Microphone — may be required depending on which capture path Chromium takes

---

## Setup

```bash
cd spikes/spike1_electron_audio
npm install
```

Optional — set a custom output directory:

```bash
cp .env.example .env
# edit OUTPUT_DIR in .env
```

---

## Run

```bash
npm start
```

This compiles TypeScript (`tsc`) and launches Electron.

---

## Usage

1. The app window opens showing a list of capture sources (screens + windows).
2. Select the source you want to capture (e.g. "Entire Screen" or a Google Meet window).
3. Click **Start Capture**.
4. Grant Screen Recording permission if macOS prompts you (requires app restart).
5. When done, click **Stop & Save**.
6. The output path is shown in the UI. Click it to open the folder in Finder.

The output file is always named `output.wav` and is overwritten on each capture.

---

## Output format

| Property | Value |
|----------|-------|
| Format | RIFF/WAV |
| Sample rate | 16 000 Hz |
| Channels | 1 (mono) |
| Bit depth | 16-bit signed PCM |

This matches the Deepgram STT preferred input format.

---

## Project structure

```
spike1_electron_audio/
├── src/
│   ├── main.ts          # Electron main process
│   ├── preload.ts       # Context bridge (IPC surface to renderer)
│   ├── audio-capture.ts # Web Audio API capture logic (renderer-side reference)
│   ├── wav-writer.ts    # RIFF/WAV file writer (Node/main process)
│   └── index.html       # Minimal UI (self-contained, no bundler)
├── .env.example
├── package.json
├── tsconfig.json
├── README.md
└── FINDINGS.md
```

---

## Known limitations (spike scope)

- Uses the deprecated `ScriptProcessorNode`; replace with `AudioWorkletNode` before production.
- No error recovery if stream drops mid-capture.
- `output.wav` is overwritten on each run.
- `loopback: true` is a non-standard constraint; behaviour varies by macOS version and Electron release.
- FAR-45 (live Google Meet testing) requires a human operator — see FINDINGS.md.
