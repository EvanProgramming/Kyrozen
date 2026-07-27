import assert from 'node:assert/strict';
import {
  normalizeServerUrl,
  getWebSocketUrlFromHttp,
  resolveDefaultServerUrl,
  isIpAddress,
} from './serverUrl';

interface Case {
  input: string;
  expected: string;
}

// normalizeServerUrl must keep an explicit scheme intact and never upgrade
// http://<ip> to https://<ip> (no domain / no TLS cert => direct IP works).
const normalizeCases: Case[] = [
  { input: 'http://192.168.1.113:8000', expected: 'http://192.168.1.113:8000' },
  { input: 'https://192.168.1.113:8000', expected: 'https://192.168.1.113:8000' },
  { input: '192.168.1.113:8000', expected: 'http://192.168.1.113:8000' },
  { input: 'http://example.com', expected: 'http://example.com' },
  { input: 'example.com', expected: 'https://example.com' },
  { input: 'http://localhost:8000', expected: 'http://localhost:8000' },
  { input: 'localhost', expected: 'http://localhost' },
  { input: 'http://127.0.0.1:8000', expected: 'http://127.0.0.1:8000' },
  { input: 'https://kyrozen.chat', expected: 'https://kyrozen.chat' },
  { input: 'http://10.0.0.5:9000/', expected: 'http://10.0.0.5:9000' },
  { input: '   http://1.2.3.4:8000/  ', expected: 'http://1.2.3.4:8000' },
];

for (const { input, expected } of normalizeCases) {
  assert.equal(
    normalizeServerUrl(input),
    expected,
    `normalizeServerUrl(${JSON.stringify(input)})`,
  );
}

// getWebSocketUrlFromHttp: http -> ws, https -> wss, IP stays plain ws.
const wsCases: Case[] = [
  { input: 'http://192.168.1.113:8000', expected: 'ws://192.168.1.113:8000/ws/desktop' },
  { input: 'https://192.168.1.113:8000', expected: 'wss://192.168.1.113:8000/ws/desktop' },
  { input: 'http://localhost:8000', expected: 'ws://localhost:8000/ws/desktop' },
  { input: 'wss://example.com/ws/desktop', expected: 'wss://example.com/ws/desktop' },
  { input: 'ws://1.2.3.4:8000/ws/desktop', expected: 'ws://1.2.3.4:8000/ws/desktop' },
];

for (const { input, expected } of wsCases) {
  assert.equal(
    getWebSocketUrlFromHttp(input),
    expected,
    `getWebSocketUrlFromHttp(${JSON.stringify(input)})`,
  );
}

assert.equal(isIpAddress('192.168.1.113'), true);
assert.equal(isIpAddress('10.0.0.5'), true);
assert.equal(isIpAddress('localhost'), false);
assert.equal(isIpAddress('example.com'), false);
assert.equal(isIpAddress('::1'), true); // IPv6

const prev = process.env.KYROZEN_DESKTOP_SERVER_URL;
process.env.KYROZEN_DESKTOP_SERVER_URL = 'http://203.0.113.10:8000';
assert.equal(resolveDefaultServerUrl(), 'http://203.0.113.10:8000');
delete process.env.KYROZEN_DESKTOP_SERVER_URL;
assert.equal(resolveDefaultServerUrl(), 'https://kyrozen.chat');
if (prev !== undefined) process.env.KYROZEN_DESKTOP_SERVER_URL = prev;

console.log('serverUrl helpers: all tests passed.');
