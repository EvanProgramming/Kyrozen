import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { StageGateStatus, SoftwareFeatureResult, SoftwareRunResult, AttachmentInfo, OperationLogEntry, InteractionStatus } from '../types/global';

type OperationStatus = 'pending' | 'running' | 'failed' | 'completed';

interface Operation {
  description: string;
  status: string;
  timestamp: string;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  operations?: Operation[];
  /** Do not render this message (e.g. option answers shown as highlighted chips instead). */
  hidden?: boolean;
  /** For assistant question cards: the option.value the user picked. */
  selectedOption?: string;
}

interface PlanStep {
  label: string;
  status: OperationStatus;
}

interface ExecutionPlan {
  task_id: string;
  steps: PlanStep[];
}

interface ConfirmationRequest {
  confirmation_id: string;
  store_id?: string | null;
  task_id: string;
  tool: string;
  action: string;
  parameters: Record<string, unknown>;
  reason: string;
  detail: string;
}

interface RoutedAgent {
  task_id: string;
  mode: string;
  mode_label: string;
  agent_name: string;
  agent_display_name: string;
  reason: string;
  available_tools: string[];
  restricted_tools: string[];
  degraded: boolean;
}

interface DegradedInfo {
  task_id: string;
  agent_display_name: string;
  reason: string;
  repair_steps: string[];
}

interface QuestionOption { label: string; value: string }
interface QuestionCard { question: string; options: QuestionOption[]; allow_other?: boolean }

interface ChatPageProps {
  projectId: string | null;
  onOpenPreview?: (url: string) => void;
  onProjectChanged?: () => void;
}

const QUESTION_BLOCK_RE = /```kyrozen-question\s*\n([\s\S]*?)```/i;

function splitQuestionBlock(content: string): { markdown: string; question: QuestionCard | null } {
  const match = content.match(QUESTION_BLOCK_RE);
  if (!match) return { markdown: content, question: null };
  try {
    const parsed = JSON.parse(match[1]) as QuestionCard;
    if (!parsed.question || !Array.isArray(parsed.options)) throw new Error('invalid question');
    return { markdown: content.replace(match[0], '').trim(), question: parsed };
  } catch {
    return { markdown: content, question: null };
  }
}

/**
 * When restoring history, a user message that is simply the answer to the
 * preceding question card (matching an option label or value) should not
 * appear as a chat bubble — instead the picked option is highlighted on the
 * question card itself. Mutates and returns the given array.
 */
function reconcileQuestionAnswers(messages: Message[]): Message[] {
  for (let i = 1; i < messages.length; i++) {
    const current = messages[i];
    const previous = messages[i - 1];
    if (current.role !== 'user' || previous.role !== 'assistant') continue;
    const question = splitQuestionBlock(previous.content).question;
    if (!question) continue;
    const answer = current.content.trim();
    const match = question.options.find((option) => option.label === answer || option.value === answer);
    if (match) {
      previous.selectedOption = match.value;
      current.hidden = true;
    }
  }
  return messages;
}

// P0-15: never surface raw backend JSON (task IDs, exception text) to a normal
// user. Map known failure shapes to a friendly summary and keep the technical
// detail in a collapsible diagnostic block.
function friendlyChatError(raw?: string): { summary: string; raw: string } {
  const text = (raw || '未知错误').trim();
  let detail = text;
  try {
    const obj = JSON.parse(text);
    if (obj && typeof obj === 'object' && obj.detail) detail = String(obj.detail);
  } catch {
    /* not JSON; use as-is */
  }
  if (/persist task|failed to persist/i.test(detail)) {
    return { summary: '消息暂时无法保存，请稍后重试；若持续出现请联系支持。', raw: text };
  }
  if (/ECONNREFUSED|ETIMEDOUT|timeout|network/i.test(detail)) {
    return { summary: '网络连接异常，请检查网络后重试。', raw: text };
  }
  if (/模型|model|provider|authentication|api key|no response/i.test(detail)) {
    return { summary: 'AI 服务暂时不可用，请稍后重试。', raw: text };
  }
  if (/401|unauthorized|未登录|not logged|no longer logged/i.test(detail)) {
    return { summary: '登录已失效，请重新登录后重试。', raw: text };
  }
  const short = detail.length > 80 ? `${detail.slice(0, 80)}…` : detail;
  return { summary: `发送失败：${short}`, raw: text };
}

function Markdown({ content, onOpenPreview }: { content: string; onOpenPreview?: (url: string) => void }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className="markdown-body"
      components={{
        a: ({ href, children }) => {
          const url = href || '';
          const local = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(url);
          return (
            <a
              href={url}
              onClick={(event) => {
                event.preventDefault();
                if (local && onOpenPreview) onOpenPreview(url);
                else window.open(url, '_blank', 'noopener,noreferrer');
              }}
            >
              {children}
            </a>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function readDroppedFile(file: File): Promise<{ name: string; content: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, content: String(reader.result || '') });
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.readAsText(file);
  });
}

const dotClass: Record<OperationStatus, string> = {
  pending: 'border border-line-strong bg-surface',
  running: 'bg-accent',
  failed: 'bg-danger',
  completed: 'bg-success',
};

// 九种路由模式的单色图标（统一使用 --accent，不引入第二套强调色）。
// 图标仅用 currentColor 描边，颜色由父级 className 控制（正常=深蓝，降级=危险红）。
const AGENT_MODE_ICONS: Record<string, ReactNode> = {
  problem_discovery: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <line x1="15" y1="15" x2="20" y2="20" />
    </>
  ),
  market_research: (
    <>
      <line x1="4" y1="20" x2="20" y2="20" />
      <rect x="5" y="11" width="3.5" height="9" />
      <rect x="10.25" y="6" width="3.5" height="14" />
      <rect x="15.5" y="14" width="3.5" height="6" />
    </>
  ),
  product_definition: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
      <circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none" />
    </>
  ),
  solution_design: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 12 L15.5 8.5" />
      <path d="M12 12 L8.5 15.5" />
    </>
  ),
  development: (
    <>
      <path d="M9 8 L5 12 L9 16" />
      <path d="M15 8 L19 12 L15 16" />
      <line x1="13" y1="6" x2="11" y2="18" />
    </>
  ),
  hardware_development: (
    <>
      <rect x="7" y="7" width="10" height="10" rx="1" />
      <path d="M10 7 V4 M14 7 V4 M10 20 V17 M14 20 V17 M7 10 H4 M7 14 H4 M20 10 H17 M20 14 H17" />
    </>
  ),
  testing: (
    <>
      <path d="M9 3 H15" />
      <path d="M10 3 V11 L5.5 18 a1 1 0 0 0 .9 1.5 H17.6 a1 1 0 0 0 .9 -1.5 L14 11 V3" />
      <line x1="8.5" y1="15" x2="15.5" y2="15" />
    </>
  ),
  iteration: (
    <>
      <path d="M5 12 A7 7 0 0 1 18 8" />
      <path d="M18 4 V8 H14" />
      <path d="M19 12 A7 7 0 0 1 6 16" />
      <path d="M6 20 V16 H10" />
    </>
  ),
  learning: (
    <>
      <path d="M12 6 C10 4 6 4 4 5 V19 C6 18 10 18 12 20 C14 18 18 18 20 19 V5 C18 4 14 4 12 6 Z" />
      <line x1="12" y1="6" x2="12" y2="20" />
    </>
  ),
};

