import { useEffect, useState } from 'react';

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

export function ProgressPanel({ projectId }: { projectId: string }) {
  const [state, setState] = useState<ProjectState | null>(null);

  useEffect(() => {
    if (!window.kyrozen || !projectId) return;
    let cancelled = false;
    const refresh = async () => {
      const next = await window.kyrozen?.getProjectState(projectId);
      if (!cancelled && next) setState(next);
    };
    void refresh();
    // P1-03: 轮询仅用于兜底重同步，WebSocket 事件推送是主要更新路径。
    // 2 秒过长对服务器压力过大；改为 30 秒。
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [projectId]);

  if (!state) return <div className="p-4 text-xs text-ink-faint">正在读取项目进度…</div>;
  const currentIndex = Math.max(0, STAGES.findIndex(([key]) => key === state.stage));
  const derivedProgress = Math.round((currentIndex / (STAGES.length - 1)) * 100);
  const progress = Math.max(state.progress || 0, derivedProgress);

  return (
    <section className="p-4 border-b border-line" aria-label="项目进度">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-hand text-lg text-ink">项目进度</h2>
        <span className="text-xs text-accent font-medium">{progress}%</span>
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
