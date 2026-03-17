/**
 * audio-capture.ts
 *
 * Renderer-side audio capture using Electron's desktopCapturer + Web Audio API.
 *
 * Flow:
 *  1. Caller asks main process for available sources (IPC: get-sources).
 *  2. Caller picks a source (screen or window) and calls startCapture(sourceId).
 *  3. getUserMedia opens the stream with chromeMediaSource:'desktop'.
 *     - On macOS 13+ with Electron 28+ the audio constraint `loopback:true` is
 *       passed; this captures the system mix for the selected display.
 *     - For a specific Google Meet window the caller should select the Meet
 *       window source by name; Chromium will capture that window's audio.
 *  4. A ScriptProcessorNode drains PCM Float32 frames; they are downmixed to
 *     mono and quantised to Int16 (16-bit signed), then appended to `pcmChunks`.
 *  5. stopCapture() concatenates all chunks and returns Int16Array + metadata.
 *
 * Target format: 16 kHz, mono, 16-bit PCM — optimal for Deepgram STT.
 *
 * NOTE: ScriptProcessorNode is deprecated in favour of AudioWorkletNode but
 * remains the simplest cross-Chromium-version option for a spike. Replace with
 * AudioWorklet before production.
 */

/** Metadata returned alongside the PCM buffer */
export interface CaptureResult {
  pcm: Int16Array;
  sampleRate: number;
  numChannels: number;
  durationSeconds: number;
}

// ---------------------------------------------------------------------------
// Internal state (one capture session at a time)
// ---------------------------------------------------------------------------
let audioCtx: AudioContext | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null;
let processorNode: ScriptProcessorNode | null = null;
let activeStream: MediaStream | null = null;
let pcmChunks: Int16Array[] = [];
let captureStartTime = 0;

const TARGET_SAMPLE_RATE = 16_000; // Hz — matches Deepgram STT default
const SCRIPT_PROCESSOR_BUFFER = 4096; // frames per callback

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Start capturing audio from the desktop source identified by `sourceId`.
 *
 * @param sourceId  The `id` field from a desktopCapturer source object,
 *                  e.g. "screen:0:0" or "window:12345:0".
 * @returns         Promise that resolves once the stream is live.
 */
export async function startCapture(sourceId: string): Promise<void> {
  if (activeStream) {
    throw new Error("Capture already in progress. Call stopCapture() first.");
  }

  // -------------------------------------------------------------------
  // 1. Open the media stream via getUserMedia with desktop capture constraints.
  //    chromeMediaSource:'desktop' is an Electron/Chromium extension.
  // -------------------------------------------------------------------
  const constraints: MediaStreamConstraints = {
    audio: {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(({
        chromeMediaSource: "desktop",
        chromeMediaSourceId: sourceId,
        // loopback:true requests the system audio mix on macOS (supported in
        // Chromium 110+ / Electron 24+). Silently ignored if unsupported.
        loopback: true,
      }) as any),
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      sampleRate: TARGET_SAMPLE_RATE,
    },
    video: {
      // Video is required by the API even though we discard it.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(({
        chromeMediaSource: "desktop",
        chromeMediaSourceId: sourceId,
      }) as any),
      width: { max: 1 },
      height: { max: 1 },
      frameRate: { max: 1 },
    },
  };

  activeStream = await navigator.mediaDevices.getUserMedia(constraints);

  // -------------------------------------------------------------------
  // 2. Build Web Audio graph: MediaStream → Source → ScriptProcessor → Dest
  // -------------------------------------------------------------------
  audioCtx = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  sourceNode = audioCtx.createMediaStreamSource(activeStream);

  // ScriptProcessorNode: 1 input channel (mono), 0 output channels (we only
  // want to read, not play back to speakers).
  processorNode = audioCtx.createScriptProcessor(
    SCRIPT_PROCESSOR_BUFFER,
    1, // input channels (downmix to mono)
    1  // output channels (silent)
  );

  processorNode.onaudioprocess = (event: AudioProcessingEvent) => {
    const inputBuffer = event.inputBuffer;
    // Downmix all input channels to mono by averaging.
    const numInputChannels = inputBuffer.numberOfChannels;
    const frameCount = inputBuffer.length;
    const mono = new Float32Array(frameCount);

    for (let ch = 0; ch < numInputChannels; ch++) {
      const channelData = inputBuffer.getChannelData(ch);
      for (let i = 0; i < frameCount; i++) {
        mono[i] += channelData[i] / numInputChannels;
      }
    }

    // Quantise Float32 [-1, 1] → Int16 [-32768, 32767]
    const int16 = float32ToInt16(mono);
    pcmChunks.push(int16);
  };

  // Connect graph. Route processor output to destination so Chromium keeps
  // the graph alive (it suspends disconnected graphs).
  sourceNode.connect(processorNode);
  processorNode.connect(audioCtx.destination);

  pcmChunks = [];
  captureStartTime = Date.now();
}

/**
 * Stop the active capture session.
 *
 * @returns CaptureResult containing the full PCM buffer and format metadata.
 */
export function stopCapture(): CaptureResult {
  if (!activeStream || !audioCtx || !processorNode || !sourceNode) {
    throw new Error("No capture in progress.");
  }

  const durationSeconds = (Date.now() - captureStartTime) / 1000;

  // Tear down the graph.
  sourceNode.disconnect();
  processorNode.disconnect();
  processorNode.onaudioprocess = null;
  activeStream.getTracks().forEach((t) => t.stop());
  void audioCtx.close();

  sourceNode = null;
  processorNode = null;
  activeStream = null;
  audioCtx = null;

  // Concatenate all Int16 chunks.
  const totalLength = pcmChunks.reduce((sum, c) => sum + c.length, 0);
  const pcm = new Int16Array(totalLength);
  let offset = 0;
  for (const chunk of pcmChunks) {
    pcm.set(chunk, offset);
    offset += chunk.length;
  }
  pcmChunks = [];

  return {
    pcm,
    sampleRate: TARGET_SAMPLE_RATE,
    numChannels: 1,
    durationSeconds,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    // Clamp to [-1, 1] then scale.
    const clamped = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return int16;
}
