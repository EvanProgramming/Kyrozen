import { useEffect, useMemo, useState } from 'react';

interface Props {
  projectId: string | null;
  onSelectFile: (relativePath: string) => void;
}

interface TreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children: TreeNode[];
}

function buildTree(files: string[]): TreeNode {
  const root: TreeNode = { name: '', path: '', isDirectory: true, children: [] };
  for (const file of files) {
    const parts = file.split('/');
    let current = root;
    let builtPath = '';
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      builtPath = builtPath ? `${builtPath}/${part}` : part;
      const isDirectory = i < parts.length - 1;
      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, path: builtPath, isDirectory, children: [] };
        current.children.push(child);
      }
      current = child;
    }
  }
  return root;
}

function sortNodes(nodes: TreeNode[]): TreeNode[] {
  return [...nodes].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) {
      return a.isDirectory ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
}

function TreeItem({
  node,
  depth,
  expanded,
  toggle,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  toggle: (path: string) => void;
  onSelectFile: (relativePath: string) => void;
}) {
  const isExpanded = expanded.has(node.path);
  const hasChildren = node.children.length > 0;

  return (
    <li>
      <div
        className="flex items-center text-slate-300 hover:text-blue-400 hover:bg-slate-700/50 rounded truncate"
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {node.isDirectory ? (
          <button
            type="button"
            onClick={() => toggle(node.path)}
            className="flex-1 flex items-center gap-1 px-2 py-1 text-left text-xs"
          >
            <span className="text-slate-500 select-none">{isExpanded ? '▼' : '▶'}</span>
            <span className="font-medium">{node.name}</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onSelectFile(node.path)}
            className="flex-1 px-2 py-1 text-left text-xs truncate"
            title={node.path}
          >
            {node.name}
          </button>
        )}
      </div>
      {node.isDirectory && isExpanded && hasChildren && (
        <ul className="space-y-0.5">
          {sortNodes(node.children).map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              toggle={toggle}
              onSelectFile={onSelectFile}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FileTree({ projectId, onSelectFile }: Props) {
  const [files, setFiles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setFiles([]);
    setError(null);
    setExpanded(new Set());
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

  const tree = useMemo(() => buildTree(files), [files]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

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
    <ul className="text-xs py-1">
      {sortNodes(tree.children).map((node) => (
        <TreeItem
          key={node.path}
          node={node}
          depth={0}
          expanded={expanded}
          toggle={toggle}
          onSelectFile={onSelectFile}
        />
      ))}
    </ul>
  );
}
