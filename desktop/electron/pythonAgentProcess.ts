import type { SpawnOptionsWithoutStdio } from 'node:child_process';

export interface PythonAgentSpawnConfig {
  args: string[];
  options: SpawnOptionsWithoutStdio;
}

/**
 * Build the Python Agent process configuration without allowing Python to
 * create bytecode next to the packaged source files.
 *
 * A packaged macOS app is a signed, sealed bundle.  CPython's default
 * `__pycache__` writes mutate that bundle after first launch and invalidate the
 * signature.  `-B` protects the Agent itself, while the environment variable
 * is inherited by any Python subprocesses the Agent starts.
 */
export function createPythonAgentSpawnConfig(
  agentScript: string,
  cwd: string,
  baseEnv: NodeJS.ProcessEnv,
  extraEnv: NodeJS.ProcessEnv,
): PythonAgentSpawnConfig {
  return {
    args: ['-B', agentScript],
    options: {
      cwd,
      env: {
        ...baseEnv,
        ...extraEnv,
        // Keep this last so a parent shell cannot accidentally re-enable
        // bytecode writes inside a signed application bundle.
        PYTHONDONTWRITEBYTECODE: '1',
      },
    },
  };
}
