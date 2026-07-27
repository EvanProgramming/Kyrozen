// Server URL resolution for the Kyrozen desktop client.
//
// Historically the desktop hardcoded `https://kyrozen.chat` and forced every
// non-localhost connection to TLS (http -> https, ws -> wss). That breaks the
// common self-hosted case where the server is reached directly by IP address
// without a registered / ICP-filed domain (and therefore has no TLS
// certificate). Let's Encrypt also cannot issue certs for a raw IP.
//
// These helpers keep an *explicitly provided* scheme intact and only guess a
// scheme when the user supplies a bare host. This lets the client connect to
// `http://<server-ip>:8000` (plain HTTP) or `wss://...` without being silently
// rewritten to HTTPS.

/** Returns true for IPv4 (four dot-separated octets) or IPv6 (contains ':'). */
export function isIpAddress(host: string): boolean {
  if (host.includes(':')) return true; // IPv6
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(host); // IPv4
}

/**
 * Normalize a user-supplied server URL.
 *
 * - If a scheme (http/https) is already present, it is respected as-is.
 * - If only a bare host is given:
 *     - localhost / 127.0.0.1 / an IP address  -> http://
 *     - anything else (a domain)              -> https://
 */
export function normalizeServerUrl(url: string): string {
  const clean = (url || '').trim().replace(/\/+$/, '');
  if (!clean) return clean;
  if (/^https?:\/\//i.test(clean)) {
    return clean;
  }
  const host = clean.split('/')[0];
  if (host === 'localhost' || host === '127.0.0.1' || isIpAddress(host)) {
    return `http://${clean}`;
  }
  return `https://${clean}`;
}

/**
 * Derive the desktop WebSocket URL from an http(s) server URL.
 * Plain http -> ws, https -> wss. An already-websocket URL is respected.
 */
export function getWebSocketUrlFromHttp(httpUrl: string): string {
  const url = (httpUrl || '').trim();
  if (/^wss?:\/\//i.test(url)) {
    return url;
  }
  const secure = url.startsWith('https://');
  const base = url.replace(/^https?:\/\//i, '');
  return `${secure ? 'wss' : 'ws'}://${base}/ws/desktop`;
}

/**
 * Default server URL: prefer an explicit env override
 * (KYROZEN_DESKTOP_SERVER_URL) so a packaged build can be pointed at a server
 * by IP without recompiling; otherwise fall back to localhost.
 */
export function resolveDefaultServerUrl(): string {
  // Production default: the public Kyrozen backend. Using the domain (not a raw
  // IP) keeps server infrastructure details out of the public repo and gives
  // TLS. KYROZEN_DESKTOP_SERVER_URL overrides this for dev/self-hosted setups.
  return process.env.KYROZEN_DESKTOP_SERVER_URL || 'https://kyrozen.chat';
}
