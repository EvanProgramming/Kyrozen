import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import {
  archiveProject,
  createProject,
  deleteProject,
  listProjects,
  renameProject,
  restoreProject,
} from '../api/projects';
import { handleApiError } from '../api/client';
import type { Project } from '../types/api';
import {
  PlusIcon,
  ArrowRightIcon,
  TrashIcon,
  PencilIcon,
} from '../components/Icons';

type ConfirmAction = {
  type: 'archive' | 'restore' | 'delete';
  project: Project;
};

const ACTION_LABELS: Record<ConfirmAction['type'], { title: string; message: string; confirm: string; variant: 'danger' | 'primary' }> = {
  archive: {
    title: '归档项目',
    message: '归档后项目将移到已归档列表，可以随时恢复。',
    confirm: '归档',
    variant: 'primary',
  },
  restore: {
    title: '恢复项目',
    message: '恢复后项目将重新变为活跃状态。',
    confirm: '恢复',
    variant: 'primary',
  },
  delete: {
    title: '删除项目',
    message: '删除后项目及其所有文件将无法恢复，请确认。',
    confirm: '删除',
    variant: 'danger',
  },
};

export function ProjectListPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await listProjects();
        setProjects(data);
      } catch (err) {
        setError(handleApiError(err));
      } finally {
        setIsLoading(false);
      }
    }
    loadProjects();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreating(true);
    try {
      const project = await createProject({
        name: newProjectName.trim(),
        description: newProjectDescription.trim(),
      });
      setProjects([project, ...projects]);
      setShowCreateForm(false);
      setNewProjectName('');
      setNewProjectDescription('');
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsCreating(false);
    }
  };

  async function handleActionConfirmed() {
    if (!confirmAction) return;
    const { type, project } = confirmAction;
    setIsActionLoading(true);
    try {
      if (type === 'archive') {
        await archiveProject(project.id);
      } else if (type === 'restore') {
        await restoreProject(project.id);
      } else if (type === 'delete') {
        await deleteProject(project.id);
      }
      const refreshed = await listProjects();
      setProjects(refreshed);
      setConfirmAction(null);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsActionLoading(false);
    }
  }

  function startRename(project: Project) {
    setEditingProjectId(project.id);
    setEditName(project.name);
  }

  function cancelRename() {
    setEditingProjectId(null);
    setEditName('');
  }

  async function handleRenameSubmit(projectId: string) {
    const trimmed = editName.trim();
    if (!trimmed) return;
    setIsRenaming(true);
    try {
      await renameProject(projectId, trimmed);
      const refreshed = await listProjects();
      setProjects(refreshed);
      setEditingProjectId(null);
      setEditName('');
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsRenaming(false);
    }
  }

  const activeProjects = projects.filter((p) => p.status !== 'archived');
  const archivedProjects = projects.filter((p) => p.status === 'archived');
  const displayedProjects = showArchived ? archivedProjects : activeProjects;

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="mb-2">我的项目</h1>
            <p className="text-warm-500">管理和继续你的产品开发项目</p>
          </div>
          <button
            onClick={() => setShowCreateForm(true)}
            className="btn-primary"
          >
            <PlusIcon className="w-4 h-4 mr-2" />
            创建项目
          </button>
        </div>

        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => setShowArchived(false)}
            className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
              !showArchived
                ? 'border-sky-500 text-sky-700'
                : 'border-transparent text-warm-500 hover:text-warm-700'
            }`}
          >
            活跃项目 ({activeProjects.length})
          </button>
          <button
            onClick={() => setShowArchived(true)}
            className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
              showArchived
                ? 'border-sky-500 text-sky-700'
                : 'border-transparent text-warm-500 hover:text-warm-700'
            }`}
          >
            已归档 ({archivedProjects.length})
          </button>
        </div>

        {showCreateForm && (
          <div className="card mb-8">
            <h3 className="mb-4">创建新项目</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="label">项目名称</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="input"
                  placeholder="例如：AI 智能音箱"
                  required
                />
              </div>
              <div>
                <label className="label">项目描述（可选）</label>
                <textarea
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  className="input min-h-[100px] resize-none"
                  placeholder="简单描述你想解决的问题..."
                  rows={3}
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={isCreating}
                  className="btn-primary disabled:opacity-60"
                >
                  {isCreating ? '创建中...' : '创建'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="btn-secondary"
                >
                  取消
                </button>
              </div>
            </form>
          </div>
        )}

        {isLoading ? (
          <div className="card text-center py-12 text-warm-500">加载中...</div>
        ) : error ? (
          <div className="card text-center py-12 text-red-600">{error}</div>
        ) : displayedProjects.length === 0 ? (
          <div className="card text-center py-16">
            <p className="text-warm-500 mb-6">
              {showArchived ? '还没有已归档项目' : '还没有项目'}
            </p>
            {!showArchived && (
              <button
                onClick={() => setShowCreateForm(true)}
                className="btn-primary inline-flex"
              >
                <PlusIcon className="w-4 h-4 mr-2" />
                创建项目
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {displayedProjects.map((project) => (
              <div
                key={project.id}
                className="card hover:shadow-soft transition-shadow group flex flex-col"
              >
                <div className="flex items-start justify-between mb-4">
                  <Link
                    to={`/projects/${project.id}`}
                    className="w-10 h-10 rounded-lg bg-sky-50 flex items-center justify-center"
                  >
                    <span className="text-sky-600 font-serif text-lg">K</span>
                  </Link>
                  <div className="flex items-center gap-1">
                    {editingProjectId !== project.id && (
                      <button
                        onClick={() => startRename(project)}
                        className="p-2 text-warm-500 hover:text-sky-600 hover:bg-sky-50 rounded-lg transition-colors"
                        title="重命名"
                      >
                        <PencilIcon className="w-5 h-5" />
                      </button>
                    )}
                    {project.status === 'archived' ? (
                      <button
                        onClick={() => setConfirmAction({ type: 'restore', project })}
                        className="p-2 text-warm-500 hover:text-sky-600 hover:bg-sky-50 rounded-lg transition-colors"
                        title="恢复项目"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                      </button>
                    ) : (
                      <button
                        onClick={() => setConfirmAction({ type: 'archive', project })}
                        className="p-2 text-warm-500 hover:text-warm-700 hover:bg-warm-100 rounded-lg transition-colors"
                        title="归档项目"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                        </svg>
                      </button>
                    )}
                    <button
                      onClick={() => setConfirmAction({ type: 'delete', project })}
                      className="p-2 text-warm-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="删除项目"
                    >
                      <TrashIcon className="w-5 h-5" />
                    </button>
                    <Link
                      to={`/projects/${project.id}`}
                      className="p-2 text-warm-400 hover:text-sky-500 rounded-lg transition-colors"
                    >
                      <ArrowRightIcon className="w-5 h-5" />
                    </Link>
                  </div>
                </div>
                {editingProjectId === project.id ? (
                  <div className="flex-1 space-y-2">
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        handleRenameSubmit(project.id);
                      }}
                      onClick={(e) => e.preventDefault()}
                    >
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        disabled={isRenaming}
                        className="input w-full"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') cancelRename();
                        }}
                      />
                      <div className="flex gap-2 mt-2">
                        <button
                          type="submit"
                          disabled={isRenaming || !editName.trim()}
                          className="btn-primary text-xs px-3 py-1.5 disabled:opacity-60"
                        >
                          {isRenaming ? '保存中...' : '保存'}
                        </button>
                        <button
                          type="button"
                          onClick={cancelRename}
                          disabled={isRenaming}
                          className="btn-secondary text-xs px-3 py-1.5"
                        >
                          取消
                        </button>
                      </div>
                    </form>
                    <div className="flex items-center gap-3 text-xs text-warm-500 pt-2">
                      <span className="px-2.5 py-1 bg-warm-100 rounded-full">
                        {project.current_stage}
                      </span>
                      <span className="px-2.5 py-1 bg-warm-100 rounded-full">
                        {project.status}
                      </span>
                    </div>
                  </div>
                ) : (
                  <Link to={`/projects/${project.id}`} className="flex-1">
                    <h3 className="font-serif text-lg text-warm-900 group-hover:text-sky-600 transition-colors mb-2">
                      {project.name}
                    </h3>
                    <p className="text-sm text-warm-500 line-clamp-2 mb-4">
                      {project.description || '暂无描述'}
                    </p>
                    <div className="flex items-center gap-3 text-xs text-warm-500">
                      <span className="px-2.5 py-1 bg-warm-100 rounded-full">
                        {project.current_stage}
                      </span>
                      <span className="px-2.5 py-1 bg-warm-100 rounded-full">
                        {project.status}
                      </span>
                    </div>
                  </Link>
                )}
              </div>
            ))}
          </div>
        )}

        {confirmAction && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
              <h3 className="text-lg font-medium text-warm-900 mb-2">
                {ACTION_LABELS[confirmAction.type].title}
              </h3>
              <p className="text-warm-600 mb-6">
                {ACTION_LABELS[confirmAction.type].message}
              </p>
              <p className="text-sm text-warm-500 mb-6 bg-warm-50 p-3 rounded-lg">
                项目：{confirmAction.project.name}
              </p>
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setConfirmAction(null)}
                  disabled={isActionLoading}
                  className="btn-secondary"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleActionConfirmed}
                  disabled={isActionLoading}
                  className={
                    ACTION_LABELS[confirmAction.type].variant === 'danger'
                      ? 'btn-danger'
                      : 'btn-primary'
                  }
                >
                  {isActionLoading ? '处理中...' : ACTION_LABELS[confirmAction.type].confirm}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
