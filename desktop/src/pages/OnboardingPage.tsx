import { useEffect, useState } from 'react';

export type OnboardingStep = 'language' | 'login' | 'python' | 'project' | 'complete';

interface Project {
  id: string;
  name: string;
  current_stage: string;
  description?: string;
}

interface OnboardingState {
  step: OnboardingStep;
  language: 'zh' | 'en';
  serverUrl: string;
  email: string;
  password: string;
  loginError: string;
  wsToken: string | null;
  pythonStatus: 'idle' | 'checking' | 'ready' | 'installing' | 'error';
  pythonPath: string | null;
  pythonError: string;
  pythonProgress: string;
  projects: Project[];
  selectedProjectId: string | null;
  workspaceRoot: string | null;
  workspaceError: string;
}

const dict = {
  zh: {
    welcome: '欢迎使用 Kyrozen',
    languageTitle: '选择语言',
    next: '下一步',
    loginTitle: '登录账号',
    serverUrl: '服务器地址',
    email: '邮箱',
    password: '密码',
    login: '登录',
    loggingIn: '登录中...',
    pythonTitle: '准备 Python 运行时',
    pythonReady: 'Python 运行时已就绪',
    pythonNotReady: '尚未安装 Python 运行时',
    pythonCheck: '检查状态',
    pythonDownload: '下载并安装',
    pythonOffline: '离线安装',
    pythonOfflineTip: '若下载失败，可访问 python-build-standalone  releases 手动下载对应版本并解压。',
    projectTitle: '选择项目目录',
    projectSubtitle: '从云端项目列表中选择一个项目，或先使用默认目录。',
    noProjects: '暂无云端项目，将使用默认目录。',
    selectProject: '选择项目',
    pickWorkspace: '选择本地目录',
    pickedWorkspace: '已选择目录',
    completeTitle: '准备就绪',
    enterApp: '进入 Kyrozen',
    errorRequired: '请填写所有必填项',
  },
  en: {
    welcome: 'Welcome to Kyrozen',
    languageTitle: 'Choose Language',
    next: 'Next',
    loginTitle: 'Sign In',
    serverUrl: 'Server URL',
    email: 'Email',
    password: 'Password',
    login: 'Sign In',
    loggingIn: 'Signing in...',
    pythonTitle: 'Prepare Python Runtime',
    pythonReady: 'Python runtime is ready',
    pythonNotReady: 'Python runtime is not installed',
    pythonCheck: 'Check Status',
    pythonDownload: 'Download & Install',
    pythonOffline: 'Offline Install',
    pythonOfflineTip: 'If download fails, visit python-build-standalone releases to manually download the matching version.',
    projectTitle: 'Choose Project Directory',
    projectSubtitle: 'Select a cloud project or use the default directory.',
    noProjects: 'No cloud projects yet; the default directory will be used.',
    selectProject: 'Select Project',
    pickWorkspace: 'Choose Local Directory',
    pickedWorkspace: 'Directory selected',
    completeTitle: 'Ready',
    enterApp: 'Enter Kyrozen',
    errorRequired: 'Please fill in all required fields',
  },
};

function useKyrozen() {
  return window.kyrozen!;
}

function LanguageStep({
  language,
  onSelect,
  t,
}: {
  language: 'zh' | 'en';
  onSelect: (lang: 'zh' | 'en') => void;
  t: (typeof dict)['zh'];
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-center">{t.languageTitle}</h2>
      <div className="grid grid-cols-2 gap-4">
        <button
          type="button"
          onClick={() => onSelect('zh')}
          className={`px-6 py-4 rounded-xl border text-lg font-medium transition-colors ${
            language === 'zh'
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-slate-800 border-slate-600 text-slate-200 hover:bg-slate-700'
          }`}
        >
          中文
        </button>
        <button
          type="button"
          onClick={() => onSelect('en')}
          className={`px-6 py-4 rounded-xl border text-lg font-medium transition-colors ${
            language === 'en'
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-slate-800 border-slate-600 text-slate-200 hover:bg-slate-700'
          }`}
        >
          English
        </button>
      </div>
    </div>
  );
}

