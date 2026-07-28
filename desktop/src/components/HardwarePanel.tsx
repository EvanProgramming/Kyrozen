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
    const unsubscribe = kyrozen.onHardwareToolStatus((nextTools) => setTools(nextTools));
    return unsubscribe;
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
    <div className="border-t border-line pt-2">
      <div className="px-2 font-medium text-ink-soft mb-1">硬件工具链</div>
      <div className="space-y-1.5 text-xs mb-2">
        <div className="flex items-center justify-between text-ink-faint">
          <span>Arduino CLI</span>
          <span className={arduino?.path ? 'text-success' : 'text-ink-ghost'}>
            {arduino?.version || (arduino?.path ? '就绪' : '未就绪')}
          </span>
        </div>
        <div className="flex items-center justify-between text-ink-faint">
          <span>PlatformIO</span>
          <span className={pio?.path ? 'text-success' : 'text-ink-ghost'}>
            {pio?.version || (pio?.path ? '就绪' : '未就绪')}
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={handleCheckUpdates}
          disabled={loading}
          className="btn-secondary w-full py-1 text-xs"
        >
          检查更新
        </button>
        <button
          type="button"
          onClick={handleInstallCores}
          disabled={loading}
          className="btn-secondary w-full py-1 text-xs"
        >
          安装常用核心
        </button>
      </div>
      {message && <div className="mt-1.5 text-xs text-ink-faint">{message}</div>}
    </div>
  );
}
