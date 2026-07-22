import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { createProject, listProjects } from '../api/projects';
import { handleApiError } from '../api/client';
import type { Project } from '../types/api';
import { PlusIcon, ArrowRightIcon } from '../components/Icons';

export function ProjectListPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
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
        ) : projects.length === 0 ? (
          <div className="card text-center py-16">
            <p className="text-warm-500 mb-6">还没有项目</p>
            <button
              onClick={() => setShowCreateForm(true)}
              className="btn-primary inline-flex"
            >
              <PlusIcon className="w-4 h-4 mr-2" />
              创建项目
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {projects.map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="card hover:shadow-soft transition-shadow group"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-lg bg-sky-50 flex items-center justify-center">
                    <span className="text-sky-600 font-serif text-lg">K</span>
                  </div>
                  <ArrowRightIcon className="w-5 h-5 text-warm-400 group-hover:text-sky-500 transition-colors" />
                </div>
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
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
