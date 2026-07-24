import http from 'http';
import { AddressInfo } from 'net';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

export interface ClipPayload {
  url: string;
  title: string;
  selection?: string;
  bodyText?: string;
}

export interface TestReportPayload {
  url: string;
  errors: Array<{ message: string; source?: string; line?: number; column?: number }>;
  metrics?: {
    loadTime?: number;
    domNodes?: number;
  };
}

export interface ExtensionServerCallbacks {
  onClip: (payload: ClipPayload) => void;
  onTestReport: (payload: TestReportPayload) => void;
  onNativeMessage?: (message: Record<string, unknown>) => void;
}

function readJsonBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk.toString();
      if (body.length > 5 * 1024 * 1024) {
        reject(new Error('Payload too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        reject(new Error('Invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function sendJson(res: http.ServerResponse, status: number, data: unknown): void {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(body);
}

function isValidClip(payload: unknown): payload is ClipPayload {
  const p = payload as Record<string, unknown>;
  return typeof p.url === 'string' && typeof p.title === 'string';
}

function isValidTestReport(payload: unknown): payload is TestReportPayload {
  const p = payload as Record<string, unknown>;
  return typeof p.url === 'string' && Array.isArray(p.errors);
}

export function createExtensionServer(callbacks: ExtensionServerCallbacks): http.Server {
  const server = http.createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
      });
      res.end();
      return;
    }

    if (req.method !== 'POST') {
      sendJson(res, 405, { error: 'Method not allowed' });
      return;
    }

    try {
      const body = await readJsonBody(req);
      const pathname = req.url?.split('?')[0] || '';

      if (pathname === '/api/clip') {
        if (!isValidClip(body)) {
          sendJson(res, 400, { error: 'Missing url or title' });
          return;
        }
        callbacks.onClip(body);
        sendJson(res, 200, { success: true });
        return;
      }

      if (pathname === '/api/test-report') {
        if (!isValidTestReport(body)) {
          sendJson(res, 400, { error: 'Missing url or errors' });
          return;
        }
        callbacks.onTestReport(body);
        sendJson(res, 200, { success: true });
        return;
      }

      if (pathname === '/api/native-message') {
        const msg = body as Record<string, unknown>;
        if (callbacks.onNativeMessage) {
          callbacks.onNativeMessage(msg);
        }
        sendJson(res, 200, { success: true, received: msg.type || 'unknown' });
        return;
      }

      sendJson(res, 404, { error: 'Not found' });
    } catch (err: any) {
      sendJson(res, 400, { error: err.message || 'Bad request' });
    }
  });

  return server;
}

function getNativeMessagingPortFilePath(): string {
  const platform = os.platform();
  let baseDir: string;
  if (platform === 'darwin') {
    baseDir = path.join(os.homedir(), 'Library', 'Application Support', 'Kyrozen');
  } else if (platform === 'win32') {
    baseDir = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'), 'Kyrozen');
  } else {
    baseDir = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'kyrozen');
  }
  return path.join(baseDir, 'extension-server-port.json');
}

async function writeExtensionServerPort(port: number): Promise<void> {
  const filePath = getNativeMessagingPortFilePath();
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify({ port, updated_at: new Date().toISOString() }, null, 2));
}

export function startExtensionServer(
  callbacks: ExtensionServerCallbacks,
  preferredPort = 9339,
): Promise<{ server: http.Server; port: number }> {
  const server = createExtensionServer(callbacks);
  return new Promise((resolve, reject) => {
    server.on('error', (err: NodeJS.ErrnoException) => {
      if (err.code === 'EADDRINUSE') {
        server.listen(0, '127.0.0.1');
        return;
      }
      reject(err);
    });
    server.on('listening', async () => {
      const address = server.address() as AddressInfo;
      try {
        await writeExtensionServerPort(address.port);
      } catch (writeErr) {
        // Port file is best-effort; the host can fall back to the default port.
        console.error('Failed to write extension server port file:', writeErr);
      }
      resolve({ server, port: address.port });
    });
    server.listen(preferredPort, '127.0.0.1');
  });
}
