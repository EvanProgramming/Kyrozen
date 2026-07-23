import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { getProject, getProjectState } from '../api/projects';
import { sendChatMessage, getTask, confirmTask, getChatHistory } from '../api/chat';
import { handleApiError } from '../api/client';
import type { Project, ProjectState, Task } from '../types/api';
import { ChatIcon, DocumentIcon, SendIcon, SparklesIcon } from '../components/Icons';
import { QuestionModal, type QuestionData } from '../components/QuestionModal';

const STAGES = [
  { id: 'problem_discovery', label: '问题发现', mode: 'discovery', hint: '澄清用户痛点，生成 Problem Brief' },
  { id: 'market_research', label: '市场调研', mode: 'market_research', hint: '搜索竞品、用户反馈与市场机会' },
  { id: 'product_definition', label: '产品规划', mode: 'planning', hint: '定义产品目标、用户与功能优先级' },
  { id: 'solution_design', label: '方案设计', mode: 'planning', hint: '对比技术方案并输出 PRD' },
  { id: 'development', label: '软件开发', mode: 'development', hint: '生成代码、运行测试与调试' },
  { id: 'hardware', label: '硬件开发', mode: 'hardware', hint: '生成 BOM、固件与硬件方案' },
  { id: 'testing', label: '测试验证', mode: 'testing', hint: '生成测试计划与验证报告' },
  { id: 'iteration', label: '迭代优化', mode: 'learning', hint: '总结经验并生成改进建议' },
];

type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  status?: 'loading' | 'error';
  taskId?: string;
};

function parseQuestionBlock(content: string): { question: QuestionData | null; displayContent: string } {
  const regex = /```kyrozen-question\s*([\s\S]*?)\s*```/;
  const match = content.match(regex);
  if (!match) return { question: null, displayContent: content };
  try {
    const parsed = JSON.parse(match[1]);
    if (parsed.question && Array.isArray(parsed.options)) {
      return {
        question: parsed as QuestionData,
        displayContent: content.replace(regex, '').trim(),
      };
    }
  } catch {
    // ignore malformed block
  }
  return { question: null, displayContent: content };
}

function getTaskAnswer(task: Task): string {
  if (task.result === null || task.result === undefined) return '已完成';
  if (typeof task.result === 'string') return task.result;
  if (typeof task.result === 'object' && 'answer' in task.result) {
    return String((task.result as { answer?: unknown }).answer ?? JSON.stringify(task.result));
  }
  return JSON.stringify(task.result);
}

