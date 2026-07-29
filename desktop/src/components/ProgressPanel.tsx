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

const KIND_LABEL: Record<string, string> = {
  deliverable: '交付物',
  confirmation: '确认',
  verification: '验证',
  task: '任务',
};

type StageAction = 'refresh' | 'advance_normal' | 'advance_risk' | 'return';
type RiskDetails = { reason: string; impact: string; recovery: string };

/** Check / alert glyph for stage-gate conditions (single accent color). */
function ConditionIcon({ satisfied, className }: { satisfied: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {satisfied ? (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M8 12.5l2.5 2.5L16 9" />
        </>
      ) : (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7.5v5" />
          <path d="M12 16.5v.5" />
        </>
      )}
    </svg>
  );
}

/**
 * UI cleanup: the former top-of-chat StageGatePanel is merged into this right
 * side panel. Stage requirements are listed under the stage steps, and the
 * control buttons live behind a "更多操作" toggle.
 */
export function ProgressPanel({ projectId }: { projectId: string }) {
  const [state, setState] = useState<ProjectState | null>(null);
  const [gateStatus, setGateStatus] = useState<StageGateStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [riskOpen, setRiskOpen] = useState(false);
  const [riskDetails, setRiskDetails] = useState<RiskDetails>({ reason: '', impact: '', recovery: '' });

  useEffect(() => {
    if (!window.kyrozen || !projectId) return;
    let cancelled = false;
    setGateStatus(null);
    setMoreOpen(false);
    setRiskOpen(false);
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

  const handleAction = async (action: StageAction, details?: RiskDetails) => {
    if (!window.kyrozen || !projectId) return;
    setBusy(true);
    try {
      await window.kyrozen.sendStageAction(action, gateStatus?.stage ?? state?.stage ?? '', details);
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
        {STAGES.map(([key, label], index) => {
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

      {/* Stage requirements written directly inside the progress area. */}
      {gate && (
        <div className="mt-4 space-y-3">
          {gate.blocked_entry_reason && (
            <div className="panel p-2.5 border-l-2 border-l-danger bg-danger-soft text-xs text-danger">{gate.blocked_entry_reason}</div>
          )}
          {gate.failed_tasks.length > 0 && (
            <div className="panel p-2.5 border-l-2 border-l-danger bg-danger-soft space-y-1.5">
              <div className="text-xs text-danger font-medium">存在失败任务，需先修复</div>
              {gate.failed_tasks.map((task) => (
                <div key={task.task_id} className="text-[11px] text-ink-soft">
                  <span className="text-danger font-medium">{task.task_id}</span> · {task.error}
                  <div className="text-ink-faint mt-0.5">修复：{task.repair}</div>
                </div>
              ))}
            </div>
          )}
          {gate.missing.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-xs font-medium text-danger">尚未满足（{gate.missing.length}）</div>
              {gate.missing.map((condition) => (
                <div key={condition.item_id} className="flex items-start gap-2 text-xs text-ink-soft">
                  <ConditionIcon satisfied={false} className="w-3.5 h-3.5 flex-shrink-0 text-danger mt-0.5" />
                  <div className="flex-1">
                    <span>{condition.label}</span>
                    <span className="ml-1 text-[11px] text-ink-faint">[{KIND_LABEL[condition.kind] ?? condition.kind}]</span>
                    {condition.detail && <span className="text-[11px] text-ink-faint"> · {condition.detail}</span>}
                    {condition.skippable && <span className="ml-1 text-[11px] text-ink-faint">（可跳过）</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {gate.satisfied.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-xs font-medium text-accent">已满足（{gate.satisfied.length}）</div>
              {gate.satisfied.map((condition) => (
                <div key={condition.item_id} className="flex items-start gap-2 text-xs text-ink-soft">
                  <ConditionIcon satisfied className="w-3.5 h-3.5 flex-shrink-0 text-accent mt-0.5" />
                  <div className="flex-1">
                    <span>{condition.label}</span>
                    <span className="ml-1 text-[11px] text-ink-faint">[{KIND_LABEL[condition.kind] ?? condition.kind}]</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Control buttons hidden behind 更多操作. */}
      {gate && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setMoreOpen((value) => !value)}
            className="btn-ghost text-xs w-full flex items-center justify-between"
            aria-expanded={moreOpen}
          >
            <span>更多操作</span>
            <span className="text-ink-faint">{moreOpen ? '收起' : '展开'}</span>
          </button>
          {moreOpen && (
            <div className="mt-2 space-y-2">
              <button
                type="button"
                disabled={!gate.can_advance || busy}
                onClick={() => void handleAction('advance_normal')}
                className="btn-primary text-xs w-full"
                title={gate.can_advance ? '当前阶段条件已满足，进入下一阶段' : '当前阶段仍有未满足条件'}
              >
                进入下一阶段
              </button>
              <button
                type="button"
                disabled={busy || gate.missing.some((condition) => !condition.skippable)}
                onClick={() => setRiskOpen((value) => !value)}
                className="btn-secondary text-xs w-full"
                title="跳过未满足的必需条件并进入下一阶段（会记录风险）"
              >
                带风险推进
              </button>
              <button
                type="button"
                disabled={busy || gate.index === 0}
                onClick={() => void handleAction('return')}
                className="btn-ghost text-xs w-full"
              >
                返回上一阶段
              </button>
              {riskOpen && (
                <div className="panel p-2.5 border-l-2 border-l-warning bg-warning-soft space-y-2">
                  <div className="text-xs font-medium text-ink">说明为什么需要带风险推进</div>
                  <input className="input text-xs w-full" value={riskDetails.reason} onChange={(event) => setRiskDetails((value) => ({ ...value, reason: event.target.value }))} placeholder="具体原因（必填）" />
                  <input className="input text-xs w-full" value={riskDetails.impact} onChange={(event) => setRiskDetails((value) => ({ ...value, impact: event.target.value }))} placeholder="可能影响" />
                  <input className="input text-xs w-full" value={riskDetails.recovery} onChange={(event) => setRiskDetails((value) => ({ ...value, recovery: event.target.value }))} placeholder="后续补救办法" />
                  <div className="flex gap-2">
                    <button type="button" className="btn-primary text-xs" disabled={!riskDetails.reason.trim() || busy} onClick={() => { void handleAction('advance_risk', riskDetails); setRiskOpen(false); }}>确认并记录风险</button>
                    <button type="button" className="btn-ghost text-xs" onClick={() => setRiskOpen(false)}>取消</button>
                  </div>
                </div>
              )}
              {gateStatus && gateStatus.skips.length > 0 && (
                <div className="text-[11px] text-ink-faint">
                  已带风险跳过 {gateStatus.skips.length} 项：{gateStatus.skips.map((skip) => skip.item_id).join('、')}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {state.next_action && (
        <div className="mt-4 panel p-3">
          <div className="text-xs font-medium text-ink">下一步：{state.next_action.action}</div>
          <div className="text-xs text-ink-faint mt-1">{state.next_action.reason}</div>
        </div>
      )}
      {state.blocked_reason && <div className="mt-3 bg-danger-soft text-danger border border-line rounded-sm p-2 text-xs">{state.blocked_reason}</div>}
    </section>
  );
}
