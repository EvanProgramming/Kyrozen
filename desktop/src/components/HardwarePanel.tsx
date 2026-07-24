import { useEffect, useState } from 'react';

interface ToolInfo {
  command: string;
  path: string | null;
  bundled: boolean;
  version: string | null;
}

export function HardwarePanel() {
  const kyrozen = window.kyrozen!;
  const [tools, setTools] = useState<Record<string, ToolInfo>>({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const result = await kyrozen.getHardwareToolStatus();
      if (result.success) {
        setTools(result.tools);
      }
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  const handleCheckUpdates = async () => {
    setLoading(true);
    setMessage('正在检查硬件工具链更新...');
    try {
      const result = await kyrozen.checkHardwareUpdates();
      if (result.success) {
        const updated = result.results?.filter((r) => r.updated).map((r) => r.tool).join(', ');
        setMessage(updated ? `已更新: ${updated}` : '所有工具均为最新');
        await loadStatus();
      } else {
        setMessage(result.error || '检查失败');
      }
    } catch {
      setMessage('检查失败');
    }
    setLoading(false);
  };

  const handleInstallCores = async () => {
    setLoading(true);
    setMessage('正在安装常用核心/平台...');
    try {
      const result = await kyrozen.installCommonCores();
      setMessage(result.success ? '安装完成' : result.error || '安装失败');
    } catch {
      setMessage('安装失败');
    }
    setLoading(false);
  };

  const arduino = tools['arduino-cli'];
  const pio = tools['pio'];

  return (
    <div className="border-t border-slate-700 pt-2">
      <div className="px-2 font-medium text-slate-300 mb-1">硬件工具链</div>
      <div className="space-y-1.5 text-xs mb-2">
        <div className="flex items-center justify-between text-slate-400">
          <span>Arduino CLI</span>
          <span className={arduino?.path ? 'text-green-400' : 'text-slate-500'}>
            {arduino?.version || (arduino?.path ? '就绪' : '未就绪')}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-400">
          <span>PlatformIO</span>
          <span className={pio?.path ? 'text-green-400' : 'text-slate-500'}>
            {pio?.version || (pio?.path ? '就绪' : '未就绪')}
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={handleCheckUpdates}
          disabled={loading}
          className="w-full py-1 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white rounded text-xs transition-colors"
        >
          检查更新
        </button>
        <button
          type="button"
          onClick={handleInstallCores}
          disabled={loading}
          className="w-full py-1 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 text-white rounded text-xs transition-colors"
        >
          安装常用核心
        </button>
      </div>
      {message && <div className="mt-1.5 text-xs text-slate-400">{message}</div>}
    </div>
  );
}
