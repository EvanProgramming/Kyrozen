import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Layout } from '../components/Layout';
import { getProject, getProjectState } from '../api/projects';
import { handleApiError } from '../api/client';
import type { Project, ProjectState } from '../types/api';
import { ChatIcon, DocumentIcon, SparklesIcon } from '../components/Icons';

const STAGES = [
  { id: 'problem_discovery', label: '问题发现', mode: 'discovery' },
  { id: 'market_research', label: '市场调研', mode: 'market_research' },
  { id: 'product_definition', label: '产品规划', mode: 'planning' },
  { id: 'solution_design', label: '方案设计', mode: 'planning' },
  { id: 'development', label: '软件开发', mode: 'development' },
  { id: 'hardware', label: '硬件开发', mode: 'hardware' },
  { id: 'testing', label: '测试验证', mode: 'testing' },
  { id: 'iteration', label: '迭代优化', mode: 'learning' },
];

export function ProjectWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [projectState, setProjectState] = useState<ProjectState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'chat'>('overview');

  useEffect(() => {
    if (!projectId) return;

    async function loadData() {
      try {
        const [projectData, stateData] = await Promise.all([
          getProject(projectId!),
          getProjectState(projectId!),
        ]);
        setProject(projectData);
        setProjectState(stateData);
      } catch (err) {
        setError(handleApiError(err));
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [projectId]);

  if (isLoading) {
    return (
      <Layout>
        <div className="card text-center py-20 text-warm-500">加载项目中...</div>
      </Layout>
    );
  }

  if (error || !project) {
    return (
      <Layout>
        <div className="card text-center py-20 text-red-600">
          {error || '项目不存在'}
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <span className="px-3 py-1 bg-sky-50 text-sky-700 text-xs font-medium rounded-full">
              {project.current_stage}
            </span>
            <span className="px-3 py-1 bg-warm-100 text-warm-600 text-xs rounded-full">
              {project.status}
            </span>
          </div>
          <h1 className="mb-2">{project.name}</h1>
          <p className="text-warm-500">{project.description || '暂无项目描述'}</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="card p-4">
              <h3 className="text-sm font-medium text-warm-500 uppercase tracking-wide mb-4">
                开发阶段
              </h3>
              <nav className="space-y-1">
                {STAGES.map((stage) => (
                  <button
                    key={stage.id}
                    onClick={() => setActiveTab('chat')}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors text-left ${
                      project.current_stage === stage.id
                        ? 'bg-sky-50 text-sky-700 font-medium'
                        : 'text-warm-600 hover:bg-warm-50'
                    }`}
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        project.current_stage === stage.id ? 'bg-sky-500' : 'bg-warm-300'
                      }`}
                    />
                    {stage.label}
                  </button>
                ))}
              </nav>
            </div>
          </div>

          {/* Main content */}
          <div className="lg:col-span-3 space-y-6">
            {activeTab === 'overview' ? (
              <>
                {/* Next Action Card */}
                <div className="card bg-gradient-to-br from-sky-50 to-white border-sky-100">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-sky-500 flex items-center justify-center flex-shrink-0">
                      <SparklesIcon className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg mb-2">推荐下一步</h3>
                      {projectState?.next_action ? (
                        <>
                          <p className="text-warm-900 font-medium mb-2">
                            {projectState.next_action.action}
                          </p>
                          <p className="text-sm text-warm-500 mb-4">
                            {projectState.next_action.reason}
                          </p>
                          <button
                            onClick={() => setActiveTab('chat')}
                            className="btn-primary text-sm"
                          >
                            <ChatIcon className="w-4 h-4 mr-2" />
                            开始对话
                          </button>
                        </>
                      ) : (
                        <p className="text-warm-500">当前阶段暂无明确推荐，可与 AI 助手交流继续推进。</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Project Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <DocumentIcon className="w-5 h-5 text-sky-500" />
                      <h3 className="text-lg">项目目标</h3>
                    </div>
                    <p className="text-warm-600">
                      {project.goal || '尚未设定项目目标'}
                    </p>
                  </div>

                  <div className="card">
                    <div className="flex items-center gap-3 mb-4">
                      <SparklesIcon className="w-5 h-5 text-sky-500" />
                      <h3 className="text-lg">下一步计划</h3>
                    </div>
                    <p className="text-warm-600">
                      {project.next_steps || '暂无下一步计划'}
                    </p>
                  </div>
                </div>

                {/* Progress */}
                <div className="card">
                  <h3 className="text-lg mb-4">项目进度</h3>
                  <div className="w-full h-2 bg-warm-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-sky-500 rounded-full transition-all"
                      style={{ width: `${project.progress}%` }}
                    />
                  </div>
                  <p className="text-sm text-warm-500 mt-2">{project.progress}% 完成</p>
                </div>
              </>
            ) : (
              <div className="card min-h-[500px]">
                <div className="flex items-center gap-3 mb-6">
                  <ChatIcon className="w-5 h-5 text-sky-500" />
                  <h3 className="text-lg">AI 助手</h3>
                </div>
                <div className="bg-warm-50 rounded-xl p-8 text-center">
                  <p className="text-warm-500 mb-4">
                    聊天功能将在后续步骤接入 Kyrozen Agent Runtime。
                  </p>
                  <p className="text-sm text-warm-400">
                    当前阶段：{project.current_stage}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}