export function ProjectWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [projectState, setProjectState] = useState<ProjectState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'chat'>('overview');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<QuestionData | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    taskId: string;
    tool: string;
    action: string;
    parameters: Record<string, unknown>;
    reason?: string;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chatLoadedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!projectId) return;

    async function loadData() {
      try {
        const [projectData, stateData] = await Promise.all([
          getProject(projectId!),
          getProjectState(projectId!),
        ]);
        setProject(projectData);
        setProjectState(stateData);
      } catch (err) {
        setError(handleApiError(err));
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [projectId]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!project || !projectId || chatLoadedRef.current === projectId) return;
    chatLoadedRef.current = projectId;
    const pid = projectId;
    const stageLabel = STAGES.find((s) => s.id === project.current_stage)?.label ?? project.current_stage;
    const greeting = { role: 'system' as const, content: `我是 Kyrozen，你的 AI 产品开发伙伴。当前阶段：${stageLabel}。告诉我你想做什么。` };

    async function loadChat() {
      try {
        const history = await getChatHistory(pid);
        if (history.length === 0 || history[0].role !== 'system') {
          setMessages([greeting, ...history.map((m) => ({ role: m.role, content: m.content }))]);
        } else {
          setMessages(history.map((m) => ({ role: m.role, content: m.content })));
        }
      } catch (err) {
        console.error('Failed to load chat history', err);
        setMessages([greeting]);
      }
    }
    loadChat();
  }, [project, projectId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingConfirmation]);

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.role === 'assistant') {
      const parsed = parseQuestionBlock(lastMessage.content);
      setPendingQuestion(parsed.question);
    } else {
      setPendingQuestion(null);
    }
  }, [messages]);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function refreshProjectState() {
    if (!projectId) return;
    try {
      const [projectData, stateData] = await Promise.all([
        getProject(projectId),
        getProjectState(projectId),
      ]);
      setProject(projectData);
      setProjectState(stateData);
    } catch (err) {
      // Non-fatal refresh error; the existing error state remains visible.
      console.error('Failed to refresh project state', err);
    }
  }

  function startPolling(taskId: string) {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const task = await getTask(taskId);
        if (task.status === 'running') {
          const latest = task.steps[task.steps.length - 1];
          const progressText = latest
            ? latest.metadata?.tool
              ? `${latest.description} · ${latest.metadata.tool}`
              : latest.description
            : '思考中...';
          updateMessageByTaskId(taskId, { content: progressText });
        } else if (task.status === 'completed') {
          stopPolling();
          updateMessageByTaskId(taskId, { content: getTaskAnswer(task), status: undefined });
          setIsSending(false);
          await refreshProjectState();
        } else if (task.status === 'failed') {
          stopPolling();
          updateMessageByTaskId(taskId, { content: `任务失败: ${task.errors.join(', ')}`, status: 'error' });
          setIsSending(false);
          await refreshProjectState();
        } else if (task.status === 'cancelled') {
          stopPolling();
          updateMessageByTaskId(taskId, { content: '已取消', status: 'error' });
          setIsSending(false);
          await refreshProjectState();
        } else if (task.status === 'waiting_confirmation') {
          stopPolling();
          const latestStep = [...task.steps].reverse().find((s) => s.status === 'waiting_confirmation');
          const metadata = latestStep?.metadata as Record<string, unknown> | undefined;
          if (metadata) {
            setPendingConfirmation({
              taskId,
              tool: String(metadata.tool ?? ''),
              action: String(metadata.action ?? ''),
              parameters: (metadata.parameters as Record<string, unknown>) ?? {},
              reason: latestStep?.description,
            });
            updateMessageByTaskId(taskId, { content: latestStep?.description || '等待确认', status: undefined });
          } else {
            updateMessageByTaskId(taskId, { content: '等待确认', status: undefined });
          }
          setIsSending(false);
        }
      } catch (err) {
        stopPolling();
        updateMessageByTaskId(taskId, { content: `轮询失败: ${handleApiError(err)}`, status: 'error' });
        setIsSending(false);
      }
    }, 1500);
  }

  function updateMessageByTaskId(taskId: string, updates: Partial<Message>) {
    setMessages((prev) => prev.map((m) => (m.taskId === taskId ? { ...m, ...updates } : m)));
  }

  async function submitUserMessage(userContent: string) {
    if (isSending || !project || !projectId) return;

    setMessages((prev) => [...prev, { role: 'user', content: userContent }]);
    setIsSending(true);

    try {
      const mode = STAGES.find((s) => s.id === project.current_stage)?.mode ?? project.current_stage;
      const response = await sendChatMessage({ message: userContent, project_id: projectId, mode });
      const assistantTaskId = response.task_id;
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '', status: 'loading', taskId: assistantTaskId },
      ]);
      startPolling(assistantTaskId);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `发送失败: ${handleApiError(err)}`, status: 'error' },
      ]);
      setIsSending(false);
    }
  }

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const userContent = input.trim();
    if (!userContent) return;
    setInput('');
    void submitUserMessage(userContent);
  }

  function handleRetry(messageIndex: number) {
    const userMessage = messages[messageIndex - 1];
    if (!userMessage || userMessage.role !== 'user') return;

    const userContent = userMessage.content;
    setMessages((prev) => prev.filter((_, i) => i !== messageIndex - 1 && i !== messageIndex));
    void submitUserMessage(userContent);
  }

  async function handleConfirm(confirmed: boolean) {
    if (!pendingConfirmation) return;
    const { taskId } = pendingConfirmation;
    setPendingConfirmation(null);
    setIsSending(true);
    updateMessageByTaskId(taskId, { content: confirmed ? '正在执行...' : '已取消', status: confirmed ? 'loading' : 'error' });

    try {
      const task = await confirmTask(taskId, confirmed);
      if (task.status === 'completed') {
        stopPolling();
        updateMessageByTaskId(taskId, { content: getTaskAnswer(task) });
        setIsSending(false);
        await refreshProjectState();
      } else if (task.status === 'failed') {
        stopPolling();
        updateMessageByTaskId(taskId, { content: `任务失败: ${task.errors.join(', ')}`, status: 'error' });
        setIsSending(false);
        await refreshProjectState();
      } else if (task.status === 'cancelled') {
        stopPolling();
        updateMessageByTaskId(taskId, { content: '已取消', status: 'error' });
        setIsSending(false);
        await refreshProjectState();
      } else if (confirmed) {
        startPolling(taskId);
      } else {
        updateMessageByTaskId(taskId, { content: '已取消', status: 'error' });
        setIsSending(false);
      }
    } catch (err) {
      updateMessageByTaskId(taskId, { content: `确认失败: ${handleApiError(err)}`, status: 'error' });
      setIsSending(false);
    }
  }

  if (isLoading) {
    return (
      <Layout>
        <div className="card text-center py-20 text-warm-500">加载项目中...</div>
      </Layout>
    );
  }

  if (error || !project) {
    return (
      <Layout>
        <div className="card text-center py-20 text-red-600">{error || '项目不存在'}</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <span className="px-3 py-1 bg-sky-50 text-sky-700 text-xs font-medium rounded-full">
              {project.current_stage}
            </span>
            <span className="px-3 py-1 bg-warm-100 text-warm-600 text-xs rounded-full">{project.status}</span>
          </div>
          <h1 className="mb-2">{project.name}</h1>
          <p className="text-warm-500">{project.description || '暂无项目描述'}</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="card p-4">
              <h3 className="text-sm font-medium text-warm-500 uppercase tracking-wide mb-4">开发阶段</h3>
              <nav className="space-y-1">
                {STAGES.map((stage) => (
                  <button
                    key={stage.id}
                    onClick={() => setActiveTab('chat')}
                    title={`${stage.hint}（点击进入对话）`}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors text-left ${
                      project.current_stage === stage.id
                        ? 'bg-sky-50 text-sky-700 font-medium'
                        : 'text-warm-600 hover:bg-warm-50'
                    }`}
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        project.current_stage === stage.id ? 'bg-sky-500' : 'bg-warm-300'
                      }`}
                    />
                    {stage.label}
                  </button>
                ))}
              </nav>
            </div>
          </div>

          {/* Main content */}
          <div className="lg:col-span-3 space-y-6">
            {activeTab === 'overview' ? (
              <>
                {/* Next Action Card */}
                <div className="card bg-gradient-to-br from-sky-50 to-white border-sky-100">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-sky-500 flex items-center justify-center flex-shrink-0">
                      <SparklesIcon className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg mb-2">推荐下一步</h3>
                      {projectState?.next_action ? (
                        <>
                          <p className="text-warm-900 font-medium mb-2">{projectState.next_action.action}</p>
                          <p className="text-sm text-warm-500 mb-4">{projectState.next_action.reason}</p>
                          <button onClick={() => setActiveTab('chat')} className="btn-primary text-sm">
                            <ChatIcon className="w-4 h-4 mr-2" />
                            开始对话
                          </button>
                        </>
                      ) : (
                        <p className="text-warm-500">当前阶段暂无明确推荐，可与 AI 助手交流继续推进。</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Project Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <DocumentIcon className="w-5 h-5 text-sky-500" />
                      <h3 className="text-lg">项目目标</h3>
                    </div>
                    <p className="text-warm-600">{project.goal || '尚未设定项目目标'}</p>
                  </div>

                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <SparklesIcon className="w-5 h-5 text-sky-500" />
                      <h3 className="text-lg">下一步计划</h3>
                    </div>
                    <p className="text-warm-600">{project.next_steps || '暂无下一步计划'}</p>
                  </div>
                </div>

                {/* Progress */}
                <div className="card">
                  <h3 className="text-lg mb-4">项目进度</h3>
                  <div className="w-full h-2 bg-warm-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 rounded-full transition-all"
                      style={{ width: `${project.progress}%` }}
                    />
                  </div>
                  <p className="text-sm text-warm-500 mt-2">{project.progress}% 完成</p>
                </div>
              </>
            ) : (
              <div className="card min-h-[500px] lg:h-[calc(100vh-10rem)] flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                  <ChatIcon className="w-5 h-5 text-sky-500" />
                  <h3 className="text-lg">AI 助手</h3>
                </div>

                <div className="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
                  {messages.map((message, index) => (
                    <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                          message.role === 'user'
                            ? 'bg-sky-500 text-white'
                            : message.role === 'system'
                              ? 'bg-warm-100 text-warm-600'
                              : 'bg-white border border-warm-200 text-warm-900'
                        }`}
                      >
                        {message.status === 'loading' ? (
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-2">
                              <span className="inline-block w-4 h-4 border-2 border-warm-300 border-t-sky-500 rounded-full animate-spin" />
                              <span className="truncate">{message.content || '思考中...'}</span>
                            </div>
                          </div>
                        ) : (
                          <div className="whitespace-pre-wrap">
                            {message.role === 'assistant'
                              ? parseQuestionBlock(message.content).displayContent || '(请从下方弹窗中选择回答)'
                              : message.content}
                          </div>
                        )}
                        {message.role === 'assistant' && message.status === 'error' && (
                          <button
                            onClick={() => handleRetry(index)}
                            className="mt-2 text-xs font-medium text-sky-600 hover:text-sky-700"
                          >
                            重试
                          </button>
                        )}
                      </div>
                    </div>
                  ))}

                  {pendingConfirmation && (
                    <div className="flex justify-start">
                      <div className="max-w-[90%] w-full bg-white border border-warm-200 rounded-2xl p-4">
                        <h4 className="font-medium text-warm-900 mb-2">等待确认</h4>
                        <div className="space-y-2 text-sm text-warm-600 mb-4">
                          <p>
                            <span className="font-medium">工具:</span> {pendingConfirmation.tool}
                          </p>
                          <p>
                            <span className="font-medium">动作:</span> {pendingConfirmation.action}
                          </p>
                          <pre className="bg-warm-50 rounded-lg p-2 overflow-x-auto text-xs">
                            {JSON.stringify(pendingConfirmation.parameters, null, 2)}
                          </pre>
                          {pendingConfirmation.reason && (
                            <p>
                              <span className="font-medium">原因:</span> {pendingConfirmation.reason}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button onClick={() => handleConfirm(true)} className="btn-primary text-sm">
                            确认执行
                          </button>
                          <button onClick={() => handleConfirm(false)} className="btn-secondary text-sm">
                            取消
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>

                <form onSubmit={handleSend} className="flex items-center gap-2 pt-4 border-t border-warm-200">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={pendingConfirmation ? '请先确认或取消上方操作' : '输入消息...'}
                    disabled={isSending || !!pendingConfirmation}
                    className="input flex-1 min-w-0"
                  />
                  <button
                    type="submit"
                    disabled={isSending || !input.trim() || !!pendingConfirmation}
                    className="btn-primary p-2 sm:p-2.5 shrink-0"
                  >
                    <SendIcon className="w-5 h-5" />
                  </button>
                </form>
              </div>
            )}
          </div>
        </div>
      </div>

      <QuestionModal
        open={!!pendingQuestion}
        question={pendingQuestion}
        onAnswer={(value) => {
          setPendingQuestion(null);
          submitUserMessage(value);
        }}
        onClose={() => setPendingQuestion(null)}
      />
    </Layout>
  );
}
