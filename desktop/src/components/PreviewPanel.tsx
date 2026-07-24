interface Props {
  url: string;
  onClose: () => void;
}

export function PreviewPanel({ url, onClose }: Props) {
  return (
    <div className="w-[45%] min-w-[360px] max-w-[720px] flex flex-col border-l border-slate-700 bg-slate-900">
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700">
        <div className="text-xs text-slate-300 truncate flex-1 mr-2">
          预览：<span className="font-medium">{url}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.kyrozen?.openPreview(url, 'window')}
            className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-100 rounded"
            title="在独立窗口中打开"
          >
            新窗口
          </button>
          <button
            onClick={() => window.kyrozen?.openPreview(url, 'external')}
            className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-100 rounded"
            title="在系统浏览器中打开"
          >
            浏览器
          </button>
          <button
            onClick={onClose}
            className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-100 rounded"
          >
            关闭
          </button>
        </div>
      </div>
      <div className="flex-1 relative">
        <iframe
          src={url}
          sandbox="allow-scripts allow-same-origin allow-forms"
          className="absolute inset-0 w-full h-full border-0 bg-white"
          title="Kyrozen preview"
        />
      </div>
    </div>
  );
}
