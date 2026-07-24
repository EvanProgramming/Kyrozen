import { useEffect, useState } from 'react';

interface Props {
  projectId: string;
  relativePath: string;
  onClose: () => void;
}

export function EditorPanel({ projectId, relativePath, onClose }: Props) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setMessage(null);
    if (!window.kyrozen) return;
    window.kyrozen
      .readFile(projectId, relativePath)
      .then((result) => {
        setContent(result.error ? `读取失败：${result.error}` : result.content);
      })
      .catch((err) => setContent(`读取失败：${err?.message || err}`))
      .finally(() => setLoading(false));
  }, [projectId, relativePath]);

  const handleSave = async () => {
    if (!window.kyrozen || loading) return;
    setSaving(true);
    setMessage(null);
    try {
      const result = await window.kyrozen.saveFile(projectId, relativePath, content);
      setMessage(result.success ? '保存成功' : `保存失败：${result.error}`);
    } catch (err: any) {
      setMessage(`保存失败：${err?.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="absolute inset-0 z-20 bg-slate-900/95 flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700">
        <div className="text-sm truncate">
          编辑：<span className="font-medium">{relativePath}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs rounded"
          >
            {saving ? '保存中...' : '保存'}
          </button>
          <button
            onClick={onClose}
            className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-xs rounded"
          >
            关闭
          </button>
        </div>
      </div>
      {message && (
        <div className="px-4 py-1 text-xs bg-slate-800 border-b border-slate-700 text-slate-300">
          {message}
        </div>
      )}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        disabled={loading}
        className="flex-1 w-full p-4 bg-slate-950 text-slate-200 font-mono text-sm resize-none focus:outline-none"
        spellCheck={false}
      />
    </div>
  );
}
