import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props { projectId: string; onClose: () => void }
type Row = Record<string, unknown>;
type WorkspaceData = {
  project?: Row;
  state?: Row;
  decisions?: Row[];
  artifacts?: Row[];
  tasks?: Row[];
  sections?: Record<string, Row>;
};

const TABS = [
  ['overview', '项目主页', '目标、阶段与下一步'],
  ['problem', '问题与证据', '用户问题、证据和市场结论'],
  ['product', '产品方案', '产品简报、PRD 与技术方案'],
  ['build', '开发交付', '实现任务、代码和硬件交付'],
  ['validation', '测试验证', '测试结果与用户反馈'],
  ['learning', '学习改进', '复盘、经验和改进建议'],
  ['decisions', '项目决策', '关键决定与原因'],
] as const;

const LABELS: Record<string, string> = {
  name: '项目名称', description: '项目描述', goal: '项目目标', initial_idea: '最初想法',
  current_stage: '当前阶段', stage: '当前阶段', progress: '完成进度', next_steps: '下一步',
  problem_statement: '问题定义', evidence_summary: '已有证据', affected_users: '目标用户',
  recommendation: '结论建议', market_status: '市场现状', market_gap: '市场机会',
  product_goal: '产品目标', target_user: '目标用户', value_proposition: '核心价值',
  mvp_features: 'MVP 功能', out_of_scope: '本次不做', functional_requirements: '功能要求',
  risks: '风险', status: '状态', title: '标题', decision: '决定', reason: '原因',
  next_action: '建议下一步', action: '行动', target_mode: '对应阶段', result: '结果',
};

const STAGE_NAMES: Record<string, string> = {
  problem_discovery: '问题探索', market_research: '市场调研', product_definition: '产品定义',
  solution_design: '方案设计', development: '开发', testing: '测试验证', iteration: '迭代改进',
  discovery: '问题探索', planning: '产品规划', learning: '学习改进',
};

function empty(value: unknown) {
  return value == null || value === '' || (Array.isArray(value) && value.length === 0)
    || (typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0);
}

function readableKey(key: string) {
  return LABELS[key] || key.replace(/_/g, ' ');
}

