import { useEffect, useState } from 'react';

interface Props {
  projectId: string | null;
  onSelectFile: (relativePath: string) => void;
}

export function FileTree({ projectId, onSelectFile }: Props) {
  const [files, setFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFiles([]);
    setError(null);
    if (!projectId || !window.kyrozen) return;
    let cancelled = false;
    window.kyrozen
      .listFiles(projectId)
      .then((result) => {
        if (cancelled) return;
        if (result.error) {
          setError(result.error);
        } else {
          setFiles(result.files || []);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || '加载文件失败');
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (!projectId) {
    return (
      <div className="text-xs text-slate-400 p-2">
        选择项目后查看本地文件
      </div>
    );
  }

  if (error) {
    return <div className="text-xs text-red-400 p-2">{error}</div>;
  }

  if (files.length === 0) {
    return (
      <div className="text-xs text-slate-400 p-2">
        工作区暂无文件
      </div>
    );
  }

  return (
    <ul className="text-xs space-y-1 p-2">
      {files.map((file) => (
        <li key={file}>
          <button
            onClick={() => onSelectFile(file)}
            className="w-full text-left text-slate-300 hover:text-blue-400 hover:bg-slate-700/50 px-2 py-1 rounded truncate"
            title={file}
          >
            {file}
          </button>
        </li>
      ))}
    </ul>
  );
}
