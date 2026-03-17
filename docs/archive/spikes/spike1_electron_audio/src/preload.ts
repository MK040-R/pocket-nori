import { contextBridge, ipcRenderer } from "electron";

/**
 * CaptureAPI — surface exposed to the renderer via window.captureAPI.
 * Kept minimal: only the calls the renderer UI actually needs.
 */
export interface CaptureAPI {
  getSources(): Promise<Array<{ id: string; name: string }>>;
  saveWav(
    pcmBuffer: number[],
    sampleRate: number,
    numChannels: number
  ): Promise<{ ok: boolean; path?: string; error?: string }>;
  openOutputDir(): Promise<string>;
}

contextBridge.exposeInMainWorld("captureAPI", {
  getSources: () => ipcRenderer.invoke("get-sources"),

  saveWav: (pcmBuffer: number[], sampleRate: number, numChannels: number) =>
    ipcRenderer.invoke("save-wav", pcmBuffer, sampleRate, numChannels),

  openOutputDir: () => ipcRenderer.invoke("open-output-dir"),
} satisfies CaptureAPI);
