#!/usr/bin/env node
/**
 * Native Messaging Host for the Kyrozen browser extension.
 *
 * The browser launches this executable directly and communicates over stdin/stdout
 * using the Chrome Native Messaging protocol (length-prefixed JSON messages).
 * This host forwards messages to the Kyrozen desktop client's extension HTTP server
 * running on localhost, so it does not need a direct IPC channel to Electron.
 */

import fs from 'fs/promises';
import path from 'path';
import os from 'os';

const DEFAULT_PORT = 9339;
const PORT_FILE_NAME = 'extension-server-port.json';

function getPortFilePath(): string {
  const platform = os.platform();
  let baseDir: string;
  if (platform === 'darwin') {
    baseDir = path.join(os.homedir(), 'Library', 'Application Support', 'Kyrozen');
  } else if (platform === 'win32') {
    baseDir = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'Kyrozen');
  } else {
    baseDir = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'kyrozen');
  }
  return path.join(baseDir, PORT_FILE_NAME);
}

async function resolveServerConfig(): Promise<{ port: number; authToken: string | null }> {
  try {
    const raw = await fs.readFile(getPortFilePath(), 'utf-8');
    const data = JSON.parse(raw) as { port?: number; authToken?: string };
    if (typeof data.port === 'number' && data.port > 0) {
      return { port: data.port, authToken: data.authToken || null };
    }
  } catch {
    // Fall back to the default port.
  }
  return { port: DEFAULT_PORT, authToken: null };
}

interface NativeMessage {
  type: string;
  [key: string]: unknown;
}

class NativeMessagingReader {
  private buffer = Buffer.alloc(0);
  private pendingLength: number | null = null;
  private onMessage: (msg: NativeMessage) => void;

  constructor(onMessage: (msg: NativeMessage) => void) {
    this.onMessage = onMessage;
    process.stdin.on('data', (chunk: Buffer) => this._onData(chunk));
    process.stdin.on('end', () => this._onEnd());
  }

  private _onData(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    this._processBuffer();
  }

  private _onEnd(): void {
    // Stream closed by the browser; exit cleanly.
    process.exit(0);
  }

  private _processBuffer(): void {
    while (true) {
      if (this.pendingLength === null) {
        if (this.buffer.length < 4) return;
        this.pendingLength = this.buffer.readUInt32LE(0);
        this.buffer = this.buffer.subarray(4);
        if (this.pendingLength === 0 || this.pendingLength > 10 * 1024 * 1024) {
          process.exit(1);
        }
      }

      if (this.buffer.length < this.pendingLength) return;
      const messageBuffer = this.buffer.subarray(0, this.pendingLength);
      this.buffer = this.buffer.subarray(this.pendingLength);
      this.pendingLength = null;

      try {
        const text = messageBuffer.toString('utf-8');
        const message = JSON.parse(text) as NativeMessage;
        this.onMessage(message);
      } catch {
        // Ignore malformed messages and continue reading.
      }
    }
  }
}

function writeMessage(message: unknown): void {
  const text = JSON.stringify(message);
  const buffer = Buffer.from(text, 'utf-8');
  const lengthBuffer = Buffer.allocUnsafe(4);
  lengthBuffer.writeUInt32LE(buffer.length, 0);
  process.stdout.write(lengthBuffer);
  process.stdout.write(buffer);
}

async function forwardToDesktop(message: NativeMessage): Promise<unknown> {
  const { port, authToken } = await resolveServerConfig();
  if (!authToken) return { success: false, error: 'Desktop bridge credentials unavailable' };
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/native-message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Kyrozen-Bridge-Token': authToken,
      },
      body: JSON.stringify(message),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!response.ok) {
      const text = await response.text();
      return { success: false, error: text || `HTTP ${response.status}` };
    }
    return await response.json();
  } catch (err: any) {
    clearTimeout(timeout);
    return { success: false, error: err.message || String(err) };
  }
}

async function runHost() {
  // Send a ready message so the extension knows the host is listening.
  writeMessage({ type: 'host_ready' });

  new NativeMessagingReader(async (message) => {
    const response = await forwardToDesktop(message);
    writeMessage({
      type: 'response',
      request_id: message.request_id,
      success: true,
      request: message,
      response,
    });
  });

  // Keep the process alive while stdin is open.
  await new Promise(() => {
    // Intentionally never resolves; process exits when stdin closes.
  });
}

runHost().catch((err) => {
  console.error('Native messaging host error:', err);
  process.exit(1);
});
