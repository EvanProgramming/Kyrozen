import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import simpleGit from 'simple-git';
import { commitAndPush, getGitStatus, initGitRepo } from './gitOperations';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

async function workspace() {
  const directory = await mkdtemp(path.join(tmpdir(), 'kyrozen-git-'));
  temporaryDirectories.push(directory);
  return directory;
}

test('initializes a main branch and creates a local commit without GitHub', async () => {
  const directory = await workspace();
  assert.equal((await initGitRepo(directory)).success, true);
  await writeFile(path.join(directory, 'README.md'), '# Test\n', 'utf-8');
  assert.equal((await commitAndPush(directory, null, 'feat: initial project')).success, true);

  const git = simpleGit(directory);
  assert.equal((await git.branch()).current, 'main');
  assert.equal((await git.log()).latest?.message, 'feat: initial project');
  assert.equal((await getGitStatus(directory)).untracked?.length, 0);
});

test('does not write credentials into the configured remote URL', async () => {
  const directory = await workspace();
  const remote = 'https://github.com/example/project.git';
  await initGitRepo(directory, remote);
  await writeFile(path.join(directory, 'index.js'), 'export {}\n', 'utf-8');
  assert.equal((await commitAndPush(directory, null, 'feat: local work')).success, true);

  const origin = (await simpleGit(directory).getRemotes(true)).find((item) => item.name === 'origin');
  assert.equal(origin?.refs.fetch, remote);
});
