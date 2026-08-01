import { useEffect, useState } from 'react';
import type { StageGateStatus } from '../types/global';

interface ProjectState {
  project_id: string;
  stage: string;
  progress: number;
  blocked_reason: string | null;
  next_action: { action: string; reason: string; target_mode: string } | null;
}

const STAGES = [
  ['problem_discovery', '问题探索'],
  ['market_research', '市场调研'],
  ['product_definition', '产品定义'],
  ['solution_design', '方案设计'],
  ['development', '开发'],
  ['testing', '测试验证'],
  ['iteration', '迭代改进'],
] as const;

/**
 * Keep the right rail compact: users see where they are and the adjacent
 * stages, while the gate details remain available only when an advance is
 * blocked.
 */
export function ProgressPanel({ projectId }: { projectId: string }) {
  const [state, setState] = useState<ProjectState | null>(null);
  const [gateStatus, setGateStatus] = useState<StageGateStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!window.kyrozen || !projectId) return;
    let cancelled = false;
    setGateStatus(null);
    setReviewNotice(null);
    const refresh = async () => {
      const next = await window.kyrozen?.getProjectState(projectId);
      if (!cancelled && next) setState(next);
    };
    void refresh();
    const unsubscribeStage = window.kyrozen.onStageUpdated((status) => {
      const statusProjectId = String((status as unknown as { project_id?: string }).project_id || '');
      if (statusProjectId && statusProjectId !== projectId) return;
      setGateStatus(status);
      void refresh();
    });
    // P1-03: 轮询仅用于兜底重同步，WebSocket 事件推送是主要更新路径。
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { cancelled = true; window.clearInterval(timer); unsubscribeStage(); };
  }, [projectId]);

  const handleAction = async (action: 'advance_normal' | 'return') => {
    if (!window.kyrozen || !projectId) return;
    setBusy(true);
    try {
      await window.kyrozen.sendStageAction(action, gateStatus?.stage ?? state?.stage ?? '');
      await new Promise((resolve) => setTimeout(resolve, 800));
    } catch {
      // The Python Agent pushes a fresh stage_updated event on success.
    } finally {
      setBusy(false);
    }
  };

  if (!state) return <div className="p-4 text-xs text-ink-faint">正在读取项目进度…</div>;
  const currentIndex = Math.max(0, STAGES.findIndex(([key]) => key === state.stage));
  const gate = gateStatus?.gate ?? null;
  const progress = Math.max(0, Math.min(100, gateStatus?.progress ?? state.progress ?? 0));
  const visibleStages = STAGES.slice(Math.max(0, currentIndex - 1), currentIndex + 2);
  const requestStageReview = async () => {
    if (!window.kyrozen || !projectId || !gate) return;
    setBusy(true);
    setReviewNotice(null);
    const currentLabel = STAGES[currentIndex]?.[1] || '当前阶段';
    const result = await window.kyrozen.sendChat(
      `请重新检查当前阶段“${currentLabel}”的目标和完成条件，结合当前项目已有成果判断是否可以进入下一阶段。如果可以，请说明判断依据；如果还不能，请说明缺少什么。`,
    );
    setReviewNotice(result.success ? '已提醒 Kyrozen 重新评估当前阶段。' : (result.error || '提醒失败，请稍后重试。'));
    setBusy(false);
  };

  return (
    <section className="p-4 border-b border-line" aria-label="项目进度">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-lg text-ink">项目进度</h2>
        <span className="text-xs text-accent font-medium tabular-nums">{progress}%</span>
      </div>
      <div className="w-full h-1.5 bg-paper-edge rounded-full overflow-hidden mb-4">
        <div className="h-full bg-accent rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
      </div>
      <div className="space-y-2">
        {visibleStages.map(([key, label], offset) => {
          const index = Math.max(0, currentIndex - 1) + offset;
          const current = index === currentIndex;
          const complete = index < currentIndex;
          return (
            <div key={key} className={`flex items-center gap-2 text-xs ${current ? 'text-ink font-medium' : complete ? 'text-ink-soft' : 'text-ink-ghost'}`}>
              <span className={`w-2.5 h-2.5 rounded-full ${current ? 'bg-accent' : complete ? 'bg-success' : 'border border-line-strong bg-surface'}`} />
              <span>{label}</span>
            </div>
          );
        })}
      </div>

      {gate && (
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={busy || gate.index === 0}
            onClick={() => void handleAction('return')}
            className="btn-secondary text-xs w-full"
          >
            返回上一阶段
          </button>
          <div className="relative group">
            <button
              type="button"
              disabled={!gate.can_advance || busy}
              onClick={() => void handleAction('advance_normal')}
              className="btn-primary text-xs w-full disabled:cursor-not-allowed disabled:opacity-45"
            >
              进入下一阶段
            </button>
            {!gate.can_advance && (
              <div className="pointer-events-auto absolute bottom-full right-0 z-20 mb-2 hidden w-72 rounded-sm border border-line bg-surface p-3 text-left shadow-lg group-hover:block">
                <div className="text-xs font-medium text-ink">还不能进入下一阶段</div>
                {gate.blocked_entry_reason && <div className="mt-1 text-[11px] text-danger">{gate.blocked_entry_reason}</div>}
                {gate.failed_tasks.length > 0 && <div className="mt-1 text-[11px] text-danger">有 {gate.failed_tasks.length} 个任务需要修复。</div>}
                {gate.missing.length > 0 && (
                  <ul className="mt-2 space-y-1 text-[11px] text-ink-soft">
                    {gate.missing.map((condition) => <li key={condition.item_id}>• {condition.label}{condition.detail ? `：${condition.detail}` : ''}</li>)}
                  </ul>
                )}
                <button type="button" onClick={() => void requestStageReview()} disabled={busy} className="btn-secondary mt-3 w-full text-xs">
                  让 Kyrozen 评估
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {reviewNotice && <div className="mt-2 text-[11px] text-ink-faint">{reviewNotice}</div>}
    </section>
  );
}
