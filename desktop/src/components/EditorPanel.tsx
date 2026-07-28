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
    <div className="absolute inset-0 z-20 bg-paper flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 bg-surface border-b border-line">
        <div className="text-sm truncate text-ink-soft">
          编辑：<span className="font-medium text-ink">{relativePath}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="btn-primary text-xs px-3 py-1"
          >
            {saving ? '保存中...' : '保存'}
          </button>
          <button
            onClick={onClose}
            className="btn-secondary text-xs px-3 py-1"
          >
            关闭
          </button>
        </div>
      </div>
      {message && (
        <div className="px-4 py-1 text-xs bg-surface border-b border-line text-ink-soft">
          {message}
        </div>
      )}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        disabled={loading}
        className="flex-1 w-full p-4 bg-paper text-ink font-mono text-sm resize-none focus:outline-none"
        spellCheck={false}
      />
    </div>
  );
}