function Value({ value }: { value: unknown }) {
  if (empty(value)) return <span className="text-ink-ghost">尚未形成</span>;
  if (typeof value === 'string') {
    if (STAGE_NAMES[value]) return <span>{STAGE_NAMES[value]}</span>;
    const trimmed = value.trim();
    if ((trimmed.startsWith('{') || trimmed.startsWith('['))) {
      try { return <Value value={JSON.parse(trimmed)} />; } catch { /* render markdown */ }
    }
    return <ReactMarkdown remarkPlugins={[remarkGfm]} className="markdown-body">{value}</ReactMarkdown>;
  }
  if (typeof value !== 'object') return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={String((item as Row)?.id || index)} className="border-l-2 border-l-accent pl-3 py-1">
            <Value value={item} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {Object.entries(value as Row).filter(([key, item]) => !key.endsWith('_id') && !['id', 'user_id', 'created_at', 'updated_at'].includes(key) && !empty(item)).map(([key, item]) => (
        <div key={key} className="min-w-0">
          <div className="text-xs font-medium text-ink-faint mb-1">{readableKey(key)}</div>
          <div className="text-sm text-ink-soft"><Value value={item} /></div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, description, value }: { title: string; description?: string; value: unknown }) {
  return (
    <section className="panel p-4">
      <h3 className="font-hand text-xl text-ink">{title}</h3>
      {description && <p className="text-xs text-ink-faint mt-1 mb-3">{description}</p>}
      <Value value={value} />
    </section>
  );
}

export function ProjectWorkspacePanel({ projectId, onClose }: Props) {
  const kyrozen = window.kyrozen!;
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('overview');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [decision, setDecision] = useState('');
  const [reason, setReason] = useState('');
  const [feedback, setFeedback] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    const result = await kyrozen.getProjectWorkspace(projectId);
    if (result.success && result.data) { setData(result.data as WorkspaceData); setNotice(''); }
    else setNotice(result.error || '项目画布加载失败');
    setLoading(false);
  }, [kyrozen, projectId]);

  useEffect(() => { void load(); }, [load]);

  const artifactsByType = useMemo(() => {
    const grouped: Record<string, Row[]> = {};
    for (const artifact of data?.artifacts || []) {
      const type = String(artifact.type || 'other');
      (grouped[type] ||= []).push(artifact);
    }
    return grouped;
  }, [data]);

  const saveDecision = async () => {
    if (!decision.trim()) return;
    const result = await kyrozen.createDecision(projectId, decision.trim(), reason.trim());
    setNotice(result.success ? '决策已保存' : result.error || '保存失败');
    if (result.success) { setDecision(''); setReason(''); await load(); }
  };

  const saveFeedback = async () => {
    if (!feedback.trim()) return;
    const result = await kyrozen.createFeedback(projectId, feedback.trim(), 'experience', 'medium');
    setNotice(result.success ? '用户反馈已记录' : result.error || '记录失败');
    if (result.success) { setFeedback(''); await load(); }
  };

  const exportProject = async () => {
    const result = await kyrozen.exportProject(projectId);
    if (!result.cancelled) setNotice(result.success ? `已导出到 ${result.filePath}` : result.error || '导出失败');
  };

  return (
    <div className="absolute inset-0 z-30 bg-paper flex flex-col" data-testid="project-workspace-panel">
      <header className="flex items-center justify-between px-5 py-3 border-b border-line bg-surface">
        <div>
          <h2 className="font-hand text-2xl leading-none">项目画布</h2>
          <p className="text-xs text-ink-faint mt-1">把项目从问题、方案到交付结果整理成可读的工作台</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void exportProject()} className="btn-secondary text-xs">导出</button>
          <button type="button" onClick={() => void load()} className="btn-secondary text-xs">刷新</button>
          <button type="button" onClick={onClose} className="btn-ghost text-xs">关闭</button>
        </div>
      </header>
      <div className="flex border-b border-line bg-paper-sink overflow-x-auto px-3">
        {TABS.map(([key, label]) => (
          <button key={key} type="button" onClick={() => setTab(key)} className={`px-3 py-2 text-xs whitespace-nowrap border-b-2 ${tab === key ? 'border-accent text-accent font-medium' : 'border-transparent text-ink-faint hover:text-ink'}`}>
            {label}
          </button>
        ))}
      </div>
      {notice && <div role="status" className="px-4 py-2 text-xs bg-accent-soft text-accent border-b border-line">{notice}</div>}
      <main className="flex-1 overflow-y-auto p-5">
        {loading || !data ? <div className="text-sm text-ink-faint">正在整理项目资料…</div> : (
          <div className="max-w-5xl mx-auto space-y-4">
            <div className="mb-2">
              <h3 className="font-hand text-2xl">{TABS.find(([key]) => key === tab)?.[1]}</h3>
              <p className="text-xs text-ink-faint">{TABS.find(([key]) => key === tab)?.[2]}</p>
            </div>

            {tab === 'overview' && (
              <>
                <Section title={String(data.project?.name || '项目概览')} value={{ description: data.project?.description, goal: data.project?.goal, current_stage: data.project?.current_stage }} />
                <div className="grid gap-4 md:grid-cols-3">
                  <Section title="当前状态" value={data.state} />
                  <Section title="已形成资料" value={`${data.artifacts?.length || 0} 份`} />
                  <Section title="执行任务" value={`${data.tasks?.length || 0} 个`} />
                </div>
                <Section title="最近任务" description="只展示用户需要关注的任务结果" value={(data.tasks || []).slice(0, 5).map((item) => ({ title: item.title, status: item.status, result: (item.result as Row)?.answer }))} />
              </>
            )}
            {tab === 'problem' && (
              <>
                <Section title="问题定义" value={data.sections?.discovery} />
                <Section title="市场与竞品" value={data.sections?.research} />
                <Section title="研究资料" value={[...(artifactsByType.problem_brief || []), ...(artifactsByType.market_research_report || [])]} />
              </>
            )}
            {tab === 'product' && (
              <>
                <Section title="产品规划" value={data.sections?.planning} />
                <Section title="产品资料" value={(data.artifacts || []).filter((item) => /product|prd|architecture|solution/i.test(String(item.type || '') + String(item.title || '')))} />
              </>
            )}
            {tab === 'build' && (
              <div className="grid gap-4 md:grid-cols-2">
                <Section title="软件开发" value={data.sections?.development} />
                <Section title="硬件与采购" value={data.sections?.hardware} />
              </div>
            )}
            {tab === 'validation' && (
              <>
                <div className="panel p-4 space-y-3">
                  <h3 className="font-hand text-xl">记录真实用户反馈</h3>
                  <textarea className="input" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="用户完成了什么、遇到什么问题、是否愿意继续使用？" rows={3} />
                  <button type="button" onClick={() => void saveFeedback()} disabled={!feedback.trim()} className="btn-primary text-sm">保存反馈</button>
                </div>
                <Section title="测试结果" value={data.sections?.testing} />
              </>
            )}
            {tab === 'learning' && (
              <>
                <Section title="项目学习" value={data.sections?.learning} />
                <Section title="改进建议" value={data.sections?.improvement} />
              </>
            )}
            {tab === 'decisions' && (
              <>
                <div className="panel p-4 space-y-3">
                  <h3 className="font-hand text-xl">记录项目决策</h3>
                  <input className="input" value={decision} onChange={(event) => setDecision(event.target.value)} placeholder="做出了什么决定？" />
                  <textarea className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="为什么这样决定？依据和取舍是什么？" rows={2} />
                  <button type="button" onClick={() => void saveDecision()} disabled={!decision.trim()} className="btn-primary text-sm">保存决策</button>
                </div>
                <Section title="决策记录" value={data.decisions} />
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
