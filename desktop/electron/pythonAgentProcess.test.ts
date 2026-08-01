import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createPythonAgentSpawnConfig } from './pythonAgentProcess';

test('Python Agent spawn prevents bytecode writes in the signed app bundle', () => {
  const config = createPythonAgentSpawnConfig(
    '/Applications/Kyrozen.app/Contents/Resources/python_agent/main.py',
    '/Applications/Kyrozen.app/Contents/Resources',
    {
      PATH: '/usr/bin',
      PYTHONDONTWRITEBYTECODE: '0',
    },
    {
      KYROZEN_DESKTOP_MODE: '1',
      PYTHONDONTWRITEBYTECODE: '0',
    },
  );

  assert.deepEqual(config.args, [
    '-B',
    '/Applications/Kyrozen.app/Contents/Resources/python_agent/main.py',
  ]);
  assert.equal(config.options.cwd, '/Applications/Kyrozen.app/Contents/Resources');
  assert.equal(config.options.env?.PATH, '/usr/bin');
  assert.equal(config.options.env?.KYROZEN_DESKTOP_MODE, '1');
  assert.equal(config.options.env?.PYTHONDONTWRITEBYTECODE, '1');
});
