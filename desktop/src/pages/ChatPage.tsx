import { useEffect, useRef, useState } from 'react';

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  raw?: string;
}

interface ExecutionPlan {
  task_id: string;
  steps: string[];
}

interface ChatPageProps {
  projectId: string | null;
  onOpenPreview?: (url: string) => void;
}

const LOCAL_URL_RE = /(https?:\/\/localhost(:\d+)(\/[^\s<>\"]*))/g;

function renderMessageContent(content: string, onOpenPreview?: (url: string) => void) {
  if (!onOpenPreview) return content;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;
  while ((match = LOCAL_URL_RE.exec(content)) !== null) {
    const [fullUrl] = match;
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    parts.push(
      <button
        key={match.index}
        onClick={() => onOpenPreview(fullUrl)}
        className="text-blue-300 hover:text-blue-200 underline"
        title="在内置预览中打开"
      >
        {fullUrl}
      </button>
    );
    lastIndex = match.index + fullUrl.length;
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }
  return parts.length > 0 ? parts : content;
}

function readDroppedFile(file: File): Promise<{ name: string; content: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, content: String(reader.result || '') });
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.readAsText(file);
  });
}

export function ChatPage({ projectId, onOpenPreview }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '已连接到 Kyrozen 云端。选择左侧项目后，可以让 AI 帮你生成代码、操作本地文件或启动预览。' },
  ]);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Array<{ name: string; content: string }>>([]);
  const [expandedRaw, setExpandedRaw] = useState<Set<number>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!window.kyrozen) return;
    const chatHandler = (msg: { role: string; content: string; raw?: string }) => {
      const item: Message = {
        role: msg.role as Message['role'],
        content: msg.content,
        raw: msg.raw,
      };
      setMessages((prev) => [...prev, item]);
      if (msg.role === 'assistant' || msg.role === 'system') {
        setIsRunning(false);
      }
    };
    const planHandler = (p: ExecutionPlan) => {
      setPlan(p);
    };
    window.kyrozen.onChatMessage(chatHandler);
    window.kyrozen.onExecutionPlan(planHandler);
    return () => {
      // ipcRenderer listeners are not removed here because the preload wrapper
      // does not expose a remove API; this is acceptable for the single-page UI.
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() && pendingAttachments.length === 0) return;
    if (!window.kyrozen) return;
    if (!projectId) {
      setMessages((prev) => [...prev, { role: 'system', content: '请先选择左侧项目。' }]);
      return;
    }
    setPlan(null);

    const attachmentText = pendingAttachments
      .map((att) => `\n\n--- 附件：${att.name} ---\n${att.content.slice(0, 8000)}${att.content.length > 8000 ? '\n...' : ''}`)
      .join('');
    const fullMessage = input.trim() ? `${input.trim()}${attachmentText}` : attachmentText.trim();

    setMessages((prev) => [...prev, { role: 'user', content: fullMessage }]);
    window.kyrozen.sendChat(fullMessage);
    setInput('');
    setPendingAttachments([]);
    setIsRunning(true);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (!projectId) {
      setMessages((prev) => [...prev, { role: 'system', content: '请先选择左侧项目后再拖拽文件。' }]);
      return;
    }
    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;
    const readFiles = await Promise.all(
      files.map(async (file) => {
        try {
          return await readDroppedFile(file);
        } catch (err: any) {
          return { name: file.name, content: `无法读取文件: ${err.message || String(err)}` };
        }
      })
    );
    setPendingAttachments((prev) => [...prev, ...readFiles]);
  };

  const removeAttachment = (index: number) => {
    setPendingAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCancel = () => {
    if (!window.kyrozen) return;
    window.kyrozen.cancelTask();
    setIsRunning(false);
    setMessages((prev) => [...prev, { role: 'system', content: '已请求取消当前任务' }]);
  };

  return (
    <div
      className={`flex-1 flex flex-col overflow-hidden relative ${isDragging ? 'bg-blue-900/20' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-blue-900/40 border-2 border-dashed border-blue-400 m-4 rounded-2xl pointer-events-none">
          <div className="text-blue-100 text-lg font-medium">释放文件以添加到附件</div>
        </div>
      )}
      {plan && (
        <div className="px-4 py-3 bg-slate-800 border-b border-slate-700">
          <div className="text-xs font-medium text-slate-300 mb-1">AI 执行计划（将自动实施）</div>
          <ol className="list-decimal list-inside space-y-1 text-sm text-slate-100">
            {plan.steps.map((step, idx) => (
              <li key={idx} className="truncate">{step}</li>
            ))}
          </ol>
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg, idx) => {
          const isRawExpanded = expandedRaw.has(idx);
          return (
            <div
              key={idx}
              className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white self-end ml-auto'
                  : 'bg-slate-700 text-slate-100'
              }`}
            >
              {renderMessageContent(msg.content, onOpenPreview)}
              {msg.raw && (
                <div className="mt-2 pt-2 border-t border-slate-600/50">
                  <button
                    type="button"
                    onClick={() => {
                      setExpandedRaw((prev) => {
                        const next = new Set(prev);
                        if (next.has(idx)) {
                          next.delete(idx);
                        } else {
                          next.add(idx);
                        }
                        return next;
                      });
                    }}
                    className="text-xs text-slate-400 hover:text-blue-300 transition-colors"
                  >
                    {isRawExpanded ? '收起原始输出' : '展开原始输出'}
                  </button>
                  {isRawExpanded && (
                    <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-400 font-mono whitespace-pre-wrap">
                      {msg.raw}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
      <div className="p-4 border-t border-slate-700 space-y-2">
        {pendingAttachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {pendingAttachments.map((att, idx) => (
              <div
                key={`${att.name}-${idx}`}
                className="inline-flex items-center gap-2 px-3 py-1 bg-slate-800 border border-slate-600 rounded-full text-xs text-slate-200"
              >
                <span className="truncate max-w-[200px]">{att.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  className="text-slate-400 hover:text-red-400"
                  aria-label="移除附件"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder={projectId ? '输入消息或拖拽文件...' : '请先选择项目'}
            disabled={!projectId || isRunning}
            className="flex-1 px-4 py-2 bg-slate-900 border border-slate-600 rounded-full focus:outline-none focus:border-blue-500 disabled:opacity-50"
          />
        {isRunning ? (
          <button
            onClick={handleCancel}
            className="px-5 py-2 bg-red-600 hover:bg-red-500 text-white rounded-full font-medium transition-colors"
          >
            停止
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!projectId}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded-full font-medium transition-colors"
          >
            发送
          </button>
        )}
        </div>
      </div>
    </div>
  );
}