function LoginStep({
  state,
  setState,
  onNext,
  t,
}: {
  state: OnboardingState;
  setState: React.Dispatch<React.SetStateAction<OnboardingState>>;
  onNext: () => void;
  t: (typeof dict)['zh'];
}) {
  const [loading, setLoading] = useState(false);
  const kyrozen = useKyrozen();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!state.serverUrl || !state.email || !state.password) {
      setState((prev) => ({ ...prev, loginError: t.errorRequired }));
      return;
    }
    setLoading(true);
    setState((prev) => ({ ...prev, loginError: '' }));
    try {
      const result = await kyrozen.login(state.email, state.password, state.serverUrl);
      if (result.success && result.wsToken) {
        setState((prev) => ({ ...prev, wsToken: result.wsToken! }));
        onNext();
      } else {
        setState((prev) => ({ ...prev, loginError: result.error || 'Login failed' }));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h2 className="text-xl font-semibold text-center">{t.loginTitle}</h2>
      <div>
        <label className="block text-sm text-slate-300 mb-1">{t.serverUrl}</label>
        <input
          type="url"
          value={state.serverUrl}
          onChange={(e) => setState((prev) => ({ ...prev, serverUrl: e.target.value }))}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-slate-300 mb-1">{t.email}</label>
        <input
          type="email"
          value={state.email}
          onChange={(e) => setState((prev) => ({ ...prev, email: e.target.value }))}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>
      <div>
        <label className="block text-sm text-slate-300 mb-1">{t.password}</label>
        <input
          type="password"
          value={state.password}
          onChange={(e) => setState((prev) => ({ ...prev, password: e.target.value }))}
          className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
          required
        />
      </div>
      {state.loginError && (
        <div className="text-sm text-red-400">{state.loginError}</div>
      )}
      <button
        type="submit"
        disabled={loading}
        className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded-lg font-medium transition-colors"
      >
        {loading ? t.loggingIn : t.login}
      </button>
    </form>
  );
}

