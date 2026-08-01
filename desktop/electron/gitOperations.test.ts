import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { mkdir, mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import simpleGit from 'simple-git';
import {
  classifyCreateRepoError,
  classifyPushError,
  commitAndPush,
  getGitStatus,
  initGitRepo,
  scanSecrets,
} from './gitOperations';

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
  const result = await commitAndPush(directory, null, 'feat: initial project');
  assert.equal(result.success, true);
  assert.equal(result.committed, true);
  assert.equal(result.pushed, false);
  assert.equal(result.pushSkippedReason, 'no_remote');

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
  const result = await commitAndPush(directory, null, 'feat: local work');
  assert.equal(result.success, true);
  assert.equal(result.committed, true);
  assert.equal(result.pushed, false);
  assert.equal(result.pushSkippedReason, 'not_authenticated');

  const origin = (await simpleGit(directory).getRemotes(true)).find((item) => item.name === 'origin');
  assert.equal(origin?.refs.fetch, remote);
});

test('reports pushed only after a real push establishes an upstream', async () => {
  const directory = await workspace();
  const remoteDirectory = await workspace();
  await mkdir(path.join(directory, 'src'), { recursive: true });
  await simpleGit(remoteDirectory).init(true);
  await initGitRepo(directory, remoteDirectory);
  await writeFile(path.join(directory, 'src', 'index.ts'), 'export const ready = true;\n', 'utf-8');

  const result = await commitAndPush(directory, 'one-shot-test-token', 'feat: add application');
  assert.equal(result.success, true);
  assert.equal(result.committed, true);
  assert.equal(result.pushed, true);
  assert.equal(result.pushSkippedReason, undefined);

  const status = await getGitStatus(directory);
  assert.equal(status.remoteUrl, remoteDirectory);
  assert.equal(status.upstream, 'origin/main');
  assert.equal(status.ahead, 0);
});

test('push failures expose the canonical failureKind field', async () => {
  const directory = await workspace();
  const missingRemote = path.join(directory, 'missing-remote.git');
  await initGitRepo(directory, missingRemote);

  const result = await commitAndPush(directory, 'one-shot-test-token', 'chore: retry push');
  assert.equal(result.success, false);
  assert.equal(result.pushed, false);
  assert.equal(result.failureKind, 'unknown');
  assert.equal('kind' in result, false, 'public push result must not leak the internal kind field');
});

test('a non-repository failure also uses the canonical failureKind field', async () => {
  const directory = await workspace();
  const result = await commitAndPush(directory, 'one-shot-test-token', 'feat: impossible');
  assert.equal(result.success, false);
  assert.equal(result.pushed, false);
  assert.equal(result.failureKind, 'not_repository');
  assert.match(result.recovery || '', /初始化/);
});

// --- 3.5 #3: init must seed the .gitignore and create the first commit when
// the workspace already holds real project content. --------------------------
test('init creates .gitignore entries and an initial commit when content exists', async () => {
  const directory = await workspace();
  await writeFile(path.join(directory, 'README.md'), '# Test\n', 'utf-8');
  const result = await initGitRepo(directory);
  assert.equal(result.success, true);

  const git = simpleGit(directory);
  assert.equal((await git.branch()).current, 'main');
  assert.ok((await git.log()).all.length >= 1, 'expected an initial commit');
  const gitignore = await readFile(path.join(directory, '.gitignore'), 'utf-8');
  assert.ok(gitignore.includes('.env'), '.gitignore should contain .env');
  assert.ok(gitignore.includes('node_modules/'), '.gitignore should contain node_modules/');
});

test('init is idempotent — a second init does not create an extra commit', async () => {
  const directory = await workspace();
  await writeFile(path.join(directory, 'README.md'), '# Test\n', 'utf-8');
  await initGitRepo(directory);
  const firstCount = (await simpleGit(directory).log()).all.length;
  assert.ok(firstCount >= 1, 'expected at least one commit after first init');

  await initGitRepo(directory); // second call must not re-commit
  const secondCount = (await simpleGit(directory).log()).all.length;
  assert.equal(secondCount, firstCount, 'init must not create duplicate commits');
});


// --- 3.5 #5: the token must never leak into the workspace. -----------------
test('scanSecrets returns zero hits for a clean workspace', async () => {
  const directory = await workspace();
  await initGitRepo(directory);
  await writeFile(path.join(directory, 'app.js'), 'console.log("hello")\n', 'utf-8');
  const hits = await scanSecrets(directory, 'ghp_supersecretTOKEN123');
  assert.deepEqual(hits, []);
});

test('scanSecrets detects a planted token inside the workspace', async () => {
  const directory = await workspace();
  await initGitRepo(directory);
  const leakPath = path.join(directory, 'leak.txt');
  await writeFile(leakPath, 'token=ghp_supersecretTOKEN123\n', 'utf-8');
  const hits = await scanSecrets(directory, 'ghp_supersecretTOKEN123');
  assert.ok(hits.includes('leak.txt'), `expected leak.txt in hits, got ${JSON.stringify(hits)}`);

  // Removing the leak clears the scan again.
  await writeFile(leakPath, 'token=clean\n', 'utf-8');
  assert.deepEqual(await scanSecrets(directory, 'ghp_supersecretTOKEN123'), []);
});

// --- 3.5 #6: push / create-repo failure classification. --------------------
test('classifyPushError maps the five failure kinds', () => {
  assert.equal(classifyPushError('fatal: remote origin already exists').kind, 'remote_exists');
  assert.equal(
    classifyPushError("fatal: unable to access 'https://github.com': Could not resolve host").kind,
    'network_failed',
  );
  assert.equal(classifyPushError('remote: Invalid username or password').kind, 'auth_failed');
  assert.equal(
    classifyPushError("fatal: unable to access 'https://github.com/example/repo': The requested URL returned error: 403").kind,
    'auth_failed',
  );
  assert.equal(
    classifyPushError('! [rejected] (non-fast-forward)').kind,
    'non_fast_forward',
  );
  assert.equal(classifyPushError('fatal: some unexpected git error').kind, 'unknown');
});

test('classifyCreateRepoError maps name-exists / auth / network / unknown', () => {
  assert.equal(classifyCreateRepoError(422, { message: 'name already exists' }).kind, 'name_exists');
  assert.equal(classifyCreateRepoError(401, {}).kind, 'auth_failed');
  assert.equal(classifyCreateRepoError(403, {}).kind, 'auth_failed');
  assert.equal(classifyCreateRepoError(0, null).kind, 'network_failed');
  assert.equal(classifyCreateRepoError(500, {}).kind, 'unknown');
});
