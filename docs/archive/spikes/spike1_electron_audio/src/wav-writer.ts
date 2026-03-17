/**
 * wav-writer.ts
 *
 * Converts an Int16Array of mono/stereo PCM samples to a standard RIFF/WAV
 * file and writes it to disk using Node's `fs` module (main process only).
 *
 * WAV format reference: http://soundfile.sapp.org/doc/WaveFormat/
 *
 * Supports: PCM signed 16-bit, any sample rate, 1 or 2 channels.
 * The spike targets 16 kHz mono (numChannels=1).
 */

import * as fs from "fs";

/** Write a WAV file without any third-party library dependency. */
export function writeWavFile(
  filePath: string,
  pcm: Int16Array,
  sampleRate: number,
  numChannels: number
): void {
  const bitsPerSample = 16;
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const dataByteLength = pcm.length * 2; // Int16 = 2 bytes per sample
  const totalFileBytes = 44 + dataByteLength; // 44-byte RIFF header

  const buffer = Buffer.allocUnsafe(totalFileBytes);
  let offset = 0;

  // ---- RIFF chunk descriptor ----
  buffer.write("RIFF", offset, "ascii");
  offset += 4;
  buffer.writeUInt32LE(36 + dataByteLength, offset); // ChunkSize
  offset += 4;
  buffer.write("WAVE", offset, "ascii");
  offset += 4;

  // ---- fmt sub-chunk ----
  buffer.write("fmt ", offset, "ascii");
  offset += 4;
  buffer.writeUInt32LE(16, offset); // SubChunk1Size = 16 for PCM
  offset += 4;
  buffer.writeUInt16LE(1, offset); // AudioFormat = 1 (PCM, no compression)
  offset += 2;
  buffer.writeUInt16LE(numChannels, offset);
  offset += 2;
  buffer.writeUInt32LE(sampleRate, offset);
  offset += 4;
  buffer.writeUInt32LE(byteRate, offset);
  offset += 4;
  buffer.writeUInt16LE(blockAlign, offset);
  offset += 2;
  buffer.writeUInt16LE(bitsPerSample, offset);
  offset += 2;

  // ---- data sub-chunk ----
  buffer.write("data", offset, "ascii");
  offset += 4;
  buffer.writeUInt32LE(dataByteLength, offset);
  offset += 4;

  // Write PCM samples as little-endian Int16.
  for (let i = 0; i < pcm.length; i++) {
    buffer.writeInt16LE(pcm[i], offset);
    offset += 2;
  }

  fs.writeFileSync(filePath, buffer);
}

/**
 * Renderer-safe helper: serialises Int16Array → plain number[] for IPC
 * transfer (structured clone does not preserve typed arrays across context
 * bridge in all Electron versions).
 */
export function int16ToArray(pcm: Int16Array): number[] {
  return Array.from(pcm);
}
