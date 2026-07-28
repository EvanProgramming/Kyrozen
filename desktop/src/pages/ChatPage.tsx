import { useEffect, useMemo, useRef, useState } from 'react';
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
        <div className="flex items-center gap-2 px-4 py-2 bg-accent-soft border-b border-line text-sm text-ink-soft" title={routedAgent.reason}>
          <span className={`w-2 h-2 rounded-full ${routedAgent.degraded ? 'bg-warning' : 'bg-accent'}`} />
          <span>
            由 <span className="font-medium text-ink">{routedAgent.agent_display_name}</span> 处理（模式：{routedAgent.mode_label}）
          </span>
          {routedAgent.restricted_tools.length > 0 && (
            <span className="text-xs text-ink-faint">受限工具 {routedAgent.restricted_tools.length} 项</span>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {degraded && (
          <div className="panel p-4 border-l-2 border-l-danger bg-danger-soft" role="alert" aria-label="只读降级提示">
            <div className="font-hand text-lg text-danger">本地 Agent 已降级为只读模式</div>
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
