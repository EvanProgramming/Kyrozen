import fs from 'node:fs/promises';
import path from 'node:path';

function isSameOrInside(parent: string, target: string): boolean {
  const relative = path.relative(path.resolve(parent), path.resolve(target));
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

/**
 * Delete a workspace that the user explicitly confirmed from the project menu.
 * Protected paths are checked as descendants too, so a corrupt workspace map
 * can never cause a home directory or application data directory to be removed.
 */
export async function deleteWorkspace(root: string, protectedPaths: string[] = []): Promise<void> {
  if (typeof root !== 'string' || !root.trim() || !path.isAbsolute(root)) {
    throw new Error('项目工作区路径无效，已停止删除');
  }

  const resolvedRoot = path.resolve(root);
  if (resolvedRoot === path.parse(resolvedRoot).root) {
    throw new Error('项目工作区路径不安全，已停止删除');
  }

  for (const protectedPath of protectedPaths) {
    if (protectedPath && isSameOrInside(resolvedRoot, protectedPath)) {
      throw new Error('项目工作区路径不安全，已停止删除');
    }
  }

  await fs.rm(resolvedRoot, { recursive: true, force: true });
}
