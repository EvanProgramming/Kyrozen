import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
// Dashboard stat cards link to the projects list
import { Layout } from '../components/Layout';
import { listProjects } from '../api/projects';
import { handleApiError } from '../api/client';
import type { Project } from '../types/api';
import { PlusIcon, ArrowRightIcon } from '../components/Icons';

export function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

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

  const recentProjects = projects.slice(0, 5);
  const activeCount = projects.filter((p) => p.status === 'active').length;

  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-10">
          <h1 className="mb-3">控制台</h1>
          <p className="text-warm-500">管理和追踪你的产品开发旅程</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
          <Link to="/projects" className="card hover:shadow-soft transition-shadow">
            <p className="text-sm text-warm-500 mb-1">总项目数</p>
            <p className="text-4xl font-serif text-warm-900">{projects.length}</p>
          </Link>
          <Link to="/projects" className="card hover:shadow-soft transition-shadow">
            <p className="text-sm text-warm-500 mb-1">进行中</p>
            <p className="text-4xl font-serif text-sky-600">{activeCount}</p>
          </Link>
          <Link to="/projects" className="card hover:shadow-soft transition-shadow">
            <p className="text-sm text-warm-500 mb-1">已完成</p>
            <p className="text-4xl font-serif text-warm-900">
              {projects.filter((p) => p.status === 'completed').length}
            </p>
          </Link>
        </div>

        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl">最近项目</h2>
          <Link to="/projects" className="text-sm text-sky-600 hover:text-sky-700 font-medium">
            查看全部
          </Link>
        </div>

        {isLoading ? (
          <div className="card text-center py-12 text-warm-500">加载中...</div>
        ) : error ? (
          <div className="card text-center py-12 text-red-600">{error}</div>
        ) : recentProjects.length === 0 ? (
          <div className="card text-center py-16">
            <p className="text-warm-500 mb-6">还没有项目，创建第一个开始吧</p>
            <Link to="/projects" className="btn-primary inline-flex">
              <PlusIcon className="w-4 h-4 mr-2" />
              创建项目
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {recentProjects.map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="card flex items-center justify-between hover:shadow-soft transition-shadow group"
              >
                <div>
                  <h3 className="font-serif text-lg text-warm-900 group-hover:text-sky-600 transition-colors">
                    {project.name}
                  </h3>
                  <p className="text-sm text-warm-500 mt-1">
                    {project.current_stage} · {project.status}
                  </p>
                </div>
                <ArrowRightIcon className="w-5 h-5 text-warm-400 group-hover:text-sky-500 transition-colors" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
