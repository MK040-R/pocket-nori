import { app, BrowserWindow, ipcMain, desktopCapturer, session } from "electron";
import * as path from "path";
import * as fs from "fs";
import { writeWavFile } from "./wav-writer";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const OUTPUT_DIR = process.env.OUTPUT_DIR ?? path.join(app.getPath("userData"), "pocket-nori-audio");
const OUTPUT_FILE = path.join(OUTPUT_DIR, "output.wav");

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------
let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 320,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: "Pocket Nori — Audio Capture Spike",
    resizable: false,
  });

  mainWindow.loadFile(path.join(__dirname, "..", "src", "index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// Permissions — allow media access for desktopCapturer streams
// ---------------------------------------------------------------------------
app.whenReady().then(() => {
  // Grant microphone/display-media permission for the renderer so
  // getUserMedia with chromeMediaSource:'desktop' works without a dialog.
  session.defaultSession.setPermissionRequestHandler(
    (_webContents, permission, callback) => {
      const allowed = ["media", "display-capture", "mediaKeySystem"];
      callback(allowed.includes(permission));
    }
  );

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// ---------------------------------------------------------------------------
// IPC: enumerate capture sources
// ---------------------------------------------------------------------------
ipcMain.handle("get-sources", async () => {
  const sources = await desktopCapturer.getSources({
    types: ["screen", "window"],
    thumbnailSize: { width: 0, height: 0 },
    fetchWindowIcons: false,
  });
  return sources.map((s) => ({ id: s.id, name: s.name }));
});

// ---------------------------------------------------------------------------
// IPC: save captured PCM buffer → .wav
// ---------------------------------------------------------------------------
ipcMain.handle(
  "save-wav",
  async (_event, pcmBuffer: number[], sampleRate: number, numChannels: number) => {
    try {
      if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
      }
      const int16 = Int16Array.from(pcmBuffer);
      writeWavFile(OUTPUT_FILE, int16, sampleRate, numChannels);
      return { ok: true, path: OUTPUT_FILE };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("[main] save-wav error:", message);
      return { ok: false, error: message };
    }
  }
);

// ---------------------------------------------------------------------------
// IPC: open output directory in Finder/Explorer
// ---------------------------------------------------------------------------
ipcMain.handle("open-output-dir", async () => {
  const { shell } = await import("electron");
  if (fs.existsSync(OUTPUT_DIR)) {
    shell.openPath(OUTPUT_DIR);
  }
  return OUTPUT_DIR;
});
