import { useEffect, useRef, useState } from 'react';

interface Props {
  onLogin: (wsToken: string, serverUrl: string) => void;
}

export function LoginPage({ onLogin }: Props) {
  const [mode, setMode] = useState<'password' | 'pairing'>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [serverUrl, setServerUrl] = useState('https://kyrozen.chat');
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [isPairing, setIsPairing] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (window.kyrozen) {
      window.kyrozen.getServerUrl().then((url) => {
        if (url) setServerUrl(url);
      }).catch(() => {
        // keep default
      });
    }
  }, []);

  const clearPollTimer = () => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  };

  useEffect(() => {
    return () => clearPollTimer();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!window.kyrozen) return;
    const result = await window.kyrozen.login(email, password, serverUrl);
    if (result.success && result.wsToken) {
      onLogin(result.wsToken, serverUrl);
    }
  };

  const startPairing = async () => {
    if (!window.kyrozen) return;
    setIsPairing(true);
    setPairingError(null);
    setPairingCode(null);
    clearPollTimer();
    const result = await window.kyrozen.startPairing(serverUrl);
    if (!result.success || !result.code) {
      setPairingError(result.error || '获取配对码失败');
      setIsPairing(false);
      return;
    }
    setPairingCode(result.code);
    schedulePoll(result.code);
  };

  const schedulePoll = (code: string) => {
    const pollOnce = async () => {
      if (!window.kyrozen) return;
      const result = await window.kyrozen.pollPairing(serverUrl, code);
      if (!result.success) {
        setPairingError(result.error || '轮询失败');
        setIsPairing(false);
        return;
      }
      if (result.ready && result.wsToken) {
        clearPollTimer();
        onLogin(result.wsToken, serverUrl);
        return;
      }
      pollTimer.current = setTimeout(() => pollOnce(), 2000);
    };
    pollOnce();
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="w-full max-w-sm bg-slate-800 rounded-2xl p-8 shadow-2xl border border-slate-700">
        <h1 className="text-2xl font-bold mb-2 text-center">Kyrozen</h1>
        <p className="text-slate-400 text-center mb-2">登录到 Kyrozen</p>
        <p className="text-xs text-slate-500 text-center mb-6">服务器：{serverUrl}</p>

        <div className="flex rounded-lg bg-slate-900 p-1 mb-6">
          <button
            type="button"
            onClick={() => setMode('password')}
            className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
              mode === 'password' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            账号密码
          </button>
          <button
            type="button"
            onClick={() => setMode('pairing')}
            className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
              mode === 'pairing' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            配对码
          </button>
        </div>

        <div className="space-y-4">
          {mode === 'password' ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-1">邮箱</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">密码</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <button
                type="submit"
                className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
              >
                登录
              </button>
            </form>
          ) : (
            <div className="space-y-4">
              {pairingCode ? (
                <div className="text-center space-y-3">
                  <div className="text-sm text-slate-300">在已登录的网站端输入以下配对码</div>
                  <div className="text-3xl font-mono font-bold tracking-widest text-blue-400 bg-slate-900 py-3 rounded-lg border border-slate-600">
                    {pairingCode}
                  </div>
                  <div className="text-xs text-slate-500">配对码 10 分钟内有效，等待网站确认中...</div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={startPairing}
                  disabled={isPairing}
                  className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded-lg font-medium transition-colors"
                >
                  {isPairing ? '正在获取配对码...' : '生成配对码'}
                </button>
              )}
              {pairingError && <div className="text-sm text-red-400">{pairingError}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
