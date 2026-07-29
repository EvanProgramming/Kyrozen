import { useState } from 'react';

interface SearchResult {
  projectId: string;
  relativePath: string;
  matchType: 'filename' | 'content';
  snippet?: string;
}

interface Props {
  onOpenFile?: (projectId: string, relativePath: string) => void;
}

export function SearchPanel({ onOpenFile }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim() || !window.kyrozen) return;
    setIsSearching(true);
    setError(null);
    try {
      const response = await window.kyrozen.searchAcrossProjects(query.trim(), { maxResults: 30 });
      setResults(response.results || []);
    } catch (err: any) {
      setError(err.message || '搜索失败');
    } finally {
      setIsSearching(false);
    }
  };

  // UI cleanup: rendered inside an expandable dropdown next to "我的项目",
  // so no standalone title — just the input and results.
  return (
    <div className="p-3">
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="跨项目搜索文件或内容…"
          className="input flex-1 px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={handleSearch}
          disabled={isSearching || !query.trim()}
          className="btn-primary px-2 py-1 text-xs"
        >
          {isSearching ? '...' : '搜索'}
        </button>
      </div>

      {error && <div className="text-xs text-danger mb-2">{error}</div>}

      <div className="max-h-48 overflow-y-auto space-y-1">
        {results.map((result, idx) => (
          <button
            key={`${result.projectId}-${result.relativePath}-${idx}`}
            type="button"
            onClick={() => onOpenFile?.(result.projectId, result.relativePath)}
            className="w-full text-left px-2 py-1.5 bg-surface border border-line hover:bg-paper-sink rounded-sm text-xs transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <span className="text-ink-ghost shrink-0">{result.projectId}:</span>
              <span className="text-accent truncate">{result.relativePath}</span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 bg-paper-edge rounded-sm text-ink-faint shrink-0">
                {result.matchType === 'filename' ? '文件名' : '内容'}
              </span>
            </div>
            {result.snippet && (
              <div className="mt-1 text-ink-faint truncate">{result.snippet}</div>
            )}
          </button>
        ))}
        {results.length === 0 && !isSearching && query && (
          <div className="text-xs text-ink-ghost px-2">未找到结果</div>
        )}
      </div>
    </div>
  );
}
