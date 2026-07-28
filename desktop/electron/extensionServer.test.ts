import assert from 'node:assert/strict';
import test from 'node:test';
import type { AddressInfo } from 'node:net';

import { createExtensionServer } from './extensionServer';

test('localhost bridge requires its per-launch authentication token', async () => {
  let captured = '';
  const token = 'audit-test-token';
  const server = createExtensionServer({
    onClip: (payload) => { captured = payload.title; },
    onTestReport: () => undefined,
  }, token);
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;
  try {
    const unauthenticated = await fetch(`http://127.0.0.1:${port}/api/clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Origin: 'https://attacker.invalid' },
      body: JSON.stringify({ url: 'https://attacker.invalid', title: 'blocked' }),
    });
    assert.equal(unauthenticated.status, 401);
    assert.equal(captured, '');

    const authenticated = await fetch(`http://127.0.0.1:${port}/api/clip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Kyrozen-Bridge-Token': token },
      body: JSON.stringify({ url: 'https://example.test', title: 'accepted' }),
    });
    assert.equal(authenticated.status, 200);
    assert.equal(captured, 'accepted');
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
