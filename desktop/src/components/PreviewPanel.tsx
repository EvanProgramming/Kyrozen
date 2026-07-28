interface Props {
  url: string;
  onClose: () => void;
}

export function PreviewPanel({ url, onClose }: Props) {
  return (
    <div className="w-[45%] min-w-[360px] max-w-[720px] flex flex-col border-l border-line bg-paper">
      <div className="flex items-center justify-between px-3 py-2 bg-surface border-b border-line">
        <div className="text-xs text-ink-soft truncate flex-1 mr-2">
          预览：<span className="font-medium text-ink">{url}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.kyrozen?.openPreview(url, 'window')}
            className="btn-ghost text-xs px-2 py-1"
            title="在独立窗口中打开"
          >
            新窗口
          </button>
          <button
            onClick={() => window.kyrozen?.openPreview(url, 'external')}
            className="btn-ghost text-xs px-2 py-1"
            title="在系统浏览器中打开"
          >
            浏览器
          </button>
          <button
            onClick={onClose}
            className="btn-ghost text-xs px-2 py-1"
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
