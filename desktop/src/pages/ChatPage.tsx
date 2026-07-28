import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  }, [projectId]);

  useEffect(() => {
    if (!window.kyrozen) return;
    const unsubChat = window.kyrozen.onChatMessage((msg) => {
      if (msg.role === 'system' && /PlatformIO|Python Agent|项目工作目录|Artifact|\[INFO\]|\[model\]|\[tool\]/i.test(msg.content)) return;
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
    return () => {
      unsubChat();
      unsubPlan();
      unsubActivity();
      unsubConfirmation();
      unsubRouted();
      unsubDegraded();
    };
  }, [onProjectChanged]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activity, confirmation]);

  const sendMessage = async (message: string) => {
    if (!window.kyrozen || !projectId || !message.trim()) return;
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setInput('');
    setPendingAttachments([]);
    setIsRunning(true);
    setActivity('正在理解你的需求');
    setPlan(null);
    setRoutedAgent(null);
    setDegraded(null);
    const result = await window.kyrozen.sendChat(message);
    if (!result.success) {
      setMessages((prev) => [...prev, { role: 'system', content: `发送失败：${result.error || '未知错误'}` }]);
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

  const respondConfirmation = async (confirmed: boolean, trust = false) => {
    if (!confirmation || !window.kyrozen) return;
    await window.kyrozen.respondConfirmation(confirmation.confirmation_id, confirmed, trust);
    setConfirmation(null);
    setActivity(confirmed ? '已确认，正在继续执行' : '已取消该操作');
  };

  const handleDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    if (!projectId) return;
    const files = Array.from(event.dataTransfer.files);
    const readFiles = await Promise.all(files.map(async (file) => {
      try { return await readDroppedFile(file); }
      catch (error: any) { return { name: file.name, content: `无法读取文件: ${error.message || String(error)}` }; }
    }));
    setPendingAttachments((prev) => [...prev, ...readFiles]);
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
            <span className="font-hand text-lg text-ink">任务计划</span>
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
              <div className="font-hand text-lg text-danger">本地 Agent 已降级为只读模式</div>
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
          const parsed = questionByMessage[index];
          const expanded = expandedOperations.has(index);
          return (
            <div key={index} className={`max-w-[84%] rounded-sm px-4 py-3 text-sm ${
              message.role === 'user' ? 'bg-accent text-white ml-auto' : message.role === 'system' ? 'bg-warning-soft border border-line text-warning' : 'bg-surface border border-line text-ink'
            }`}>
              {parsed.markdown && <Markdown content={parsed.markdown} onOpenPreview={onOpenPreview} />}
              {parsed.question && (
                <div className="mt-3 border-t border-line pt-3">
                  <div className="font-medium text-ink mb-2">{parsed.question.question}</div>
                  <div className="flex flex-wrap gap-2">
                    {parsed.question.options.map((option) => (
                      <button key={option.value} type="button" onClick={() => void sendMessage(option.value)} disabled={isRunning} className="btn-secondary text-xs">
                        {option.label}
                      </button>
                    ))}
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
            <div className="font-hand text-lg">需要你的确认</div>
            <div className="text-sm text-ink mt-1">{confirmation.tool}.{confirmation.action}</div>
            <div className="text-xs text-ink-faint mt-2">{confirmation.reason || '此操作会修改项目或运行命令。'}</div>
            <pre className="mt-3 max-h-40 overflow-auto bg-paper-sink border border-line rounded-sm p-3 text-xs text-ink-soft font-mono whitespace-pre-wrap">{JSON.stringify(confirmation.parameters, null, 2)}</pre>
            <div className="flex flex-wrap gap-2 mt-3">
              <button type="button" onClick={() => void respondConfirmation(true)} className="btn-primary text-xs">确认一次</button>
              <button type="button" onClick={() => void respondConfirmation(true, true)} className="btn-secondary text-xs">本次会话信任此类操作</button>
              <button type="button" onClick={() => void respondConfirmation(false)} className="btn-ghost text-xs">取消</button>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 border-t border-line space-y-2 bg-paper">
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
