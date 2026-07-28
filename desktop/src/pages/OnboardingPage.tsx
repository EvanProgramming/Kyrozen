import { useEffect, useState } from 'react';

export type OnboardingStep = 'language' | 'python' | 'project' | 'complete';

interface Project {
  id: string;
  name: string;
  current_stage: string;
  description?: string;
}

interface OnboardingState {
  step: OnboardingStep;
  language: 'zh' | 'en';
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
    pythonTitle: '准备 Python 运行时',
    pythonReady: 'Python 运行时已就绪',
    pythonNotReady: '尚未安装 Python 运行时',
    pythonCheck: '检查状态',
    pythonDownload: '下载并安装',
    pythonOffline: '离线安装',
    pythonOfflineTip: '若下载失败，可访问 python-build-standalone releases 手动下载对应版本并解压。',
    projectTitle: '选择项目目录',
    projectSubtitle: '从云端项目列表中选择一个项目，或先使用默认目录。',
    noProjects: '暂无云端项目，将使用默认目录。',
    selectProject: '选择项目',
    pickWorkspace: '选择本地目录',
    pickedWorkspace: '已选择目录',
    completeTitle: '准备就绪',
    enterApp: '进入 Kyrozen',
  },
  en: {
    welcome: 'Welcome to Kyrozen',
    languageTitle: 'Choose Language',
    next: 'Next',
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
      <h2 className="font-hand text-2xl leading-none text-center text-ink">{t.languageTitle}</h2>
      <div className="grid grid-cols-2 gap-4">
        <button
          type="button"
          onClick={() => onSelect('zh')}
          className={`px-6 py-4 rounded border text-lg font-medium transition-colors ${
            language === 'zh'
              ? 'bg-accent border-accent text-white'
              : 'bg-surface border-line-strong text-ink-soft hover:bg-paper-sink'
          }`}
        >
          中文
        </button>
        <button
          type="button"
          onClick={() => onSelect('en')}
          className={`px-6 py-4 rounded border text-lg font-medium transition-colors ${
            language === 'en'
              ? 'bg-accent border-accent text-white'
              : 'bg-surface border-line-strong text-ink-soft hover:bg-paper-sink'
          }`}
        >
          English
        </button>
      </div>
    </div>
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
      unsubscribe();
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
      <h2 className="font-hand text-2xl leading-none text-center text-ink">{t.pythonTitle}</h2>
      <div className="text-sm text-ink-soft">
        {state.pythonStatus === 'ready' ? (
          <div className="text-success">{t.pythonReady}</div>
        ) : (
          <div>{state.pythonStatus === 'idle' ? t.pythonNotReady : ''}</div>
        )}
        {state.pythonPath && <div className="mt-1 text-ink-faint break-all">{state.pythonPath}</div>}
      </div>
      {state.pythonProgress && (
        <div className="text-xs text-ink-soft font-mono bg-paper-sink border border-line p-2 rounded-sm">
          {state.pythonProgress}
        </div>
      )}
      {state.pythonError && <div className="text-sm text-danger">{state.pythonError}</div>}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={checkStatus}
          disabled={state.pythonStatus === 'checking' || state.pythonStatus === 'installing'}
          className="btn-secondary w-full"
        >
          {t.pythonCheck}
        </button>
        <button
          type="button"
          onClick={ensureRuntime}
          disabled={state.pythonStatus === 'checking' || state.pythonStatus === 'installing'}
          className="btn-primary w-full"
        >
          {t.pythonDownload}
        </button>
      </div>
      <div className="text-xs text-ink-ghost">
        {t.pythonOfflineTip}
      </div>
      {state.pythonStatus === 'ready' && (
        <button
          type="button"
          onClick={onNext}
          className="btn-success w-full"
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
    const loadProjects = () => kyrozen.getProjects().then((list) => {
      if (!mounted) return;
      const projects = Array.isArray(list) ? list : [];
      setState((prev) => ({
        ...prev,
        projects,
        selectedProjectId: projects[0]?.id || null,
      }));
    });
    void loadProjects();
    const unsubscribe = kyrozen.onConnectionChange((connection) => {
      if (connection === 'connected') void loadProjects();
    });
    return () => {
      mounted = false;
      unsubscribe();
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
      <h2 className="font-hand text-2xl leading-none text-center text-ink">{t.projectTitle}</h2>
      <p className="text-sm text-ink-faint">{t.projectSubtitle}</p>

      {state.projects.length > 0 ? (
        <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
          {state.projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => setState((prev) => ({ ...prev, selectedProjectId: project.id }))}
              className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors border-l-2 ${
                project.id === state.selectedProjectId
                  ? 'bg-accent-soft border-accent text-ink'
                  : 'bg-surface border-transparent hover:bg-paper-sink text-ink-soft'
              }`}
            >
              <div className="font-medium truncate">{project.name}</div>
              <div className="text-xs text-ink-faint truncate">{project.current_stage}</div>
            </button>
          ))}
        </div>
      ) : (
        <div className="text-sm text-ink-faint bg-paper-sink border border-line p-3 rounded-sm">{t.noProjects}</div>
      )}

      <button
        type="button"
        onClick={pickWorkspace}
        className="btn-primary w-full"
      >
        {state.workspaceRoot ? t.pickedWorkspace : t.pickWorkspace}
      </button>

      {state.workspaceRoot && (
        <div className="text-xs text-ink-soft font-mono bg-paper-sink border border-line p-2 rounded-sm break-all">
          {state.workspaceRoot}
        </div>
      )}

      {state.workspaceError && <div className="text-sm text-danger">{state.workspaceError}</div>}

      <button
        type="button"
        onClick={onNext}
        disabled={!state.workspaceRoot}
        className="btn-success w-full"
      >
        {t.next}
      </button>
    </div>
  );
}

function CompleteStep({ t, onFinish }: { t: (typeof dict)['zh']; onFinish: () => void }) {
  return (
    <div className="space-y-6 text-center">
      <h2 className="font-hand text-2xl leading-none text-ink">{t.completeTitle}</h2>
      <button
        type="button"
        onClick={onFinish}
        className="btn-primary w-full"
      >
        {t.enterApp}
      </button>
    </div>
  );
}

interface Props {
  onComplete: () => void;
}

export function OnboardingPage({ onComplete }: Props) {
  const [state, setState] = useState<OnboardingState>({
    step: 'language',
    language: 'zh',
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
    goTo('python');
  };

  const finish = async () => {
    await kyrozen.completeOnboarding(state.language);
    onComplete();
  };

  const steps: { key: OnboardingStep; label: string }[] = [
    { key: 'language', label: state.language === 'zh' ? '语言' : 'Language' },
    { key: 'python', label: 'Python' },
    { key: 'project', label: state.language === 'zh' ? '目录' : 'Directory' },
  ];

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-paper p-6">
      <div className="w-full max-w-md panel p-8">
        <h1 className="font-hand text-3xl leading-none mb-6 text-center text-ink">{t.welcome}</h1>

        <div className="flex items-center justify-between mb-8">
          {steps.map((s, index) => (
            <div key={s.key} className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                  steps.findIndex((x) => x.key === state.step) >= index
                    ? 'bg-accent text-white'
                    : 'bg-paper-edge text-ink-faint'
                }`}
              >
                {index + 1}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={`w-8 h-0.5 mx-1 ${
                    steps.findIndex((x) => x.key === state.step) > index ? 'bg-accent' : 'bg-paper-edge'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {state.step === 'language' && (
          <LanguageStep language={state.language} onSelect={selectLanguage} t={t} />
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
