import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildReleaseRun } from '../e2e/release-reporter';

test('buildReleaseRun assembles the 3.6 #4 release-run metadata', () => {
  const run = buildReleaseRun({
    version: '0.1.0',
    system: 'darwin arm64',
    account: 'desktop-e2e@local.test',
    projectId: 'proj_abc123',
    startedAt: '2026-07-28T00:00:00.000Z',
    durationMs: 12345,
    status: 'passed',
    results: [
      { name: '登录 → 建项目', file: 'e2e/core-journey.spec.ts', status: 'passed', durationMs: 5000 },
      { name: '失败用例', file: 'e2e/core-journey.spec.ts', status: 'failed', durationMs: 1000, error: 'boom' },
    ],
    recordings: ['/tmp/v.mp4', '/tmp/v.mp4'],
    screenshots: ['/tmp/s.png'],
  });

  assert.equal(run.schema, 'kyrozen.release-run/v1');
  assert.equal(run.version, '0.1.0');
  assert.equal(run.system, 'darwin arm64');
  assert.equal(run.account, 'desktop-e2e@local.test');
  assert.equal(run.projectId, 'proj_abc123');
  assert.equal(run.status, 'passed');
  assert.equal((run.recordings as string[]).length, 1); // 去重
  assert.equal((run.screenshots as string[]).length, 1);
  assert.equal((run.summary as any).total, 2);
  assert.equal((run.summary as any).passed, 1);
  assert.equal((run.summary as any).failed, 1);
});
