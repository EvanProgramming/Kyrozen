import { useEffect, useState } from 'react';

interface ProjectState {
  project_id: string;
  stage: string;
  progress: number;
  blocked_reason: string | null;
  next_action: { action: string; reason: string; target_mode: string } | null;
}

const STAGE_LABELS: Record<string, string> = {
  problem_discovery: '1. 问题发现',
  market_research: '2. 市场调研',
  product_definition: '3. 产品定义',
  solution_design: '4. 方案设计',
  development: '5. 开发',
  testing: '6. 测试',
  iteration: '7. 迭代改进',
};

const STAGE_ORDER = Object.keys(STAGE_LABELS);

interface Props {
  projectId: string;
}

export function ProgressPanel({ projectId }: Props) {
  const [state, setState] = useState<ProjectState | null>(null);

  useEffect(() => {
    if (!window.kyrozen || !projectId) return;
    let cancelled = false;
    window.kyrozen.getProjectState(projectId).then((s) => {
      if (!cancelled && s) setState(s);
    });
    return () => { cancelled = true; };
  }, [projectId]);

  if (!state) {
    return (
      <div className="p-4 text-xs text-slate-500">加载进度中...</div>
    );
  }

  const currentIdx = STAGE_ORDER.indexOf(state.stage);

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-slate-200 mb-3">开发进度</h2>

      <div className="text-xs text-slate-300 mb-1">
        当前阶段：<span className="text-blue-400 font-medium">{STAGE_LABELS[state.stage] || state.stage}</span>
      </div>

      <div className="w-full bg-slate-700 rounded-full h-2 mb-3">
        <div
          className="bg-blue-500 h-2 rounded-full transition-all"
          style={{ width: `${Math.max(1, state.progress)}%` }}
        />
      </div>

      <div className="text-xs text-slate-400 mb-4">{state.progress}%</div>

      {state.next_action && (
        <div className="bg-slate-800 rounded-lg p-2 mb-3 border border-slate-700">
          <div className="text-xs font-medium text-slate-300">{state.next_action.action}</div>
          <div className="text-xs text-slate-500 mt-0.5">{state.next_action.reason}</div>
        </div>
      )}

      {state.blocked_reason && (
        <div className="text-xs text-red-400 bg-red-400/10 rounded p-2 mb-3">
          ⚠ {state.blocked_reason}
        </div>
      )}

      <div className="space-y-0.5">
        {STAGE_ORDER.map((stage, idx) => {
          const isCurrent = stage === state.stage;
          const isPast = idx < currentIdx;
          return (
            <div
              key={stage}
              className={`text-xs flex items-center gap-1.5 px-2 py-0.5 rounded ${
                isCurrent
                  ? 'bg-blue-600/20 text-blue-300 font-medium'
                  : isPast
                  ? 'text-slate-500'
                  : 'text-slate-600'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${
                isCurrent ? 'bg-blue-400' : isPast ? 'bg-slate-500' : 'bg-slate-700'
              }`} />
              {STAGE_LABELS[stage]}
            </div>
          );
        })}
      </div>
    </div>
  );
}
