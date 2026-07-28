/**
 * Kyrozen 3.6 P0 端到端发布门槛 — 发布运行记录（必须交付 #4）
 *
 * 每次 `playwright test` 运行结束后，本 reporter 在 e2e/release-runs/ 下写入一份
 * JSON 报告，包含文档要求的字段：
 *   - version   应用版本（package.json）
 *   - system    操作系统 + 架构
 *   - account   执行账号（由 spec 通过 KYROZEN_E2E_ACCOUNT 注入）
 *   - projectId 被测项目 ID（由 spec 通过 KYROZEN_E2E_PROJECT_ID 注入）
 *   - recording 本次运行的录像（video 附件路径）
 *   - screenshots 失败截图（image 附件路径）
 *   - results   每个用例的名称 / 状态 / 耗时 / 错误
 *
 * 纯函数 buildReleaseRun 被独立单测覆盖，保证记录逻辑本身“真实可用”。
 */

import { existsSync, readFileSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter';

export interface ReleaseRunResult {
  name: string;
  file: string;
  status: string;
  durationMs: number;
  error?: string;
}

export interface ReleaseRunMeta {
  version: string;
  system: string;
  account: string;
  projectId: string;
  startedAt: string;
  durationMs: number;
  status: FullResult['status'];
  results: ReleaseRunResult[];
  recordings: string[];
  screenshots: string[];
}

export function buildReleaseRun(meta: ReleaseRunMeta): Record<string, unknown> {
  return {
    schema: 'kyrozen.release-run/v1',
    generatedAt: new Date().toISOString(),
    version: meta.version,
    system: meta.system,
    account: meta.account,
    projectId: meta.projectId,
    startedAt: meta.startedAt,
    durationMs: meta.durationMs,
    status: meta.status,
    results: meta.results,
    recordings: [...new Set(meta.recordings)],
    screenshots: [...new Set(meta.screenshots)],
    summary: {
      total: meta.results.length,
      passed: meta.results.filter((r) => r.status === 'passed').length,
      failed: meta.results.filter((r) => r.status === 'failed').length,
      interrupted: meta.results.filter((r) => r.status === 'interrupted').length,
    },
  };
}

function resolveProjectRoot(): string {
  try {
    // ESM 安全：playwright 以 ESM 方式加载本 reporter。
    return path.dirname(fileURLToPath(import.meta.url));
  } catch {
    return process.cwd();
  }
}

const PROJECT_ROOT = resolveProjectRoot();

function readAppVersion(): string {
  const candidates = [
    path.resolve(PROJECT_ROOT, '..', 'package.json'), // e2e/ -> desktop/package.json
    path.resolve(process.cwd(), 'package.json'),
  ];
  for (const p of candidates) {
    if (existsSync(p)) {
      try {
        const pkg = JSON.parse(readFileSync(p, 'utf-8'));
        if (pkg?.version) return String(pkg.version);
      } catch {
        /* ignore */
      }
    }
  }
  return 'unknown';
}

class ReleaseReporter implements Reporter {
  private outputDir = path.resolve(PROJECT_ROOT, 'release-runs');
  private startedAt = new Date().toISOString();
  private results: ReleaseRunResult[] = [];
  private recordings: string[] = [];
  private screenshots: string[] = [];

  async onBegin(): Promise<void> {
    await mkdir(this.outputDir, { recursive: true });
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const error = result.error ? result.error.message || String(result.error) : undefined;
    this.results.push({
      name: test.title,
      file: test.location.file,
      status: result.status,
      durationMs: result.duration,
      error,
    });
    for (const attachment of result.attachments) {
      if (attachment.path && attachment.contentType.startsWith('video/')) {
        this.recordings.push(attachment.path);
      }
      if (attachment.path && attachment.contentType.startsWith('image/')) {
        this.screenshots.push(attachment.path);
      }
    }
  }

  async onEnd(result: FullResult): Promise<void> {
    const run = buildReleaseRun({
      version: readAppVersion(),
      system: `${process.platform} ${process.arch}`,
      account: process.env.KYROZEN_E2E_ACCOUNT || 'unknown',
      projectId: process.env.KYROZEN_E2E_PROJECT_ID || 'unknown',
      startedAt: this.startedAt,
      durationMs: result.duration,
      status: result.status,
      results: this.results,
      recordings: [...new Set(this.recordings)],
      screenshots: [...new Set(this.screenshots)],
    });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const file = path.join(this.outputDir, `release-run-${stamp}.json`);
    await writeFile(file, JSON.stringify(run, null, 2), 'utf-8');
    await writeFile(path.join(this.outputDir, 'latest.json'), JSON.stringify(run, null, 2), 'utf-8');
  }
}

export default ReleaseReporter;
