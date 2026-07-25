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

  return (
    <div className="p-3 border-t border-slate-700">
      <div className="text-xs font-medium text-slate-300 mb-2">跨项目搜索</div>
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索文件或内容..."
          className="flex-1 px-2 py-1 bg-slate-900 border border-slate-600 rounded text-xs text-slate-200 focus:outline-none focus:border-blue-500"
        />
        <button
          type="button"
          onClick={handleSearch}
          disabled={isSearching || !query.trim()}
          className="px-2 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded text-xs transition-colors"
        >
          {isSearching ? '...' : '搜索'}
        </button>
      </div>

      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      <div className="max-h-48 overflow-y-auto space-y-1">
        {results.map((result, idx) => (
          <button
            key={`${result.projectId}-${result.relativePath}-${idx}`}
            type="button"
            onClick={() => onOpenFile?.(result.projectId, result.relativePath)}
            className="w-full text-left px-2 py-1.5 bg-slate-800 hover:bg-slate-700 rounded text-xs transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 shrink-0">{result.projectId}:</span>
              <span className="text-blue-300 truncate">{result.relativePath}</span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 bg-slate-700 rounded text-slate-300 shrink-0">
                {result.matchType === 'filename' ? '文件名' : '内容'}
              </span>
            </div>
            {result.snippet && (
              <div className="mt-1 text-slate-400 truncate">{result.snippet}</div>
            )}
          </button>
        ))}
        {results.length === 0 && !isSearching && query && (
          <div className="text-xs text-slate-500 px-2">未找到结果</div>
        )}
      </div>
    </div>
  );
}
