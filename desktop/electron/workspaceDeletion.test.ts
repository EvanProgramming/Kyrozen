import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { deleteWorkspace } from './workspaceDeletion';

const root = await fs.mkdtemp(path.join(os.tmpdir(), 'kyrozen-workspace-delete-'));
const workspace = path.join(root, 'project');
await fs.mkdir(path.join(workspace, '.kyrozen'), { recursive: true });
await fs.writeFile(path.join(workspace, 'notes.txt'), 'temporary project data');

await deleteWorkspace(workspace, [root]);
assert.equal(await fs.access(workspace).then(() => true).catch(() => false), false);

await assert.rejects(
  () => deleteWorkspace(root, [root]),
  /路径不安全/,
);

await fs.rm(root, { recursive: true, force: true });
console.log('workspace deletion: all tests passed.');