function PythonStep({
  state,
  setState,
  onNext,
  t,
}: {
  state: OnboardingState;
  setState: React.Dispatch<React.SetStateAction<OnboardingState>>;
  onNext: () => void;
  t: (typeof dict)['zh'];
}) {
  const kyrozen = useKyrozen();

  useEffect(() => {
    const unsubscribe = kyrozen.onOnboardingProgress((progress) => {
      if (progress.step === 'python') {
        setState((prev) => ({ ...prev, pythonProgress: progress.message }));
      }
    });
    return () => {
      // ipcRenderer.on returns no unsubscribe; best-effort cleanup is a no-op here.
      void unsubscribe;
    };
  }, [kyrozen, setState]);

  const checkStatus = async () => {
    setState((prev) => ({ ...prev, pythonStatus: 'checking', pythonError: '', pythonProgress: '' }));
    const result = await kyrozen.checkPythonRuntime();
    if (result.ready && result.path) {
      setState((prev) => ({ ...prev, pythonStatus: 'ready', pythonPath: result.path }));
    } else {
      setState((prev) => ({ ...prev, pythonStatus: 'error', pythonError: result.error || t.pythonNotReady }));
    }
  };

  const ensureRuntime = async () => {
    setState((prev) => ({ ...prev, pythonStatus: 'installing', pythonError: '', pythonProgress: '' }));
    const result = await kyrozen.ensurePythonRuntime();
    if (result.success && result.path) {
      setState((prev) => ({ ...prev, pythonStatus: 'ready', pythonPath: result.path }));
    } else {
      setState((prev) => ({
        ...prev,
        pythonStatus: 'error',
        pythonError: result.error || 'Unknown error',
      }));
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-center">{t.pythonTitle}</h2>
      <div className="text-sm text-slate-300">
        {state.pythonStatus === 'ready' ? (
          <div className="text-green-400">{t.pythonReady}</div>
        ) : (
          <div>{state.pythonStatus === 'idle' ? t.pythonNotReady : ''}</div>
        )}
        {state.pythonPath && <div className="mt-1 text-slate-400 break-all">{state.pythonPath}</div>}
      </div>
      {state.pythonProgress && (
        <div className="text-xs text-slate-400 font-mono bg-slate-900 p-2 rounded-lg">
          {state.pythonProgress}
        </div>
      )}
      {state.pythonError && <div className="text-sm text-red-400">{state.pythonError}</div>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={checkStatus}
          disabled={state.pythonStatus === 'checking' || state.pythonStatus === 'installing'}
          className="w-full py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white rounded-lg font-medium transition-colors"
        >
          {t.pythonCheck}
        </button>
        <button
          type="button"
          onClick={ensureRuntime}
          disabled={state.pythonStatus === 'checking' || state.pythonStatus === 'installing'}
          className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded-lg font-medium transition-colors"
        >
          {t.pythonDownload}
        </button>
      </div>
      <div className="text-xs text-slate-500">
        {t.pythonOfflineTip}
      </div>
      {state.pythonStatus === 'ready' && (
        <button
          type="button"
          onClick={onNext}
          className="w-full py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-medium transition-colors"
        >
          {t.next}
        </button>
      )}
    </div>
  );
}

function ProjectStep({
  state,
  setState,
  onNext,
  t,
}: {
  state: OnboardingState;
  setState: React.Dispatch<React.SetStateAction<OnboardingState>>;
  onNext: () => void;
  t: (typeof dict)['zh'];
}) {
  const kyrozen = useKyrozen();

  useEffect(() => {
    let mounted = true;
    kyrozen.getProjects().then((list) => {
      if (!mounted) return;
      const projects = Array.isArray(list) ? list : [];
      setState((prev) => ({
        ...prev,
        projects,
        selectedProjectId: projects[0]?.id || null,
      }));
    });
    return () => {
      mounted = false;
    };
  }, [kyrozen, setState]);

  const pickWorkspace = async () => {
    setState((prev) => ({ ...prev, workspaceError: '' }));
    try {
      let result: { workspaceRoot: string | null };
      if (state.selectedProjectId) {
        result = await kyrozen.pickWorkspace(state.selectedProjectId);
      } else {
        result = await kyrozen.pickOnboardingWorkspace();
      }
      if (result.workspaceRoot) {
        setState((prev) => ({ ...prev, workspaceRoot: result.workspaceRoot }));
      }
    } catch (err: any) {
      setState((prev) => ({ ...prev, workspaceError: err.message || String(err) }));
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-center">{t.projectTitle}</h2>
      <p className="text-sm text-slate-400">{t.projectSubtitle}</p>

      {state.projects.length > 0 ? (
        <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
          {state.projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => setState((prev) => ({ ...prev, selectedProjectId: project.id }))}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                project.id === state.selectedProjectId
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200'
              }`}
            >
              <div className="font-medium truncate">{project.name}</div>
              <div className="text-xs opacity-80 truncate">{project.current_stage}</div>
            </button>
          ))}
        </div>
      ) : (
        <div className="text-sm text-slate-400 bg-slate-800 p-3 rounded-lg">{t.noProjects}</div>
      )}

      <button
        type="button"
        onClick={pickWorkspace}
        className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
      >
        {state.workspaceRoot ? t.pickedWorkspace : t.pickWorkspace}
      </button>

      {state.workspaceRoot && (
        <div className="text-xs text-slate-400 font-mono bg-slate-900 p-2 rounded-lg break-all">
          {state.workspaceRoot}
        </div>
      )}

      {state.workspaceError && <div className="text-sm text-red-400">{state.workspaceError}</div>}

      <button
        type="button"
        onClick={onNext}
        disabled={!state.workspaceRoot}
        className="w-full py-2 bg-green-600 hover:bg-green-500 disabled:bg-green-900 text-white rounded-lg font-medium transition-colors"
      >
        {t.next}
      </button>
    </div>
  );
}

function CompleteStep({ t, onFinish }: { t: (typeof dict)['zh']; onFinish: () => void }) {
  return (
    <div className="space-y-6 text-center">
      <h2 className="text-xl font-semibold">{t.completeTitle}</h2>
      <button
        type="button"
        onClick={onFinish}
        className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
      >
        {t.enterApp}
      </button>
    </div>
  );
}

interface Props {
  onComplete: (wsToken: string) => void;
}

export function OnboardingPage({ onComplete }: Props) {
  const [state, setState] = useState<OnboardingState>({
    step: 'language',
    language: 'zh',
    serverUrl: 'https://kyrozen.chat',
    email: '',
    password: '',
    loginError: '',
    wsToken: null,
    pythonStatus: 'idle',
    pythonPath: null,
    pythonError: '',
    pythonProgress: '',
    projects: [],
    selectedProjectId: null,
    workspaceRoot: null,
    workspaceError: '',
  });

  const kyrozen = useKyrozen();
  const t = dict[state.language];

  const goTo = (step: OnboardingStep) => setState((prev) => ({ ...prev, step }));

  const selectLanguage = async (language: 'zh' | 'en') => {
    setState((prev) => ({ ...prev, language }));
    await kyrozen.saveOnboardingLanguage(language);
    goTo('login');
  };

  const finish = async () => {
    await kyrozen.completeOnboarding(state.language);
    if (state.wsToken) {
      onComplete(state.wsToken);
    }
  };

  const steps: { key: OnboardingStep; label: string }[] = [
    { key: 'language', label: state.language === 'zh' ? '语言' : 'Language' },
    { key: 'login', label: state.language === 'zh' ? '登录' : 'Sign In' },
    { key: 'python', label: 'Python' },
    { key: 'project', label: state.language === 'zh' ? '目录' : 'Directory' },
  ];

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-slate-950 p-6">
      <div className="w-full max-w-md bg-slate-900 rounded-2xl p-8 shadow-2xl border border-slate-700">
        <h1 className="text-2xl font-bold mb-6 text-center text-white">{t.welcome}</h1>

        <div className="flex items-center justify-between mb-8">
          {steps.map((s, index) => (
            <div key={s.key} className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                  steps.findIndex((x) => x.key === state.step) >= index
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-400'
                }`}
              >
                {index + 1}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={`w-8 h-0.5 mx-1 ${
                    steps.findIndex((x) => x.key === state.step) > index ? 'bg-blue-600' : 'bg-slate-700'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {state.step === 'language' && (
          <LanguageStep language={state.language} onSelect={selectLanguage} t={t} />
        )}
        {state.step === 'login' && (
          <LoginStep state={state} setState={setState} onNext={() => goTo('python')} t={t} />
        )}
        {state.step === 'python' && (
          <PythonStep state={state} setState={setState} onNext={() => goTo('project')} t={t} />
        )}
        {state.step === 'project' && (
          <ProjectStep state={state} setState={setState} onNext={() => goTo('complete')} t={t} />
        )}
        {state.step === 'complete' && <CompleteStep t={t} onFinish={finish} />}
      </div>
    </div>
  );
}
