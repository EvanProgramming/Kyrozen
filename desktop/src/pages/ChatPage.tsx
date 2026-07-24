import { useEffect, useRef, useState } from 'react';

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface ExecutionPlan {
  task_id: string;
  steps: string[];
}

interface ChatPageProps {
  projectId: string | null;
}

export function ChatPage({ projectId }: ChatPageProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '已连接到 Kyrozen 云端。选择左侧项目后，可以让 AI 帮你生成代码、操作本地文件或启动预览。' },
  ]);
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!window.kyrozen) return;
    const chatHandler = (msg: { role: string; content: string }) => {
      const item: Message = {
        role: msg.role as Message['role'],
        content: msg.content,
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
    if (!input.trim() || !window.kyrozen) return;
    if (!projectId) {
      setMessages((prev) => [...prev, { role: 'system', content: '请先选择左侧项目。' }]);
      return;
    }
    setPlan(null);
    setMessages((prev) => [...prev, { role: 'user', content: input }]);
    window.kyrozen.sendChat(input);
    setInput('');
    setIsRunning(true);
  };

  const handleCancel = () => {
    if (!window.kyrozen) return;
    window.kyrozen.cancelTask();
    setIsRunning(false);
    setMessages((prev) => [...prev, { role: 'system', content: '已请求取消当前任务' }]);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
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
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white self-end ml-auto'
                : 'bg-slate-700 text-slate-100'
            }`}
          >
            {msg.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="p-4 border-t border-slate-700 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={projectId ? '输入消息...' : '请先选择项目'}
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
  );
}