// 九种模式的专属提示语（行内辅助说明，遵循设计系统：功能色仅表语义、单强调色）。
const AGENT_MODE_HINTS: Record<string, string> = {
  problem_discovery: '厘清真问题，界定范围与目标。',
  market_research: '收集市场、用户与竞品情报。',
  product_definition: '明确要做什么、为谁做、价值何在。',
  solution_design: '评估可行方案并权衡取舍。',
  development: '编写与运行软件代码。',
  hardware_development: '固件、电路与硬件集成。',
  testing: '设计用例、执行测试并验收。',
  iteration: '在已有成果上持续打磨改进。',
  learning: '总结经验、沉淀可复用知识。',
};

function AgentModeIcon({ mode, className }: { mode: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {AGENT_MODE_ICONS[mode] ?? AGENT_MODE_ICONS.problem_discovery}
    </svg>
  );
}

/** Small check / alert glyph for stage-gate conditions (single accent color). */
function ConditionIcon({ satisfied, className }: { satisfied: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
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

type StageAction = 'refresh' | 'advance_normal' | 'advance_risk' | 'return';
type RiskDetails = { reason: string; impact: string; recovery: string };

function StageGatePanel({
  status,
  busy,
  onAction,
}: {
  status: StageGateStatus;
  busy: boolean;
  onAction: (action: StageAction, riskDetails?: RiskDetails) => void;
}) {
  const { gate } = status;
  const kindLabel: Record<string, string> = {
    deliverable: '交付物',
    confirmation: '确认',
    verification: '验证',
    task: '任务',
  };
  const [open, setOpen] = useState(true);
  const [riskOpen, setRiskOpen] = useState(false);
  const [riskDetails, setRiskDetails] = useState<RiskDetails>({ reason: '', impact: '', recovery: '' });
  return (
    <div className="bg-surface border-b border-line">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full px-4 py-2 flex items-center justify-between text-left"
      >
        <span className="flex items-center gap-2">
          <span className="font-display text-lg text-ink">阶段门禁 · {gate.stage_label}</span>
          <span className="text-xs text-ink-faint">{gate.index + 1}/{gate.total}</span>
        </span>
        <span className="flex items-center gap-3">
          <span className="text-xs tabular-nums text-ink-soft">{status.progress}%</span>
          <span className="text-xs text-ink-faint">{open ? '收起' : '展开'}</span>
        </span>
      </button>
      {/* Progress is computed from real signals, always visible. */}
      <div className="px-4 pb-2">
        <div className="h-1.5 w-full bg-paper-sink rounded-sm overflow-hidden">
          <div className="h-full bg-accent transition-all" style={{ width: `${status.progress}%` }} />
        </div>
      </div>
      {open && (
      <div className="px-4 pb-3 space-y-3">
        {gate.blocked_entry_reason && (
          <div className="panel p-3 border-l-2 border-l-danger bg-danger-soft">
            <div className="text-sm text-danger">{gate.blocked_entry_reason}</div>
          </div>
        )}
        {gate.failed_tasks.length > 0 && (
          <div className="panel p-3 border-l-2 border-l-danger bg-danger-soft space-y-1.5">
            <div className="text-sm text-danger font-medium">存在失败任务，需先修复</div>
            {gate.failed_tasks.map((task) => (
              <div key={task.task_id} className="text-xs text-ink-soft">
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
              <div key={condition.item_id} className="flex items-start gap-2 text-sm text-ink-soft">
                <ConditionIcon satisfied={false} className="w-4 h-4 flex-shrink-0 text-danger mt-0.5" />
                <div className="flex-1">
                  <span>{condition.label}</span>
                  <span className="ml-1 text-xs text-ink-faint">[{kindLabel[condition.kind] ?? condition.kind}]</span>
                  {condition.detail && <span className="text-xs text-ink-faint"> · {condition.detail}</span>}
                  {condition.skippable && <span className="ml-1 text-xs text-ink-faint">（可跳过）</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        {gate.satisfied.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-accent">已满足（{gate.satisfied.length}）</div>
            {gate.satisfied.map((condition) => (
              <div key={condition.item_id} className="flex items-start gap-2 text-sm text-ink-soft">
                <ConditionIcon satisfied={condition.satisfied} className="w-4 h-4 flex-shrink-0 text-accent mt-0.5" />
                <div className="flex-1">
                  <span>{condition.label}</span>
                  <span className="ml-1 text-xs text-ink-faint">[{kindLabel[condition.kind] ?? condition.kind}]</span>
                  {condition.detail && <span className="text-xs text-ink-faint"> · {condition.detail}</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            disabled={!gate.can_advance || busy}
            onClick={() => onAction('advance_normal')}
            className="btn-primary text-xs"
            title={gate.can_advance ? '当前阶段条件已满足，进入下一阶段' : '当前阶段仍有未满足条件'}
          >
            进入下一阶段
          </button>
          <button
            type="button"
            disabled={busy || gate.missing.some((condition) => !condition.skippable)}
            onClick={() => setRiskOpen((value) => !value)}
            className="btn-secondary text-xs"
            title="跳过未满足的必需条件并进入下一阶段（会记录风险）"
          >
            带风险推进
          </button>
          <button
            type="button"
            disabled={busy || gate.index === 0}
            onClick={() => onAction('return')}
            className="btn-ghost text-xs"
          >
            返回上一阶段
          </button>
        </div>

        {riskOpen && (
          <div className="panel p-3 border-l-2 border-l-warning bg-warning-soft space-y-2">
            <div className="text-sm font-medium text-ink">说明为什么需要带风险推进</div>
            <input className="input text-xs w-full" value={riskDetails.reason} onChange={(event) => setRiskDetails((value) => ({ ...value, reason: event.target.value }))} placeholder="具体原因（必填）" />
            <input className="input text-xs w-full" value={riskDetails.impact} onChange={(event) => setRiskDetails((value) => ({ ...value, impact: event.target.value }))} placeholder="可能影响" />
            <input className="input text-xs w-full" value={riskDetails.recovery} onChange={(event) => setRiskDetails((value) => ({ ...value, recovery: event.target.value }))} placeholder="后续补救办法" />
            <div className="flex gap-2">
              <button type="button" className="btn-primary text-xs" disabled={!riskDetails.reason.trim() || busy} onClick={() => { onAction('advance_risk', riskDetails); setRiskOpen(false); }}>确认并记录风险</button>
              <button type="button" className="btn-ghost text-xs" onClick={() => setRiskOpen(false)}>取消</button>
            </div>
          </div>
        )}

        {status.skips.length > 0 && (
          <div className="text-xs text-ink-faint pt-1">
            已带风险跳过 {status.skips.length} 项：
            {status.skips.map((skip) => skip.item_id).join('、')}
          </div>
        )}
      </div>
      )}
    </div>
  );
}

// Feature 3.3: real software generation / run / repair panel. Talks to the
// deterministic SoftwareFeatureTool in the desktop Python Agent (no LLM needed).
const WEB_APP_SET = new Set(['web_app', 'website', 'simple_saas', 'ai_tool', 'desktop_app']);
const APP_TYPE_LABELS: Record<string, string> = {
  web_app: 'Web 应用',
  website: '官网/落地页',
  simple_saas: '轻量 SaaS',
  ai_tool: 'AI 工具',
  automation_tool: '自动化工具',
  desktop_app: '桌面应用',
  cli_tool: '命令行工具',
};
const DELIVERABLE_LABELS: Record<string, string> = {
  research_report: '调研报告',
  content_plan: '内容计划',
  ops_plan: '运营方案',
  business_process: '业务流程',
};

function SoftwareFeaturePanel({
  projectId,
  onOpenPreview,
  agentReady,
  stageStatus,
}: {
  projectId: string | null;
  onOpenPreview?: (url: string) => void;
  agentReady: { status: string; version?: string; mode?: string; reason?: string } | null;
  stageStatus: StageGateStatus | null;
}) {
  const [feature, setFeature] = useState<SoftwareFeatureResult | null>(null);
  const [appType, setAppType] = useState<string>('web_app');
  const [busy, setBusy] = useState(false);
  const busyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [error, setError] = useState<string | null>(null);
  // P0-R9: do NOT expand the software-generation form during problem discovery
  // or market research. It is disabled there and should not dominate the flow.
  const earlyStage = stageStatus?.stage === 'problem_discovery' || stageStatus?.stage === 'market_research';
  const [open, setOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  useEffect(() => {
    if (earlyStage && open) setOpen(false);
    if (earlyStage && formOpen) setFormOpen(false);
  }, [earlyStage, open, formOpen]);
  const [copied, setCopied] = useState(false);

  // P0-07: the development entry must be gated by the stage gate. Code may only
  // be generated once the gate for entering development is satisfied (or we are
  // already in the development stage). Otherwise we surface the reason and a
  // "return to current stage" hint instead of letting the user skip the lifecycle.
  const agentDown = agentReady != null && agentReady.status !== 'ready';
  const gate = stageStatus?.gate;
  // P0-07: 软件生成入口必须受门禁约束。仅当 stage 确认为 development
  // 或 gate.can_advance 为 true 时才开放。stageStatus 为 null（加载中）视为阻塞。
  const canGenerate =
    stageStatus != null && stageStatus.stage === 'development' && !gate?.blocked_entry_reason;
  const generateBlockReason = canGenerate
    ? null
    : (gate?.blocked_entry_reason || '请先完成当前阶段门禁（问题界定、调研、PRD、方案确认）后再生成代码。');

  // Generate form state.
  const [appName, setAppName] = useState('我的 Web 应用');
  const [genType, setGenType] = useState('web_app');
  const [featuresText, setFeaturesText] = useState('用户登录\n数据看板\n导出报表');
  const [desc, setDesc] = useState('');

  // Non-coding deliverable form state.
  const [deliverableType, setDeliverableType] = useState('research_report');
  const [deliverableTitle, setDeliverableTitle] = useState('竞品调研报告');
  const [deliverableFields, setDeliverableFields] = useState('背景: 行业现状与规模\n目标: 找出 3 个差异化切入点\n结论: 建议优先切入方向');

  useEffect(() => {
    setFeature(null);
    setError(null);
    setBusy(false);
    if (!projectId) return;
    const raw = localStorage.getItem(`kyrozen:software-draft:${projectId}`);
    if (!raw) return;
    try {
      const draft = JSON.parse(raw) as Record<string, string>;
      setAppName(draft.appName || '我的 Web 应用');
      setGenType(draft.genType || 'web_app');
      setFeaturesText(draft.featuresText || '用户登录\n数据看板\n导出报表');
      setDesc(draft.desc || '');
      setDeliverableType(draft.deliverableType || 'research_report');
      setDeliverableTitle(draft.deliverableTitle || '竞品调研报告');
      setDeliverableFields(draft.deliverableFields || '背景: 行业现状与规模\n目标: 找出 3 个差异化切入点\n结论: 建议优先切入方向');
    } catch { /* ignore a corrupt local draft */ }
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    localStorage.setItem(`kyrozen:software-draft:${projectId}`, JSON.stringify({ appName, genType, featuresText, desc, deliverableType, deliverableTitle, deliverableFields }));
  }, [projectId, appName, genType, featuresText, desc, deliverableType, deliverableTitle, deliverableFields]);

  useEffect(() => {
    if (!window.kyrozen) return;
    const unsub = window.kyrozen.onSoftwareFeature((result) => {
      if (busyTimerRef.current) { clearTimeout(busyTimerRef.current); busyTimerRef.current = null; }
      setFeature(result);
      if (result.app_type) setAppType(result.app_type);
      setBusy(false);
      setError(null);
    });
    return unsub;
  }, []);

  const send = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!window.kyrozen || !projectId) return;
    if (agentDown) {
      setError('本地 Agent 当前不可用，无法生成或运行软件。请检查 Python 运行环境后重试。');
      return;
    }
    setError(null);
    setBusy(true);
    busyTimerRef.current = setTimeout(() => {
      busyTimerRef.current = null;
      setBusy(false);
      setError('操作超时：本地 Agent 未在预期时间内响应，请重试或检查运行环境。');
    }, 60000);
    try {
      const { workspaceRoot } = await window.kyrozen.getWorkspaceRoot(projectId);
      window.kyrozen.sendSoftwareFeature({ action, workspace_root: workspaceRoot, project_id: projectId, ...extra });
    } catch {
      if (busyTimerRef.current) { clearTimeout(busyTimerRef.current); busyTimerRef.current = null; }
      setBusy(false);
      setError('无法发送软件生成请求，请重试。');
    }
  };

  useEffect(() => {
    if (!window.kyrozen || !projectId || agentReady?.status !== 'ready') return;
    void window.kyrozen.getWorkspaceRoot(projectId).then(({ workspaceRoot }) => {
      window.kyrozen?.sendSoftwareFeature({ action: 'load', workspace_root: workspaceRoot, project_id: projectId });
    });
  }, [projectId, agentReady?.status]);

  const copyCommand = async () => {
    const cmd = feature?.command || (WEB_APP_SET.has(feature?.app_type ?? appType) ? 'python app.py' : 'python main.py');
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable in some contexts; ignore.
    }
  };

  const handleGenerate = () => {
    const features = featuresText.split('\n').map((line) => line.trim()).filter(Boolean);
    send('generate', {
      app_type: genType,
      app_name: appName.trim() || 'kyrozen-app',
      description: desc.trim(),
      prd: { features, name: appName.trim() || 'kyrozen-app', description: desc.trim() },
    });
  };

  const handleNoncoding = () => {
    const fields: Record<string, string> = {};
    deliverableFields.split('\n').forEach((line) => {
      const idx = line.indexOf(':');
      if (idx > 0) fields[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    });
    send('noncoding', {
      deliverable_type: deliverableType,
      title: deliverableTitle.trim() || '未命名交付物',
      fields,
    });
  };

  const activeType = feature?.app_type ?? appType;
  const isWeb = WEB_APP_SET.has(activeType);
  const previewUrl = feature?.preview_url || '';
  const runCommand = feature?.command || (isWeb ? 'python app.py' : 'python main.py');
  const artifactPath = feature?.artifact_path || '';

  return (
    <div className="bg-surface border-b border-line">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full px-4 py-2 flex items-center justify-between text-left"
      >
        <span className="flex items-center gap-2">
          <span className="font-display text-lg text-ink">软件生成</span>
          <span className="text-xs text-ink-faint">真实生成 · 运行 · 修复</span>
        </span>
        <span className="text-xs text-ink-faint">{open ? '收起' : '展开'}</span>
      </button>

      {open && (
        <div className="px-4 pb-3 space-y-3">
          {!projectId && (
            <div className="text-xs text-ink-faint">请先选择左侧项目后再生成软件。</div>
          )}

          {generateBlockReason && (
            <div className="panel p-3 border-l-2 border-l-danger bg-danger-soft space-y-1">
              <div className="text-sm text-danger font-medium">开发入口暂未开放</div>
              <div className="text-xs text-ink-soft">{generateBlockReason}</div>
              {stageStatus && (
                <button type="button" onClick={() => void send('return')} className="btn-ghost text-xs mt-1">
                  返回当前阶段
                </button>
              )}
            </div>
          )}

          {error && (
            <div className="panel p-3 border-l-2 border-l-danger bg-danger-soft">
              <div className="text-sm text-danger">{error}</div>
            </div>
          )}

          {feature && (
            <div className="panel p-3 border-l-2 border-l-accent bg-accent-soft space-y-2">
              {feature.action === 'generate' && (
                <div className="space-y-1.5">
                  <div className="text-sm text-ink font-medium">
                    已生成 {APP_TYPE_LABELS[feature.app_type || ''] || feature.app_type} 原型
                  </div>
                  <div className="text-xs text-ink-soft">
                    写入文件 {feature.files?.length ?? 0} 个 · 功能 {feature.feature_slugs?.length ?? 0} 项
                    {feature.files?.includes('README.md') ? ' · README.md 已生成' : ' · 缺少 README.md'}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(feature.files || []).map((file) => (
                      <span key={file} className="text-xs bg-surface border border-line rounded-sm px-2 py-0.5 text-ink-soft font-mono">
                        {file}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {feature.action === 'run' && feature.run && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-sm ${feature.run.overall_success ? 'bg-accent text-white' : 'bg-danger text-white'}`}>
                      {feature.run.overall_success ? '运行 / 测试通过' : '运行 / 测试未通过'}
                    </span>
                    <span className="text-xs text-ink-faint">
                      安装 {tick(feature.run.install)} · 构建 {tick(feature.run.build)} · 测试 {tick(feature.run.test)} · 核心流程 {tick(feature.run.core_flow)}
                    </span>
                  </div>

                  {isWeb && previewUrl && (
                    <div>
                      <button type="button" onClick={() => onOpenPreview?.(previewUrl)} className="btn-primary text-xs">
                        打开可点击预览 {previewUrl}
                      </button>
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ink-faint">启动命令</span>
                    <code className="text-xs bg-paper-sink border border-line rounded-sm px-2 py-1 text-ink-soft font-mono flex-1 truncate">{runCommand}</code>
                    <button type="button" onClick={() => void copyCommand()} className="btn-ghost text-xs">{copied ? '已复制' : '复制'}</button>
                  </div>

                  {artifactPath && (
                    <div className="text-xs text-ink-faint">
                      交付物路径：<span className="font-mono text-ink-soft">{artifactPath}</span>
                    </div>
                  )}

                  {feature.feature_records && feature.feature_records.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-xs font-medium text-ink-soft">功能实现记录</div>
                      {feature.feature_records.map((record, index) => (
                        <div key={index} className="flex items-center gap-2 text-xs text-ink-soft">
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${record.status === 'tested' ? 'bg-accent' : 'bg-danger'}`} />
                          <span className="flex-1">{record.prd_feature}</span>
                          <span className={record.status === 'tested' ? 'text-accent' : 'text-danger'}>{record.status === 'tested' ? '已验证' : '未通过'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {feature.action === 'repair' && feature.repair && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-sm ${feature.repair.success ? 'bg-accent text-white' : 'bg-danger text-white'}`}>
                      {feature.repair.success ? '自动修复成功' : '修复未成功'}
                    </span>
                    <span className="text-xs text-ink-faint">尝试 {feature.repair.attempts} 次</span>
                  </div>
                  {feature.repair.repairs.map((step, index) => (
                    <div key={index} className="panel p-2 border-l-2 border-l-accent bg-surface space-y-0.5">
                      <div className="text-xs text-ink-soft font-medium">{step.file}</div>
                      <div className="text-xs text-danger">{step.error_summary}</div>
                      <div className="text-xs text-accent">修复：{step.fix_applied}</div>
                    </div>
                  ))}
                </div>
              )}

              {feature.action === 'noncoding' && (
                <div className="space-y-1.5">
                  <div className="text-sm text-ink font-medium">
                    {DELIVERABLE_LABELS[feature.deliverable_type || ''] || feature.deliverable_type} · {feature.title}
                  </div>
                  <div className="text-xs text-ink-faint">已保存：{feature.file}</div>
                  <div className="max-h-48 overflow-auto bg-paper-sink border border-line rounded-sm p-3 text-xs text-ink-soft">
                    <Markdown content={feature.markdown || ''} onOpenPreview={onOpenPreview} />
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {feature && (
              <button type="button" disabled={busy || !projectId} onClick={() => void send('run')} className="btn-primary text-xs">
                {busy ? '执行中…' : '运行 / 测试'}
              </button>
            )}
            {feature && (
              <button type="button" disabled={busy || !projectId} onClick={() => void send('repair')} className="btn-secondary text-xs">
                自动修复
              </button>
            )}
            <button type="button" onClick={() => setFormOpen((value) => !value)} className="btn-ghost text-xs">
              {formOpen ? '收起生成表单' : '新建应用 / 交付物'}
            </button>
          </div>

          {formOpen && (
            <div className="space-y-3 border-t border-line pt-3">
              <div className="space-y-2">
                <div className="text-xs font-medium text-ink-soft">生成可运行软件</div>
                <div className="flex flex-wrap gap-2">
                  <input value={appName} onChange={(event) => setAppName(event.target.value)} placeholder="应用名称" className="input text-xs flex-1 min-w-[140px]" />
                  <select value={genType} onChange={(event) => setGenType(event.target.value)} className="input text-xs">
                    {Object.entries(APP_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <textarea
                  value={featuresText}
                  onChange={(event) => setFeaturesText(event.target.value)}
                  placeholder="每个功能一行"
                  rows={3}
                  className="input text-xs w-full font-mono"
                />
                <input value={desc} onChange={(event) => setDesc(event.target.value)} placeholder="一句话描述（可选）" className="input text-xs w-full" />
                <button type="button" disabled={busy || !projectId || !canGenerate} onClick={handleGenerate} className="btn-primary text-xs" title={canGenerate ? '生成并写入可运行软件到工作区' : generateBlockReason ?? undefined}>
                  生成并写入工作区
                </button>
              </div>

              <div className="space-y-2 border-t border-line pt-2">
                <div className="text-xs font-medium text-ink-soft">非代码交付物</div>
                <div className="flex flex-wrap gap-2">
                  <input value={deliverableTitle} onChange={(event) => setDeliverableTitle(event.target.value)} placeholder="交付物标题" className="input text-xs flex-1 min-w-[140px]" />
                  <select value={deliverableType} onChange={(event) => setDeliverableType(event.target.value)} className="input text-xs">
                    {Object.entries(DELIVERABLE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <textarea
                  value={deliverableFields}
                  onChange={(event) => setDeliverableFields(event.target.value)}
                  placeholder="字段用「键: 值」逐行填写"
                  rows={3}
                  className="input text-xs w-full font-mono"
                />
                <button type="button" disabled={busy || !projectId} onClick={handleNoncoding} className="btn-secondary text-xs">
                  生成交付物
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function tick(result: SoftwareRunResult | null): string {
  if (!result) return '—';
  return result.exit_code === 0 ? '✓' : '✗';
}

// Feature 3.4: attachments, status bar, operation log, confirmations.
const STATUS_LABEL: Record<string, string> = {
  reading: '读取中',
  editing: '编辑中',
  running: '运行中',
  searching: '搜索中',
  waiting: '等待中',
  retrying: '重试中',
};

function InteractionPanel({
  projectId,
  agentReady,
}: {
  projectId: string | null;
  agentReady: { status: string; version?: string; mode?: string; reason?: string } | null;
}) {
  const [status, setStatus] = useState<InteractionStatus | null>(null);
  const [attachments, setAttachments] = useState<AttachmentInfo[]>([]);
  const [records, setRecords] = useState<OperationLogEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [attOpen, setAttOpen] = useState(true);
  const [opOpen, setOpOpen] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const agentDown = agentReady != null && agentReady.status !== 'ready';

  const send = async (extra: Record<string, unknown>) => {
    if (!window.kyrozen || !projectId) return;
    const { workspaceRoot } = await window.kyrozen.getWorkspaceRoot(projectId);
    window.kyrozen.sendInteraction({ ...extra, workspace_root: workspaceRoot });
  };

  useEffect(() => {
    if (!window.kyrozen) return;
    const unsubStatus = window.kyrozen.onStatusUpdated((s) => setStatus(s));
    const unsubInt = window.kyrozen.onInteraction((payload) => {
      const action = String(payload.action || '');
      if (action === 'attach') {
        if (uploadTimerRef.current) { clearTimeout(uploadTimerRef.current); uploadTimerRef.current = null; }
        if (payload.error) {
          setUploadError(String(payload.error));
        } else if (payload.attachment) {
          const att = payload.attachment as AttachmentInfo;
          setAttachments((prev) => [...prev.filter((a) => a.id !== att.id), att]);
          setUploadError(null);
        }
        setUploading(false);
      } else if (action === 'delete_attachment') {
        // Refresh the list from disk so deletes always reflect.
        void send({ action: 'attach_list' });
      } else if (action === 'attach_list') {
        setAttachments((payload.attachments as AttachmentInfo[]) ?? []);
      } else if (action === 'op_list') {
        setRecords((payload.records as OperationLogEntry[]) ?? []);
      }
    });
    if (projectId && agentReady?.status === 'ready') {
      void send({ action: 'attach_list' });
      void send({ action: 'op_list' });
    }
    return () => {
      unsubStatus();
      unsubInt();
    };
  }, [projectId, agentReady?.status]);

  const onPick = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    // P0-04: fail fast (don't hang) when the Agent is known to be down.
    if (agentDown) {
      setUploadError('本地 Agent 当前不可用，无法处理附件。请检查 Python 运行环境后重试。');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setUploading(true);
    setUploadError(null);
    // Reset uploading after a timeout so the button never stays "上传中…".
    uploadTimerRef.current = setTimeout(() => {
      uploadTimerRef.current = null;
      setUploading(false);
      setUploadError('附件处理超时，请重试或检查本地 Agent 状态。');
    }, 60000);
    for (const file of files) {
      // Electron exposes the real on-disk path on the File object.
      const filePath = (file as unknown as { path?: string }).path || file.name;
      await send({ action: 'attach', path: filePath });
    }
    if (fileRef.current) fileRef.current.value = '';
  };

  const onDelete = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
    void send({ action: 'delete_attachment', attachment_id: id });
  };

  const statusText = status?.state ? (STATUS_LABEL[status.state] ?? status.state) : '就绪';

  return (
    <div className="bg-surface border-b border-line">
      <div className="flex items-center justify-between px-4 py-2">
        <button type="button" onClick={() => { setAttOpen((v) => !v); setOpOpen((v) => !v); }} className="flex items-center gap-2">
          <span className="font-display text-lg text-ink">附件 · 状态 · 操作</span>
        </button>
        <span className={`inline-flex items-center gap-1.5 rounded-sm border border-line-strong px-2 py-0.5 text-xs ${status?.state ? 'text-accent' : 'text-ink-faint'}`}>
          <span className={`w-2 h-2 rounded-full ${status?.state ? 'bg-accent' : 'bg-ink-faint'}`} />
          {statusText}
        </span>
      </div>

      {attOpen && (
        <div className="px-4 pb-3 space-y-2">
          <div className="flex items-center gap-2">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime" multiple className="hidden" onChange={onPick} />
            <button type="button" disabled={uploading || !projectId} onClick={() => fileRef.current?.click()} className="btn-secondary text-xs">
              {uploading ? '上传中…' : '添加附件'}
            </button>
            {uploadError && <span className="text-xs text-danger">{uploadError}</span>}
          </div>

          {attachments.length === 0 && !uploading && (
            <div className="text-xs text-ink-faint">暂无附件。支持 PNG/JPEG/WebP/MP4/MOV，将生成缩略图与视觉分析。</div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {attachments.map((att) => (
              <div key={att.id} className="panel p-2 border-l-2 border-l-accent bg-paper-sink space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-ink truncate">{att.filename}</div>
                    <div className="text-[11px] text-ink-faint">{att.kind} · {(att.size_bytes / 1024).toFixed(1)} KB</div>
                  </div>
                  <button type="button" onClick={() => onDelete(att.id)} className="text-xs text-ink-faint hover:text-danger">删除</button>
                </div>
                {att.kind === 'image' && att.thumbnail_path && (
                  <img src={att.thumbnail_path} alt={att.filename} className="w-24 h-auto rounded-sm border border-line" />
                )}
                {att.kind === 'video' && (
                  <div className="space-y-1">
                    {att.thumbnail_path && <img src={att.thumbnail_path} alt={att.filename} className="w-24 h-auto rounded-sm border border-line" />}
                    {Array.isArray(att.analysis?.keyframes) && (att.analysis?.keyframes as Array<{ timestamp: number; path: string }>).length > 0 && (
                      <div className="flex gap-1 overflow-x-auto">
                        {(att.analysis?.keyframes as Array<{ timestamp: number; path: string }>).map((kf, i) => (
                          <div key={i} className="flex-shrink-0">
                            <img src={kf.path} alt={`关键帧 ${kf.timestamp}s`} className="w-12 h-9 object-cover rounded-sm border border-line" />
                            <div className="text-[10px] text-ink-faint text-center">{kf.timestamp}s</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {Boolean(att.analysis?.description) && <div className="text-xs text-ink-soft">{String(att.analysis?.description)}</div>}
                {Boolean(att.analysis?.summary) && <div className="text-xs text-ink-soft">{String(att.analysis?.summary)}</div>}
                {att.error && <div className="text-xs text-danger">{att.error}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {opOpen && (
        <div className="px-4 pb-3">
          <button type="button" onClick={() => setOpOpen((v) => !v)} className="text-xs text-ink-faint hover:text-accent">
            操作记录（{records.length}）{opOpen ? '收起' : '展开'}
          </button>
          {opOpen && records.length > 0 && (
            <div className="mt-2 max-h-48 overflow-auto bg-paper-sink border border-line rounded-sm p-2 space-y-1">
              {records.map((rec) => (
                <div key={rec.id} className="flex items-start gap-2 text-xs">
                  <span className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${rec.status === 'failed' ? 'bg-danger' : 'bg-accent'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-ink-soft truncate">{rec.input_summary || rec.action}</div>
                    {rec.error_reason && <div className="text-danger">{rec.error_reason}</div>}
                  </div>
                  <span className="text-ink-faint flex-shrink-0">
                    {rec.duration_ms != null ? `${rec.duration_ms}ms` : '…'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatPage({ projectId, onOpenPreview, onProjectChanged }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [activity, setActivity] = useState('');
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [planExpanded, setPlanExpanded] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Array<{ name: string; content: string }>>([]);
  const [expandedOperations, setExpandedOperations] = useState<Set<number>>(new Set());
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);
  const [routedAgent, setRoutedAgent] = useState<RoutedAgent | null>(null);
  const [degraded, setDegraded] = useState<DegradedInfo | null>(null);
  const [chatError, setChatError] = useState<{ summary: string; raw: string } | null>(null);
  const [stageStatus, setStageStatus] = useState<StageGateStatus | null>(null);
  const [stageBusy, setStageBusy] = useState(false);
  // P0-03/04/06: whether the bundled Python Agent is alive. null = unknown
  // (optimistic), 'down'/'degraded' means we must not hang on a dead Agent.
  const [agentReady, setAgentReady] = useState<{ status: string; version?: string; mode?: string; reason?: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Conversation UI is project-scoped. Never carry a user's messages,
    // execution plan, confirmation, or attachments into another project.
    setMessages([]);
    setInput('');
    setIsRunning(false);
    setActivity('');
    setPlan(null);
    setPendingAttachments([]);
    setExpandedOperations(new Set());
    setConfirmation(null);
    setRoutedAgent(null);
    setDegraded(null);
    setStageStatus(null);
    // Proactively refresh the stage gate on project open so the panel reflects
    // the persisted real progress even before any task runs.
    if (window.kyrozen && projectId) {
      window.kyrozen.getProjectState(projectId)
        .then((state) => { window.kyrozen?.sendStageAction('refresh', state?.stage ?? ''); })
        .catch(() => {});
    }

    // P0-14: 加载该项目已有的聊天历史。消息通过后端持久化，
    // 重启后恢复对话。仅在消息为空时加载（避免覆盖实时对话）。
    if (window.kyrozen && projectId) {
      window.kyrozen.loadChatMessages(projectId)
        .then((result) => {
          if (!result.success || !result.messages?.length) return;
          setMessages(
            reconcileQuestionAnswers(
              result.messages.map((m: { role: string; content: string; operations?: unknown[] }) => ({
                role: (m.role === 'user' || m.role === 'assistant' || m.role === 'system') ? m.role as Message['role'] : 'system',
                content: m.content,
                operations: (Array.isArray(m as any) ? undefined : (m as any).operations),
              }))
            )
          );
        })
        .catch(() => {});
    }
  }, [projectId]);

  useEffect(() => {
    if (!window.kyrozen) return;
    const unsubChat = window.kyrozen.onChatMessage((msg) => {
      if (msg.role === 'system' && /PlatformIO|Python Agent|项目工作目录|Artifact|\[INFO\]|\[model\]|\[tool\]|Failed to persist/i.test(msg.content)) return;
      if (msg.role === 'error') {
        setChatError(friendlyChatError(msg.error || msg.raw || msg.content));
        setIsRunning(false);
        setActivity('');
        return;
      }
      setMessages((prev) => [...prev, {
        role: msg.role as Message['role'],
        content: msg.content,
        operations: msg.operations,
      }]);
      if (msg.role === 'assistant') {
        setIsRunning(false);
        setActivity('');
        setPlan((current) => current ? {
          ...current,
          steps: current.steps.map((step) => ({ ...step, status: 'completed' })),
        } : null);
        onProjectChanged?.();
        // P0-R8: refresh the operation log after each assistant turn so the
        // panel count reflects work actually performed this session (not just
        // the empty list captured at mount time).
        if (window.kyrozen && projectId) {
          window.kyrozen.getWorkspaceRoot(projectId)
            .then(({ workspaceRoot }) => { window.kyrozen?.sendInteraction({ action: 'op_list', workspace_root: workspaceRoot }); })
            .catch(() => {});
        }
      }
    });
    const unsubPlan = window.kyrozen.onExecutionPlan((incoming) => {
      setPlan({ task_id: incoming.task_id, steps: incoming.steps.map((label) => ({ label, status: 'pending' })) });
      setPlanExpanded(true);
    });
    const unsubActivity = window.kyrozen.onTaskActivity((incoming) => {
      setActivity(incoming.description);
      if (incoming.status === 'running' && incoming.task_id) setIsRunning(true);
      setPlan((current) => {
        if (!current || (incoming.task_id && current.task_id && incoming.task_id !== current.task_id)) return current;
        const steps = current.steps.map((step) => ({ ...step }));
        const runningIndex = steps.findIndex((step) => step.status === 'running');
        if (incoming.status === 'failed') {
          const target = runningIndex >= 0 ? runningIndex : steps.findIndex((step) => step.status === 'pending');
          if (target >= 0) steps[target].status = 'failed';
        } else if (incoming.status === 'completed' && runningIndex >= 0) {
          steps[runningIndex].status = 'completed';
        } else if (incoming.status === 'running' && runningIndex < 0) {
          const next = steps.findIndex((step) => step.status === 'pending');
          if (next >= 0) steps[next].status = 'running';
        }
        return { ...current, steps };
      });
    });
    const unsubConfirmation = window.kyrozen.onConfirmationRequest((request) => {
      setConfirmation(request);
      setActivity('等待你确认下一步操作');
    });
    const unsubRouted = window.kyrozen.onAgentRouted((decision) => {
      setRoutedAgent(decision);
      if (decision.degraded) {
        setActivity(`已降级为只读模式（${decision.agent_display_name}）`);
      } else {
        setActivity(`由${decision.agent_display_name}处理中`);
      }
    });
    const unsubDegraded = window.kyrozen.onAgentDegraded((info) => {
      setDegraded(info);
    });
    // P0-06: on stage update, ignore events for other projects to prevent
    // brief cross-project state leakage during project switches.
    const unsubStage = window.kyrozen.onStageUpdated((status) => {
      const eventPid = String((status as any).project_id || '');
      if (eventPid && eventPid !== projectId) return;
      setStageStatus(status);
      onProjectChanged?.();
    });
    const unsubAgentReady = window.kyrozen.onAgentReady((info) => {
      setAgentReady(info);
      if (info.status === 'ready' && projectId) {
        window.kyrozen?.getProjectState(projectId)
          .then((state) => { window.kyrozen?.sendStageAction('refresh', state?.stage ?? ''); })
          .catch(() => {});
      }
    });
    return () => {
      unsubChat();
      unsubPlan();
      unsubActivity();
      unsubConfirmation();
      unsubRouted();
      unsubDegraded();
      unsubStage();
      unsubAgentReady();
    };
  }, [onProjectChanged, projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activity, confirmation]);

  const sendMessage = async (message: string, options?: { echoUser?: boolean }) => {
    if (!window.kyrozen || !projectId || !message.trim()) return;
    if (options?.echoUser !== false) {
      setMessages((prev) => [...prev, { role: 'user', content: message }]);
    }
    setInput('');
    setPendingAttachments([]);
    setIsRunning(true);
    setActivity('正在理解你的需求');
    setPlan(null);
    setRoutedAgent(null);
    setDegraded(null);
    setChatError(null);
    const result = await window.kyrozen.sendChat(message);
    if (!result.success) {
      const friendly = friendlyChatError(result.error);
      setChatError(friendly);
      setIsRunning(false);
      setActivity('');
    } else if (result.content) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: result.content || '',
        operations: result.operations,
      }]);
      setIsRunning(false);
      setActivity('');
      setPlan((current) => current ? {
        ...current,
        steps: current.steps.map((step) => ({ ...step, status: 'completed' })),
      } : null);
      onProjectChanged?.();
    }
  };

  const handleStageAction = async (action: 'refresh' | 'advance_normal' | 'advance_risk' | 'return', riskDetails?: RiskDetails) => {
    if (!window.kyrozen || !projectId) return;
    setStageBusy(true);
    try {
      await window.kyrozen.sendStageAction(action, stageStatus?.stage ?? '', riskDetails);
      await new Promise((resolve) => setTimeout(resolve, 800));
    } catch {
      // The Python Agent pushes a fresh stage_updated event on success; ignore
      // transport errors here so the UI stays responsive.
    } finally {
      setStageBusy(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() && pendingAttachments.length === 0) return;
    if (!projectId) {
      setMessages((prev) => [...prev, { role: 'system', content: '请先选择左侧项目。' }]);
      return;
    }
    const attachmentText = pendingAttachments
      .map((att) => `\n\n--- 附件：${att.name} ---\n${att.content.slice(0, 8000)}${att.content.length > 8000 ? '\n...' : ''}`)
      .join('');
    await sendMessage(input.trim() ? `${input.trim()}${attachmentText}` : attachmentText.trim());
  };

  const respondConfirmation = async (confirmed: boolean, trust = false, storeId?: string | null) => {
    if (!confirmation || !window.kyrozen) return;
    await window.kyrozen.respondConfirmation(confirmation.confirmation_id, confirmed, trust, storeId);
    setConfirmation(null);
    setActivity(confirmed ? '已确认，正在继续执行' : '已取消该操作');
  };

  const handleDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    if (!projectId || !window.kyrozen) return;
    const kyrozenApi = window.kyrozen;
    const files = Array.from(event.dataTransfer.files);
    // P0-05: dragged media (PNG/JPEG/WebP/MP4/MOV) MUST go through the same
    // attachment service as the file picker -- thumbnail + visual analysis --
    // not the plain-text path. Text/code files stay inline in the chat.
    const mediaRe = /^(image\/png|image\/jpeg|image\/webp|video\/mp4|video\/quicktime)$/;
    try {
      const { workspaceRoot } = await kyrozenApi.getWorkspaceRoot(projectId);
      for (const file of files) {
        const filePath = (file as unknown as { path?: string }).path || file.name;
        if (mediaRe.test(file.type)) {
          kyrozenApi.sendInteraction({ action: 'attach', path: filePath, workspace_root: workspaceRoot });
        } else {
          try {
            const text = await readDroppedFile(file);
            setPendingAttachments((prev) => [...prev, text]);
          } catch (error: any) {
            setPendingAttachments((prev) => [...prev, { name: file.name, content: `无法读取文件: ${error.message || String(error)}` }]);
          }
        }
      }
    } catch {
      // Fallback: inline whatever we can still read as text.
      const readFiles = await Promise.all(files.map(async (file) => {
        try { return await readDroppedFile(file); }
        catch (error: any) { return { name: file.name, content: `无法读取文件: ${error.message || String(error)}` }; }
      }));
      setPendingAttachments((prev) => [...prev, ...readFiles]);
    }
  };

  const questionByMessage = useMemo(() => messages.map((message) => splitQuestionBlock(message.content)), [messages]);

  return (
    <div
      className={`flex-1 flex flex-col overflow-hidden relative ${isDragging ? 'bg-accent-soft' : ''}`}
      onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
      onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-hl-blue border-2 border-dashed border-accent m-4 rounded pointer-events-none">
          <div className="text-accent text-lg font-medium">释放文件以添加到附件</div>
        </div>
      )}

      {plan && (
        <div className="bg-surface border-b border-line">
          <button type="button" onClick={() => setPlanExpanded((value) => !value)} className="w-full px-4 py-2 flex items-center justify-between text-left">
            <span className="font-display text-lg text-ink">任务计划</span>
            <span className="text-xs text-ink-faint">{planExpanded ? '收起' : '展开'}</span>
          </button>
          {planExpanded && (
            <div className="px-4 pb-3 space-y-2">
              {plan.steps.map((step, index) => (
                <div key={`${step.label}-${index}`} className="flex items-start gap-2 text-sm text-ink-soft">
                  <span className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 ${dotClass[step.status]}`} />
                  <div className="flex-1"><Markdown content={step.label} onOpenPreview={onOpenPreview} /></div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {stageStatus && (
        <StageGatePanel status={stageStatus} busy={stageBusy} onAction={handleStageAction} />
      )}

      {projectId && (
        <>
          <SoftwareFeaturePanel
            projectId={projectId}
            onOpenPreview={onOpenPreview}
            agentReady={agentReady}
            stageStatus={stageStatus}
          />
          <InteractionPanel projectId={projectId} agentReady={agentReady} />
        </>
      )}

      {routedAgent && (
        <div className={`border-b border-line ${routedAgent.degraded ? 'bg-danger-soft' : 'bg-accent-soft'}`}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 pt-2 text-sm text-ink-soft">
            <AgentModeIcon
              mode={routedAgent.mode}
              className={`w-4 h-4 flex-shrink-0 ${routedAgent.degraded ? 'text-danger' : 'text-accent'}`}
            />
            <span>当前由</span>
            <span className="font-medium text-ink">{routedAgent.agent_display_name}</span>
            <span>处理</span>
            <span className="inline-flex items-center rounded-sm border border-line-strong bg-surface px-2 py-0.5 text-xs font-medium text-accent">
              {routedAgent.mode_label}
            </span>
            {routedAgent.restricted_tools.length > 0 && (
              <span
                className="text-xs text-ink-faint"
                title={`受限工具：${routedAgent.restricted_tools.join('、')}`}
              >
                受限 {routedAgent.restricted_tools.length} 项工具
              </span>
            )}
          </div>
          <div className="px-4 pb-2 text-xs text-ink-faint">
            {AGENT_MODE_HINTS[routedAgent.mode] ?? ''}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {degraded && (
          <div className="panel p-4 border-l-2 border-l-danger bg-danger-soft" role="alert" aria-label="只读降级提示">
            <div className="flex items-center gap-2">
              <AgentModeIcon mode="development" className="w-4 h-4 flex-shrink-0 text-danger" />
              <div className="font-display text-lg text-danger">本地 Agent 已降级为只读模式</div>
            </div>
            <div className="text-sm text-ink mt-1">{degraded.agent_display_name} 初始化失败，当前无法修改文件或执行命令。</div>
            <div className="text-xs text-ink-faint mt-2">原因：{degraded.reason}</div>
            <div className="text-xs text-ink-soft mt-2 font-medium">修复步骤：</div>
            <ol className="list-decimal list-inside text-xs text-ink-soft mt-1 space-y-1">
              {degraded.repair_steps.map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ol>
          </div>
        )}
        {messages.map((message, index) => {
          if (message.hidden) return null;
          const parsed = questionByMessage[index];
          const expanded = expandedOperations.has(index);
          const answered = message.selectedOption !== undefined;
          return (
            <div key={index} data-testid={`chat-message-${message.role}`} className={`max-w-[84%] rounded-sm px-4 py-3 text-sm ${
              message.role === 'user' ? 'bg-accent text-white ml-auto' : message.role === 'system' ? 'bg-warning-soft border border-line text-warning' : 'bg-surface border border-line text-ink'
            }`}>
              {parsed.markdown && <Markdown content={parsed.markdown} onOpenPreview={onOpenPreview} />}
              {parsed.question && (
                <div className="mt-3 border-t border-line pt-3">
                  <div className="font-medium text-ink mb-2">{parsed.question.question}</div>
                  <div className="flex flex-wrap gap-2">
                    {parsed.question.options.map((option) => {
                      const isSelected = message.selectedOption === option.value;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => {
                            if (answered || isRunning) return;
                            setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, selectedOption: option.value } : m)));
                            void sendMessage(option.label, { echoUser: false });
                          }}
                          disabled={isRunning || answered}
                          aria-pressed={isSelected}
                          className={`text-xs rounded-sm px-3 py-1.5 border transition-colors ${
                            isSelected
                              ? 'bg-accent text-white border-accent font-medium'
                              : answered
                                ? 'bg-surface text-ink-faint border-line opacity-60'
                                : 'btn-secondary'
                          }`}
                        >
                          {isSelected ? '✓ ' : ''}{option.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {message.operations && message.operations.length > 0 && (
                <div className="mt-3 pt-2 border-t border-line">
                  <button
                    type="button"
                    onClick={() => setExpandedOperations((previous) => {
                      const next = new Set(previous);
                      if (next.has(index)) next.delete(index); else next.add(index);
                      return next;
                    })}
                    className="text-xs text-ink-faint hover:text-accent"
                  >
                    {expanded ? '收起操作记录' : `查看操作记录（${message.operations.length}）`}
                  </button>
                  {expanded && (
                    <div className="mt-2 bg-paper-sink border border-line rounded-sm p-3 space-y-1.5">
                      {message.operations.map((operation, operationIndex) => (
                        <div key={`${operation.timestamp}-${operationIndex}`} className="flex gap-2 text-xs text-ink-soft font-mono">
                          <span className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${dotClass[(operation.status as OperationStatus) || 'completed'] || dotClass.completed}`} />
                          <span>{operation.description}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {isRunning && activity && (
          <div className="inline-flex items-center gap-2 bg-surface border border-line rounded-sm px-3 py-2 text-sm text-ink-soft" role="status">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <span>{activity}</span>
          </div>
        )}

        {confirmation && (
          <div className="max-w-[84%] panel p-4 border-l-2 border-l-warning" role="dialog" aria-label="操作确认">
            <div className="font-display text-lg">需要你的确认</div>
            <div className="text-sm text-ink mt-1">{confirmation.tool}.{confirmation.action}</div>
            <div className="text-xs text-ink-faint mt-2">{confirmation.reason || '此操作会修改项目或运行命令。'}</div>
            <pre className="mt-3 max-h-40 overflow-auto bg-paper-sink border border-line rounded-sm p-3 text-xs text-ink-soft font-mono whitespace-pre-wrap">{JSON.stringify(confirmation.parameters, null, 2)}</pre>
            <div className="flex flex-wrap gap-2 mt-3">
              <button type="button" onClick={() => void respondConfirmation(true, false, confirmation?.store_id)} className="btn-primary text-xs">允许一次</button>
              <button type="button" onClick={() => void respondConfirmation(true, true, confirmation?.store_id)} className="btn-secondary text-xs">本项目信任此操作类型</button>
              <button type="button" onClick={() => void respondConfirmation(false, false, confirmation?.store_id)} className="btn-ghost text-xs">拒绝</button>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 border-t border-line space-y-2 bg-paper">
        {chatError && (
          <div className="border border-line border-l-2 border-l-danger bg-danger-soft rounded-sm px-3 py-2 text-xs">
            <div className="flex items-start justify-between gap-2">
              <span className="text-danger">{chatError.summary}</span>
              <button type="button" onClick={() => setChatError(null)} className="text-ink-faint hover:text-ink shrink-0">×</button>
            </div>
            <details className="mt-1">
              <summary className="cursor-pointer text-ink-faint">技术详情</summary>
              <pre className="mt-1 max-h-32 overflow-auto bg-paper-sink border border-line rounded-sm p-2 text-[11px] text-ink-soft font-mono whitespace-pre-wrap">{chatError.raw}</pre>
            </details>
          </div>
        )}
        {pendingAttachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {pendingAttachments.map((attachment, index) => (
              <div key={`${attachment.name}-${index}`} className="inline-flex items-center gap-2 px-3 py-1 bg-surface border border-line-strong rounded text-xs text-ink-soft">
                <span className="truncate max-w-[200px]">{attachment.name}</span>
                <button type="button" onClick={() => setPendingAttachments((prev) => prev.filter((_, itemIndex) => itemIndex !== index))} className="text-ink-faint hover:text-danger">×</button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && void handleSend()}
            placeholder={projectId ? '说说你的想法或下一步想做什么…' : '请先选择项目'}
            disabled={!projectId || isRunning}
            className="input flex-1"
          />
          {isRunning ? (
            <button type="button" onClick={() => { window.kyrozen?.cancelTask(); setIsRunning(false); setActivity(''); }} className="btn-danger px-5">停止</button>
          ) : (
            <button type="button" onClick={() => void handleSend()} disabled={!projectId || (!input.trim() && pendingAttachments.length === 0)} className="btn-primary px-5">发送</button>
          )}
        </div>
      </div>
    </div>
  );
}
