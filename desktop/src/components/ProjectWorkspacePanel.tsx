import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props { projectId: string; onClose: () => void }
type Row = Record<string, unknown>;
type RetryAction = { label: string; run: () => Promise<void> };
type WorkspaceData = {
  project?: Row;
  state?: Row;
  decisions?: Row[];
  artifacts?: Row[];
  tasks?: Row[];
  local?: Row;
  phase2?: Row;
  sections?: Row;
};

const TABS = [
  ['overview', '项目主页', '项目目标、阶段与本地成果概览'],
  ['decisions', '决策中心', '方案确认、撤销与受影响任务'],
  ['procurement', '采购中心', 'BOM、替代件与采购状态'],
  ['maker', 'Maker 模式', '按步骤装配并记录安全确认'],
  ['testing', '测试中心', '用例、失败、缺陷与回归'],
  ['improvements', '改进中心', '建议、证据、收益与风险'],
  ['feedback', '反馈中心', '记录真实使用反馈'],
] as const;

const LABELS: Record<string, string> = {
  name: '项目名称', description: '项目描述', goal: '项目目标', initial_idea: '最初想法',
  current_stage: '当前阶段', stage: '当前阶段', progress: '完成进度', next_steps: '下一步',
  problem_statement: '问题定义', evidence_summary: '已有证据', affected_users: '目标用户',
  recommendation: '结论建议', market_status: '市场现状', market_gap: '市场机会',
  product_goal: '产品目标', target_user: '目标用户', value_proposition: '核心价值',
  mvp_features: 'MVP 功能', out_of_scope: '本次不做', functional_requirements: '功能要求',
  risks: '风险', budget: '预算', status: '状态', title: '标题', decision: '决定', reason: '原因',
  next_action: '建议下一步', action: '行动', target_mode: '对应阶段', result: '结果',
  confidence: '可信度', summary: '摘要', missing_dimensions: '还需澄清', question: '下一条问题',
  feature_records: '功能验证', overall_success: '整体结果', preview_url: '预览地址',
  workspace_root: '本地工作区', files: '本地文件', deliverables: '本地交付物', software: '软件生成结果', stagegate: '本地阶段门禁',
  project_type: '项目类型', workflow_version: '流程版本', type_confirmed: '类型已确认', source_count: '研究来源',
  source_coverage: '来源覆盖率', provider_status: '来源状态', citation_count: '引用数量', freshness: '来源新鲜度',
  fact_types: '事实/推断/未知', polarities: '正面/负面/混合/未知', conflict_count: '冲突证据',
  latest_run: '最近运行', retry_queue: '重试队列', attempts: '尝试次数', errors: '失败详情', run_id: '运行编号',
  hardware: '硬件轨道', protocol: '协议轨道', integration: '集成轨道',
  state: '轨道状态', completed_stages: '已完成阶段', next_stage: '下一阶段',
  active_count: '有效证据', artifact_count: '资料数量', blocked_reason: '阻塞原因', status_detail: '状态说明',
};

const STAGE_NAMES: Record<string, string> = {
  problem_discovery: '问题探索', market_research: '市场调研', product_definition: '产品定义',
  solution_design: '方案设计', protocol_design: '协议设计', development: '软件开发',
  hardware_design: '硬件方案', procurement: '采购/BOM', maker: 'Maker 装配', firmware: '固件',
  hardware_testing: '硬件测试', integration_testing: '软硬件集成测试', testing: '测试验证', iteration: '迭代改进',
  discovery: '问题探索', planning: '产品规划', learning: '学习改进',
};

const TRACK_NAMES: Record<string, string> = {
  software: '软件', hardware: '硬件', protocol: '协议', integration: '集成',
};

function empty(value: unknown) {
  return value == null || value === '' || (Array.isArray(value) && value.length === 0)
    || (typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0);
}

// Internal-only keys that should never reach the user-facing canvas.
const SANITIZE_KEYS = new Set([
  'stagegate', 'software', 'deliverables', 'files', 'records', 'skips',
  'events', 'tasks', 'raw', 'blobs', 'runtime', 'debug', 'metadata', 'internal',
  'verifications', 'gate_state', 'question_dimension', 'dimension', 'blocked_entry_reason',
  'missing_dimensions', 'question', 'log', 'metrics', 'trace', 'debug_info',
  'raw_response', 'tool_calls', 'intermediate', 'notes_internal',
]);

const BLOCKED_KEYS = new Set([
  'command', 'stdout', 'stderr', 'exit_code', 'duration_ms', 'cwd',
  'previous_error', 'stderr_snippet', 'error_type',
]);

function readableKey(key: string) {
  return LABELS[key] || key.replace(/_/g, ' ');
}

// Recursively strip internal-only keys before rendering.
function sanitize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === 'object') {
    const out: Row = {};
    for (const [k, v] of Object.entries(value as Row)) {
      if (SANITIZE_KEYS.has(k) || BLOCKED_KEYS.has(k)) continue;
      out[k] = sanitize(v) as Row[string];
    }
    return out;
  }
  return value;
}

// Build a human-readable summary of the local workspace instead of dumping the
// raw .kyrozen engine blobs (stagegate.json / software_feature.json / files).
function localSummary(local: Row | undefined): Row {
  if (!local) return {};
  const files = Array.isArray(local.files) ? (local.files as unknown[]) : [];
  const docsFiles = files.filter((f) => {
    const s = String(f);
    return s.startsWith('docs/') || /PROBLEM\.md|PRD\.md|MARKET\.md|TECH_DESIGN\.md|README\.md/i.test(s);
  }).length;
  const otherFiles = Math.max(0, files.length - docsFiles);
  const stagegate = (local.stagegate as Row | null) || null;
  const software = local.software as Row | null;
  const hardwareRuns = Array.isArray(local.hardware_runs) ? local.hardware_runs.length : 0;
  const stageLabel = stagegate && stagegate.stage ? (STAGE_NAMES[String(stagegate.stage)] || String(stagegate.stage)) : '';
  const progress = stagegate && typeof stagegate.progress === 'number' ? `${stagegate.progress}%` : '';
  return {
    '本地工作区': local.workspace_root,
    '文档资料': docsFiles > 0 ? `${docsFiles} 份文档已生成` : '尚未生成',
    '其他文件': otherFiles > 0 ? `${otherFiles} 个` : '无',
    '软件生成': software ? '已完成' : '尚未开始',
    '硬件运行记录': hardwareRuns > 0 ? `${hardwareRuns} 条` : '尚未运行',
    '当前阶段': stageLabel ? `${stageLabel}${progress ? `（${progress}）` : ''}` : '未知',
  };
}

function Value({ value }: { value: unknown }) {
  if (empty(value)) return <span className="text-ink-ghost">尚未形成</span>;
  if (typeof value === 'string') {
    if (STAGE_NAMES[value]) return <span>{STAGE_NAMES[value]}</span>;
    const trimmed = value.trim();
    if ((trimmed.startsWith('{') || trimmed.startsWith('['))) {
      try { return <Value value={JSON.parse(trimmed)} />; } catch { /* render markdown */ }
    }
    return <ReactMarkdown remarkPlugins={[remarkGfm]} className="markdown-body">{value}</ReactMarkdown>;
  }
  if (typeof value !== 'object') return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={String((item as Row)?.id || index)} className="border-l-2 border-l-accent pl-3 py-1">
            <Value value={item} />
          </div>
        ))}
      </div>
    );
  }
  const cleaned = sanitize(value) as Row;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {Object.entries(cleaned).filter(([key, item]) =>
        !key.endsWith('_id') && !['id', 'user_id', 'created_at', 'updated_at'].includes(key)
        && !BLOCKED_KEYS.has(key) && !empty(item)
      ).map(([key, item]) => (
        <div key={key} className="min-w-0">
          <div className="text-xs font-medium text-ink-faint mb-1">{readableKey(key)}</div>
          <div className="min-w-0 break-words text-sm text-ink-soft"><Value value={item} /></div>
        </div>
      ))}
    </div>
  );
}

function Section({ title, description, value }: { title: string; description?: string; value: unknown }) {
  return (
    <section className="panel p-4">
      <h3 className="font-display text-xl text-ink">{title}</h3>
      {description && <p className="text-xs text-ink-faint mt-1 mb-3">{description}</p>}
      <Value value={value} />
    </section>
  );
}

function EvidenceReferences({
  brief,
  items,
  onOpen,
}: {
  brief: Row | null | undefined;
  items: Row[];
  onOpen: (evidenceId: string) => void;
}) {
  if (!brief) return <p className="text-sm text-ink-faint">尚未保存 Problem Brief。</p>;
  const findEvidence = (id: string) => items.find((item) => String(item.artifact_id || '') === id);
  const references = (key: string) => Array.isArray(brief[key]) ? (brief[key] as unknown[]).map(String).filter(Boolean) : [];
  const support = references('evidence_ids');
  const counter = references('counter_evidence_ids');
  const unresolved = references('unresolved_questions');
  const group = (title: string, ids: string[], clickable: boolean) => (
    <div className="space-y-1">
      <h4 className="text-xs font-medium text-ink-faint">{title}</h4>
      {ids.length ? ids.map((id) => {
        const evidence = findEvidence(id);
        return clickable ? (
          <button
            key={id}
            type="button"
            className="block text-left text-sm text-accent underline underline-offset-2 hover:text-ink"
            onClick={() => onOpen(id)}
            title={evidence ? String(evidence.claim || evidence.summary || id) : '原始证据当前不可见'}
          >
            {evidence ? String(evidence.claim || evidence.summary || id) : id}
          </button>
        ) : <p key={id} className="text-sm text-ink-soft">{id}</p>;
      }) : <p className="text-sm text-ink-ghost">尚未形成</p>}
    </div>
  );
  return (
    <div className="grid gap-3 lg:grid-cols-3" data-testid="problem-brief-evidence-references">
      {group('支持证据（点击查看原始记录）', support, true)}
      {group('反对证据（点击查看原始记录）', counter, true)}
      {group('未解决问题', unresolved, false)}
    </div>
  );
}

export function ProjectWorkspacePanel({ projectId, onClose }: Props) {
  const kyzon = window.kyrozen!;
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('overview');
  const [loading, setLoading] = useState(true);
  const [loadingSlow, setLoadingSlow] = useState(false);
  const [notice, setNotice] = useState('');
  const [retryAction, setRetryAction] = useState<RetryAction | null>(null);
  const [solutionComparison, setSolutionComparison] = useState<Row | null>(null);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [decision, setDecision] = useState('');
  const [reason, setReason] = useState('');
  const [feedback, setFeedback] = useState('');
  const [feedbackParticipantId, setFeedbackParticipantId] = useState('');
  const [feedbackUserType, setFeedbackUserType] = useState('');
  const [feedbackTask, setFeedbackTask] = useState('');
  const [feedbackCompleted, setFeedbackCompleted] = useState('unknown');
  const [feedbackDuration, setFeedbackDuration] = useState('');
  const [feedbackBlockers, setFeedbackBlockers] = useState('');
  const [feedbackQuote, setFeedbackQuote] = useState('');
  const [feedbackSatisfaction, setFeedbackSatisfaction] = useState('');
  const [procurement, setProcurement] = useState('');
  const [hardwareArchitecture, setHardwareArchitecture] = useState('');
  const [bomModel, setBomModel] = useState('');
  const [bomQuantity, setBomQuantity] = useState('1');
  const [bomPrice, setBomPrice] = useState('');
  const [bomVendor, setBomVendor] = useState('');
  const [bomAlternative, setBomAlternative] = useState('');
  const [bomCompatibility, setBomCompatibility] = useState('');
  const [bomStatus, setBomStatus] = useState('not_purchased');
  const [bomLink, setBomLink] = useState('');
  const [wireDevice, setWireDevice] = useState('');
  const [wirePin, setWirePin] = useState('');
  const [wireTarget, setWireTarget] = useState('');
  const [wireTargetType, setWireTargetType] = useState('controller');
  const [wireVoltage, setWireVoltage] = useState('');
  const [wireCurrentDirection, setWireCurrentDirection] = useState('');
  const [wireSafety, setWireSafety] = useState('');
  const [firmwarePlatform, setFirmwarePlatform] = useState('esp32');
  const [firmwareFramework, setFirmwareFramework] = useState('arduino');
  const [firmwareVersion, setFirmwareVersion] = useState('');
  const [firmwareSource, setFirmwareSource] = useState('');
  const [firmwareFiles, setFirmwareFiles] = useState('');
  const [maker, setMaker] = useState('');
  const [makerComponent, setMakerComponent] = useState('');
  const [makerAction, setMakerAction] = useState('');
  const [makerExpected, setMakerExpected] = useState('');
  const [makerSafety, setMakerSafety] = useState('');
  const [makerPhoto, setMakerPhoto] = useState('');
  const [makerConfirmed, setMakerConfirmed] = useState(false);
  const [testResult, setTestResult] = useState('');
  const [testResultStatus, setTestResultStatus] = useState('passed');
  const [testEvidence, setTestEvidence] = useState('');
  const [testDefectOwner, setTestDefectOwner] = useState('');
  const [testCaseId, setTestCaseId] = useState('TC-DESKTOP-01');
  const [testCaseName, setTestCaseName] = useState('');
  const [testCaseRequirement, setTestCaseRequirement] = useState('');
  const [testCaseSteps, setTestCaseSteps] = useState('');
  const [testCaseExpected, setTestCaseExpected] = useState('');
  const [regressionNotes, setRegressionNotes] = useState('');
  const [validationConclusion, setValidationConclusion] = useState('continue_release');
  const [validationMetrics, setValidationMetrics] = useState('');
  const [improvement, setImprovement] = useState('');
  const [improvementStatus, setImprovementStatus] = useState('draft');
  const [projectType, setProjectType] = useState<'software' | 'embedded' | 'hybrid'>('software');
  const [hardwarePort, setHardwarePort] = useState('');
  const [hardwareBoard, setHardwareBoard] = useState('esp32:esp32:esp32');
  const [hardwareBusy, setHardwareBusy] = useState(false);
  const [hardwareResult, setHardwareResult] = useState<Row | null>(null);
  const [hardwareObserved, setHardwareObserved] = useState('');
  const [hardwareBehaviorConfirmed, setHardwareBehaviorConfirmed] = useState(false);
  const [hardwareQuestionAnswered, setHardwareQuestionAnswered] = useState(false);
  const [hardwareTools, setHardwareTools] = useState<Row | null>(null);
  const [toolchainBusy, setToolchainBusy] = useState(false);
  const [protocolTransport, setProtocolTransport] = useState<'fake' | 'serial'>('fake');
  const [protocolMessage, setProtocolMessage] = useState('{"protocol_version":"1.0","message_type":"telemetry","fields":{"value":1},"direction":"app_to_device"}');
  const [integrationTest, setIntegrationTest] = useState('');
  const protocolMessageRef = useRef(protocolMessage);
  const protocolTransportRef = useRef(protocolTransport);
  protocolMessageRef.current = protocolMessage;
  protocolTransportRef.current = protocolTransport;
  const [evidenceType, setEvidenceType] = useState('interview');
  const [evidenceClaim, setEvidenceClaim] = useState('');
  const [evidenceOriginal, setEvidenceOriginal] = useState('');
  const [evidenceSource, setEvidenceSource] = useState('');
  const [evidenceSourceUrl, setEvidenceSourceUrl] = useState('');
  const [evidenceObservedAt, setEvidenceObservedAt] = useState('');
  const [evidenceConfidence, setEvidenceConfidence] = useState('medium');
  const [evidenceClaimType, setEvidenceClaimType] = useState('unknown');
  const [evidenceAudience, setEvidenceAudience] = useState('');
  const [evidenceQuestion, setEvidenceQuestion] = useState('');
  const [evidenceCounter, setEvidenceCounter] = useState('');
  const [editingEvidenceId, setEditingEvidenceId] = useState('');
  const [editingEvidenceVersion, setEditingEvidenceVersion] = useState(0);
  const [researchQuery, setResearchQuery] = useState('');
  const [researchBusy, setResearchBusy] = useState(false);
  const [evidenceImpact, setEvidenceImpact] = useState<Row | null>(null);
  const [evidenceMergeTarget, setEvidenceMergeTarget] = useState('');

  const hardwareRunList = Array.isArray(data?.local?.hardware_runs)
    ? data!.local!.hardware_runs as Row[]
    : [];
  const successfulHardwareRuns = hardwareRunList.filter((run) => run.status === 'PASSED' && run.success === true);
  const successfulPortDiscoveries = successfulHardwareRuns.filter((run) => run.action === 'list_ports' && run.board_detected === true);
  const physicalAcceptanceMissing = [
    successfulPortDiscoveries.length >= 2 ? '' : '两次确认板卡的串口发现（含拔插后重新发现）',
    successfulHardwareRuns.some((run) => run.action === 'compile') ? '' : '固件编译',
    successfulHardwareRuns.some((run) => run.action === 'upload') ? '' : '固件上传',
    successfulHardwareRuns.some((run) => run.action === 'monitor') ? '' : '串口观察',
  ].filter(Boolean);
  const physicalAcceptanceReady = physicalAcceptanceMissing.length === 0;

  const load = useCallback(async (preserveNotice = false) => {
    setLoading(true);
    setLoadingSlow(false);
    const slowTimer = window.setTimeout(() => setLoadingSlow(true), 8000);
    const result = await kyzon.getProjectWorkspace(projectId);
    window.clearTimeout(slowTimer);
    if (result.success && result.data) {
      setData(result.data as WorkspaceData);
      setProjectType((result.data as WorkspaceData).project?.project_type as typeof projectType || 'software');
      const solutions = await kyzon.getSolutions(projectId);
      if (solutions.success && solutions.data?.comparison) setSolutionComparison(solutions.data.comparison as Row);
      if (!preserveNotice) setNotice('');
    } else {
      setNotice(result.error || '项目画布加载失败');
      setRetryAction({ label: '刷新项目工作台', run: () => load(false) });
    }
    setLoading(false);
    setLoadingSlow(false);
  }, [kyzon, projectId]);

  useEffect(() => { void load(); }, [load]);

  // A planning request may be dispatched asynchronously through the desktop
  // chat channel. Refresh the workbench when the Agent replies so a user does
  // not have to guess that a manual refresh is required before seeing the
  // persisted solution comparison.
  useEffect(() => {
    const unsubscribe = kyzon.onChatMessage((message) => {
      if (message.role === 'assistant') void load(true);
    });
    return unsubscribe;
  }, [kyzon, load]);

  const artifactCount = useCallback(() => {
    const docs = Array.isArray(data?.local?.files)
      ? (data!.local!.files as unknown[]).filter((f) => {
          const s = String(f);
          return s.startsWith('docs/') || /PROBLEM\.md|PRD\.md|MARKET\.md|TECH_DESIGN\.md|README\.md/i.test(s);
        }).length
      : 0;
    return (data?.artifacts?.length || 0) + docs + (data?.local?.software ? 1 : 0);
  }, [data]);

  const saveDecision = async () => {
    if (!decision.trim()) return;
    const result = await kyzon.createDecision(projectId, decision.trim(), reason.trim());
    setNotice(result.success ? '决策已保存' : result.error || '保存失败');
    if (result.success) { setRetryAction(null); setDecision(''); setReason(''); await load(true); }
    else setRetryAction({ label: '保存决策', run: saveDecision });
  };

  const saveSolution = async (action: 'select' | 'compose' | 'reject' | 'regenerate' | 'revoke') => {
    if (!solutionComparison) {
      setNotice('尚未形成可确认的三方案比较');
      return;
    }
    const result = await kyzon.saveSolution(projectId, solutionComparison, action, reason.trim() ? [reason.trim()] : []);
    setNotice(result.success ? (action === 'revoke' || action === 'reject' ? '方案确认已撤销' : action === 'regenerate' ? '方案已重新生成并保存版本链' : '方案已确认，已解除实现阶段门禁') : result.error || '方案保存失败，可重试');
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: '保存方案决策', run: () => saveSolution(action) });
  };

  const requestSolutionCandidates = async (regenerate = false) => {
    if (planningBusy) return;
    setPlanningBusy(true);
    setNotice(regenerate ? '正在请求方案 Agent，重新评估当前证据和研究结果…' : '正在请求方案 Agent，先检查当前证据和研究结果…');
    const result = await kyzon.sendChat(
      `${regenerate ? '请重新生成一组真正不同、且能解释变化原因的候选方案；不要仅递增旧 Artifact 版本。' : ''}请基于当前项目已经保存的真实证据、市场研究和 Problem Brief，完成方案设计闭环：只在证据和研究结果足够时生成并保存恰好三个候选方案（保守、平衡、激进），统一比较时间、成本、用户价值、技术风险、维护成本、数据风险、验证难度七个维度，并保存引用证据、推荐理由、关键假设、放弃内容和失败条件。不得编造外部研究结果；如果资料不足，请明确说明缺少哪些证据或研究来源，不要保存看似真实的替代结果。`,
    );
    if (!result.success) {
      setNotice(result.error || '方案 Agent 请求失败，可重试');
      setRetryAction({ label: regenerate ? '重新请求方案 Agent' : '请求方案 Agent', run: () => requestSolutionCandidates(regenerate) });
    } else {
      setRetryAction(null);
      setNotice(result.content ? '方案 Agent 已完成，请检查三案及其证据引用' : '方案 Agent 已开始处理，完成后会自动刷新决策中心');
      await load(true);
    }
    setPlanningBusy(false);
  };

  const saveFeedback = async () => {
    if (!feedback.trim()) return;
    const validation: Row = {
      participant_id: feedbackParticipantId.trim(),
      user_type: feedbackUserType.trim(),
      task: feedbackTask.trim(),
      completed: feedbackCompleted === 'unknown' ? null : feedbackCompleted === 'yes',
      duration_seconds: feedbackDuration.trim() ? Number(feedbackDuration) : null,
      blockers: feedbackBlockers.split('\n').map((item) => item.trim()).filter(Boolean),
      quote: feedbackQuote.trim(),
      satisfaction: feedbackSatisfaction.trim() ? Number(feedbackSatisfaction) : null,
    };
    const result = await kyzon.createFeedback(projectId, feedback.trim(), 'experience', 'medium', validation);
    setNotice(result.success ? '用户反馈已记录' : result.error || '记录失败');
    if (result.success) {
      setRetryAction(null);
      const blockers = Array.isArray(validation.blockers) ? validation.blockers as string[] : [];
      if (validation.completed === false || blockers.length > 0) {
        const iteration = await kyzon.createArtifact(projectId, 'iteration_task', `Feedback Iteration: ${feedbackTask.trim() || '用户反馈'}`, JSON.stringify({
          source_feedback: feedback.trim(), participant_id: validation.participant_id,
          blockers, status: 'pending', next_step: '根据反馈修复阻塞并重新验证',
          saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
        }), '用户反馈自动生成迭代任务');
        if (!iteration.success) setNotice(`用户反馈已记录，但迭代任务创建失败：${iteration.error || '可重试'}`);
      }
      setFeedback(''); setFeedbackParticipantId(''); setFeedbackUserType(''); setFeedbackTask(''); setFeedbackCompleted('unknown');
      setFeedbackDuration(''); setFeedbackBlockers(''); setFeedbackQuote(''); setFeedbackSatisfaction('');
      await load(true);
    } else setRetryAction({ label: '保存用户反馈', run: saveFeedback });
  };

  const saveImprovement = async (status: string = 'draft') => {
    if (!improvement.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'improvement_suggestion', 'Desktop Improvement Suggestion', JSON.stringify({
      text: improvement.trim(), status, saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), `改进建议状态：${status}`);
    setNotice(result.success ? (status === 'draft' ? '改进建议已保存' : `改进建议已${status === 'accepted' ? '接受' : status === 'ignored' ? '忽略' : status === 'deferred' ? '延期' : status === 'hidden' ? '隐藏' : '标记删除'}`) : result.error || '改进建议保存失败，可重试');
    if (result.success) { setRetryAction(null); setImprovementStatus(status); await load(true); }
    else setRetryAction({ label: '保存改进建议', run: () => saveImprovement(status) });
  };

  const saveArtifact = async (type: string, title: string, value: string) => {
    if (!value.trim()) return;
    const result = await kyzon.createArtifact(projectId, type, title, JSON.stringify({
      text: value.trim(), status: 'draft', saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), '桌面端工作中心保存');
    setNotice(result.success ? '已保存，刷新后仍可恢复' : result.error || '保存失败，可重试');
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: '保存工作中心记录', run: () => saveArtifact(type, title, value) });
  };

  const saveBomItem = async () => {
    if (!bomModel.trim()) return;
    const quantity = Math.max(1, Number.parseInt(bomQuantity, 10) || 1);
    const numericPrice = Number.parseFloat(bomPrice);
    const totalPrice = Number.isFinite(numericPrice) ? String(numericPrice * quantity) : '';
    const result = await kyzon.createArtifact(projectId, 'bom', 'Bill of Materials', JSON.stringify({
      items: [{
        name: bomModel.trim(), model: bomModel.trim(), quantity, price: bomPrice.trim(),
        total_price: totalPrice, vendor: bomVendor.trim(), alternative: bomAlternative.trim(), compatibility: bomCompatibility.trim(), link: bomLink.trim(),
        procurement_status: bomStatus, purchase_status: bomStatus === 'already_owned' ? 'already_owned' : 'need_purchase',
      }], total_estimate: totalPrice, saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), '桌面采购中心保存结构化 BOM');
    setNotice(result.success ? 'BOM 条目已保存' : result.error || 'BOM 保存失败，可重试');
    if (result.success) {
      setRetryAction(null);
      setBomModel(''); setBomQuantity('1'); setBomPrice(''); setBomVendor(''); setBomAlternative(''); setBomCompatibility(''); setBomLink('');
      await load(true);
    } else setRetryAction({ label: '保存 BOM 条目', run: saveBomItem });
  };

  const saveMakerStep = async () => {
    if (!makerComponent.trim() || !makerAction.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'assembly_step', `Maker Step: ${makerComponent.trim()}`, JSON.stringify({
      order: 0, title: makerAction.trim(), instructions: makerAction.trim(),
      components_involved: [makerComponent.trim()], expected_result: makerExpected.trim(),
      safety_notes: makerSafety.trim(), photo: makerPhoto.trim(), confirmed: makerConfirmed,
      status: makerConfirmed ? 'done' : 'pending', saved_from: 'desktop_phase2_workbench',
    }), 'Maker 模式保存结构化装配步骤');
    setNotice(result.success ? '装配步骤已保存' : result.error || '装配步骤保存失败，可重试');
    if (result.success) {
      setRetryAction(null);
      setMakerComponent(''); setMakerAction(''); setMakerExpected(''); setMakerSafety(''); setMakerPhoto(''); setMakerConfirmed(false);
      await load(true);
    } else setRetryAction({ label: '保存 Maker 装配步骤', run: saveMakerStep });
  };

  const saveWiring = async () => {
    if (!wireDevice.trim() || !wirePin.trim() || !wireTarget.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'wiring_design', 'Wiring Design', JSON.stringify({
      connections: [{
        device: wireDevice.trim(), pin: wirePin.trim(), target: wireTarget.trim(), target_type: wireTargetType,
        voltage: wireVoltage.trim(), current_direction: wireCurrentDirection.trim(),
        safety_conditions: wireSafety.split('\n').map((item) => item.trim()).filter(Boolean),
      }], saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), '桌面采购中心保存结构化接线');
    setNotice(result.success ? '接线设计已保存' : result.error || '接线设计保存失败，可重试');
    if (result.success) { setRetryAction(null); setWireDevice(''); setWirePin(''); setWireTarget(''); setWireVoltage(''); setWireCurrentDirection(''); setWireSafety(''); await load(true); }
    else setRetryAction({ label: '保存接线设计', run: saveWiring });
  };

  const saveHardwareArchitecture = async () => {
    if (!hardwareArchitecture.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'hardware_architecture', 'Hardware Architecture', JSON.stringify({
      description: hardwareArchitecture.trim(), saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), '桌面采购中心保存硬件方案');
    setNotice(result.success ? '硬件方案已保存' : result.error || '硬件方案保存失败，可重试');
    if (result.success) { setRetryAction(null); setHardwareArchitecture(''); await load(true); }
    else setRetryAction({ label: '保存硬件方案', run: saveHardwareArchitecture });
  };

  const saveIntegrationTest = async () => {
    if (!integrationTest.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'integration_test', 'Software Hardware Integration Test', JSON.stringify({
      result: integrationTest.trim(), transport: protocolTransportRef.current, saved_from: 'desktop_phase2_workbench', saved_at: new Date().toISOString(),
    }), '桌面采购中心保存软硬件集成测试');
    setNotice(result.success ? '集成测试记录已保存' : result.error || '集成测试保存失败，可重试');
    if (result.success) { setRetryAction(null); setIntegrationTest(''); await load(true); }
    else setRetryAction({ label: '保存集成测试', run: saveIntegrationTest });
  };

  const saveFirmware = async () => {
    if (!hardwareBoard.trim() || !firmwareVersion.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'firmware_project', 'Firmware Project', JSON.stringify({
      platform: firmwarePlatform, board: hardwareBoard.trim(), version: firmwareVersion.trim(), source: firmwareSource.trim(),
      framework: firmwareFramework, files: firmwareFiles.split('\n').map((item) => item.trim()).filter(Boolean),
      build_status: 'pending', upload_status: 'pending', port: hardwarePort.trim(), baud: 115200,
    }), '桌面采购中心保存固件定义');
    setNotice(result.success ? '固件项目定义已保存' : result.error || '固件定义保存失败，可重试');
    if (result.success) { setRetryAction(null); setFirmwareVersion(''); setFirmwareSource(''); setFirmwareFiles(''); await load(true); }
    else setRetryAction({ label: '保存固件定义', run: saveFirmware });
  };

  const saveEvidence = async () => {
    if (!evidenceClaim.trim()) return;
    const evidencePayload = {
      claim: evidenceClaim.trim(), original_text: evidenceOriginal.trim(),
      summary: evidenceClaim.trim(), source: evidenceType === 'public_source' ? 'external_evidence' : 'user_statement', source_name: evidenceSource.trim(),
      evidence_type: evidenceType, verified: false, confidence: evidenceConfidence, claim_type: evidenceClaimType,
      target_audience: evidenceAudience.trim(), related_question: evidenceQuestion.trim(),
      counter_evidence: evidenceCounter.split('\n').map((item) => item.trim()).filter(Boolean),
      source_url: evidenceSourceUrl.trim(),
      observed_at: evidenceObservedAt.trim() ? new Date(evidenceObservedAt).toISOString() : new Date().toISOString(),
    };
    const result = editingEvidenceId
      ? await kyzon.editEvidence(projectId, editingEvidenceId, evidencePayload, editingEvidenceVersion)
      : await kyzon.createEvidence(projectId, evidencePayload);
    setNotice(result.success ? (editingEvidenceId ? '证据已编辑并保存新版本' : '证据已保存，刷新后仍可恢复') : result.error || '证据保存失败，可重试');
    if (result.success) { setRetryAction(null); setEvidenceClaim(''); setEvidenceOriginal(''); setEvidenceSource(''); setEvidenceSourceUrl(''); setEvidenceObservedAt(''); setEvidenceAudience(''); setEvidenceQuestion(''); setEvidenceCounter(''); setEvidenceConfidence('medium'); setEvidenceClaimType('unknown'); setEditingEvidenceId(''); setEditingEvidenceVersion(0); await load(true); }
    else setRetryAction({ label: editingEvidenceId ? '保存证据新版本' : '保存证据', run: saveEvidence });
  };

  const editEvidence = (item: Row) => {
    setEditingEvidenceId(String(item.artifact_id || ''));
    setEditingEvidenceVersion(Number(item.version || 0));
    setEvidenceType(String(item.evidence_type || 'interview'));
    setEvidenceClaim(String(item.claim || ''));
    setEvidenceOriginal(String(item.original_text || ''));
    setEvidenceSource(String(item.source_name || ''));
    setEvidenceSourceUrl(String(item.source_url || ''));
    setEvidenceObservedAt(String(item.observed_at || '').slice(0, 16));
    setEvidenceConfidence(String(item.confidence || 'medium'));
    setEvidenceClaimType(String(item.claim_type || 'unknown'));
    setEvidenceAudience(String(item.target_audience || ''));
    setEvidenceQuestion(String(item.related_question || ''));
    setEvidenceCounter(Array.isArray(item.counter_evidence) ? (item.counter_evidence as unknown[]).join('\n') : '');
    setNotice(`正在编辑证据 v${String(item.version || '')}，保存时会创建新版本`);
  };

  const previewEvidenceImpact = async (artifactId: string) => {
    const result = await kyzon.evidenceImpact(projectId, artifactId);
    setEvidenceImpact((result.data as Row) || null);
    setNotice(result.success ? `影响预览完成：${String((result.data as Row)?.count || 0)} 项资料会被改写` : result.error || '影响预览失败，可重试');
    if (result.success) setRetryAction(null);
    else setRetryAction({ label: '查看证据影响', run: () => previewEvidenceImpact(artifactId) });
  };

  const updateEvidenceStatus = async (artifactId: string, status: 'active' | 'invalid' | 'deleted', version: number) => {
    const result = await kyzon.updateEvidence(projectId, artifactId, status, version);
    setNotice(result.success ? (status === 'invalid' ? '证据已标记无效' : '证据已恢复') : result.error || '证据状态更新失败，可重试');
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: status === 'active' ? '恢复证据' : '标记证据状态', run: () => updateEvidenceStatus(artifactId, status, version) });
  };

  const deleteEvidence = async (artifactId: string, version: number) => {
    const impact = await kyzon.evidenceImpact(projectId, artifactId);
    if (!impact.success) { setNotice(impact.error || '删除前影响预览失败，可重试'); setRetryAction({ label: '预览删除影响', run: () => deleteEvidence(artifactId, version) }); return; }
    setEvidenceImpact((impact.data as Row) || null);
    const count = Number((impact.data as Row)?.count || 0);
    if (!window.confirm(`删除将影响 ${count} 项 Problem Brief、研究结论或方案引用。确认继续吗？`)) return;
    const result = await kyzon.deleteEvidence(projectId, artifactId, version);
    setNotice(result.success ? '证据已删除（保留版本历史，可恢复）' : result.error || '证据删除失败，可重试');
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: '删除证据', run: () => deleteEvidence(artifactId, version) });
  };

  const mergeEvidence = async (artifactId: string, sourceVersion: number, items: Row[]) => {
    if (!evidenceMergeTarget || evidenceMergeTarget === artifactId) return;
    const target = items.find((item) => String(item.artifact_id) === evidenceMergeTarget);
    const result = await kyzon.mergeEvidence(projectId, artifactId, evidenceMergeTarget, sourceVersion, Number(target?.version || 0) || undefined);
    setNotice(result.success ? '证据已合并，引用已生成新版本' : result.error || '证据合并失败，可重试');
    if (result.success) { setRetryAction(null); setEvidenceMergeTarget(''); await load(true); }
    else setRetryAction({ label: '合并证据', run: () => mergeEvidence(artifactId, sourceVersion, items) });
  };

  const runResearch = async () => {
    if (!researchQuery.trim()) return;
    const query = researchQuery.trim();
    setResearchBusy(true);
    const result = await kyzon.runResearch(projectId, query, 5);
    setResearchBusy(false);
    const status = (result.data?.status as string) || '';
    const blocked = result.success && status === 'blocked';
    setNotice(result.success ? (blocked ? '研究运行已记录，但没有可用外部结果；可配置来源后重试' : '研究运行已完成并保存来源状态') : result.error || '研究运行失败，可重试');
    if (result.success && !blocked) { setRetryAction(null); setResearchQuery(''); await load(true); }
    else {
      // Keep the exact query in the input so an unconfigured/rate-limited
      // run can be retried after credentials or provider availability change.
      setRetryAction({ label: '重试研究运行', run: runResearch });
      await load(true);
    }
  };

  const confirmWorkflow = async () => {
    const result = await kyzon.confirmWorkflow(projectId, projectType);
    setNotice(result.success ? '项目类型与流程已确认' : result.error || '类型确认失败，可重试');
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: '确认项目流程', run: confirmWorkflow });
  };

  const advanceHybridTrack = async (track: string) => {
    const result = await kyzon.advanceHybridTrack(projectId, track);
    const trackLabel = `${TRACK_NAMES[track] || track}轨道`;
    setNotice(result.success ? `${trackLabel}已推进并持久化` : result.error || `${trackLabel}推进失败，可重试`);
    if (result.success) {
      setRetryAction(null);
      await load(true);
    } else {
      setRetryAction({ label: `推进${trackLabel}`, run: () => advanceHybridTrack(track) });
    }
  };

  const confirmProtocol = async () => {
    try {
      const protocol = JSON.parse(protocolMessage) as Row;
      const result = await kyzon.confirmProtocol(projectId, protocol, true, [], []);
      setNotice(result.success ? '协议版本已确认并写入门禁' : result.error || '协议确认失败，可重试');
      if (result.success) { setRetryAction(null); await load(true); }
      else setRetryAction({ label: '确认协议版本', run: confirmProtocol });
    } catch {
      setNotice('协议消息必须是有效 JSON');
      setRetryAction({ label: '确认协议版本', run: confirmProtocol });
    }
  };

  const runHardware = async (action: string, extra: Row = {}) => {
    const root = String(data?.local?.workspace_root || '');
    if (action !== 'protocol_scenarios' && !root) { setNotice('请先为项目选择本地工作区'); return; }
    setHardwareBusy(true);
    const result = action === 'protocol_scenarios'
      ? await kyzon.runProtocolScenarios(projectId)
      : await kyzon.runLocalHardware(projectId, root, action, { board: hardwareBoard, port: hardwarePort, baud: 115200, ...extra });
    setHardwareBusy(false);
    setHardwareResult((result.data as Row) || null);
    const blocked = result.data?.status === 'BLOCKED' || Boolean(result.data?.block_reason);
    const operationSucceeded = result.success && !blocked;
    if (operationSucceeded && action === 'protocol_scenarios' && result.data) {
      setNotice(result.data.status === 'PASSED' ? '协议六场景已通过并持久化' : '协议场景未全部通过');
    } else {
      setNotice(operationSucceeded ? `${action} 已完成并记录本地硬件证据` : result.error || '硬件操作失败，可修复后重试');
    }
    if (operationSucceeded) setRetryAction(null);
    else setRetryAction({ label: `重试硬件操作：${action}`, run: () => runHardware(action, extra) });
    await load(true);
  };

  const runProtocolMessage = async () => {
    try {
      const message = JSON.parse(protocolMessageRef.current) as Row;
      await runHardware('protocol_exchange', { transport: protocolTransportRef.current, message });
    } catch {
      setNotice('协议消息必须是有效 JSON');
      setRetryAction({ label: '执行协议测试', run: runProtocolMessage });
    }
  };

  const openEvidenceReference = (evidenceId: string) => {
    setTab('overview');
    window.requestAnimationFrame(() => {
      document.getElementById(`evidence-${evidenceId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  const inspectToolchain = async () => {
    const result = await kyzon.getHardwareToolStatus();
    setHardwareTools((result.tools as Row) || null);
    setNotice(result.success ? '硬件工具链状态已刷新' : '硬件工具链状态读取失败，可重试');
    if (result.success) setRetryAction(null);
    else setRetryAction({ label: '检查硬件工具链', run: inspectToolchain });
  };

  const repairToolchain = async () => {
    setToolchainBusy(true);
    const result = await kyzon.ensureHardwareToolchain();
    setToolchainBusy(false);
    setNotice(result.success ? '硬件工具链检查/修复已完成' : result.error || '硬件工具链修复失败，可重试');
    if (result.success) setRetryAction(null);
    else setRetryAction({ label: '修复硬件工具链', run: repairToolchain });
    await inspectToolchain();
  };

  const installCores = async () => {
    setToolchainBusy(true);
    const result = await kyzon.installCommonCores();
    setToolchainBusy(false);
    setNotice(result.success ? '常用板卡核心安装完成' : result.error || '板卡核心安装失败，可重试');
    if (result.success) setRetryAction(null);
    else setRetryAction({ label: '安装板卡核心', run: installCores });
    await inspectToolchain();
  };

  const saveHardwareAcceptance = async () => {
    if (!hardwareObserved.trim() || !hardwareBehaviorConfirmed) return;
    if (!physicalAcceptanceReady) {
      setNotice(`尚不能保存实物确认，还缺少：${physicalAcceptanceMissing.join('、')}`);
      return;
    }
    const result = await kyzon.createArtifact(projectId, 'hardware_acceptance', 'ESP32 Physical Acceptance', JSON.stringify({
      observed_behavior: hardwareObserved.trim(), confirmed_by_user: true, confirmation_prompt: '请确认 LED/串口实际行为符合预期，并确认拔插后已恢复。', confirmation_answer: 'confirmed_behavior_and_reconnect', confirmed_at: new Date().toISOString(), physical_evidence_required: true,
      hardware_run_timestamps: successfulHardwareRuns.map((run) => run.timestamp).filter(Boolean),
      hardware_runs: successfulHardwareRuns.filter((run) => ['list_ports', 'compile', 'upload', 'monitor'].includes(String(run.action))).map((run) => ({
        action: run.action, status: run.status, success: run.success, board_detected: run.board_detected, board: run.board || '', port: run.port || '', baud: run.baud || '', tool_version: run.tool_version || '', timestamp: run.timestamp || '', command: run.command || '', error_category: run.error_category || '',
      })),
    }), '桌面端 ESP32 实物验收');
    setNotice(result.success ? '实物验收证据已保存' : result.error || '实物验收保存失败，可重试');
    if (result.success) { setRetryAction(null); setHardwareObserved(''); setHardwareBehaviorConfirmed(false); setHardwareQuestionAnswered(false); await load(true); }
    else setRetryAction({ label: '保存实物验收', run: saveHardwareAcceptance });
  };

  const answerHardwareQuestion = async (confirmed: boolean) => {
    setHardwareQuestionAnswered(true);
    setHardwareBehaviorConfirmed(confirmed);
    if (!confirmed) {
      const result = await kyzon.createArtifact(projectId, 'hardware_question_response', 'ESP32 Physical Acceptance Question', JSON.stringify({
        status: 'BLOCKED',
        confirmation_answer: 'not_confirmed',
        confirmation_prompt: '请确认 LED/串口实际行为符合预期，并确认拔插后已恢复。',
        answered_by_user: true,
        answered_at: new Date().toISOString(),
        physical_evidence_required: true,
      }), '用户未确认硬件实际行为，保持 BLOCKED');
      setNotice(result.success ? '已记录“不符合/暂不确认”，实物验收保持 BLOCKED；请修复后重新观察。' : result.error || '保存硬件问答失败，可重试');
      if (result.success) setRetryAction(null);
      else setRetryAction({ label: '保存硬件问答', run: () => answerHardwareQuestion(false) });
    }
  };

  const saveTest = async () => {
    if (!testResult.trim()) return;
    const testCases = Array.isArray((data?.phase2?.testing as Row)?.test_cases)
      ? (data!.phase2!.testing as Row).test_cases as Row[]
      : [];
    const selectedCase = testCases.find((item) => String(item.id || '') === testCaseId.trim()) || testCases[testCases.length - 1];
    const resolvedTestCaseId = String(selectedCase?.id || testCaseId.trim() || 'TC-DESKTOP-WORKBENCH');
    const resolvedExpected = String(selectedCase?.expected || '工作台操作可保存并在刷新后恢复');
    const failed = testResultStatus === 'failed' || testResultStatus === 'error' || /失败|未通过|fail/i.test(testResult);
    const resultStatus = failed && testResultStatus === 'passed' ? 'failed' : testResultStatus;
    const evidence = testEvidence.split('\n').map((item) => item.trim()).filter(Boolean);
    const defectId = failed ? `DEF-DESKTOP-${Date.now()}` : '';
    const savedResult = await kyzon.createArtifact(projectId, 'test_result', 'Desktop Workbench Test Result', JSON.stringify({
      test_case_id: resolvedTestCaseId, test_case_name: String(selectedCase?.name || '桌面工作台用例'),
      result: resultStatus, actual: testResult.trim(), expected: resolvedExpected,
      ...(defectId ? { defect_id: defectId } : {}),
      evidence: evidence.length ? evidence : ['desktop_user_flow'],
    }), '桌面端测试中心保存测试结果');
    if (!savedResult.success) {
      setNotice(savedResult.error || '测试结果保存失败，可重试');
      setRetryAction({ label: '保存测试结果', run: saveTest });
      return;
    }
    if (failed) {
      const savedDefect = await kyzon.createArtifact(projectId, 'defect', 'Desktop Workbench Defect', JSON.stringify({
        defect_id: defectId, title: '工作台测试失败', severity: 'medium', status: 'open',
        reproduction_steps: selectedCase?.steps || [testResult.trim()], expected: resolvedExpected,
        actual: testResult.trim(), test_case_id: resolvedTestCaseId,
        related_requirement: String(selectedCase?.related_requirement || ''), owner: testDefectOwner.trim(),
        evidence_ids: evidence.length ? evidence : ['desktop_user_flow'],
      }), '失败测试自动创建缺陷');
      if (!savedDefect.success) {
        setNotice(savedDefect.error || '缺陷保存失败，可重试');
        setRetryAction({ label: '保存失败缺陷', run: saveTest });
        return;
      }
    }
    await load(true);
    setRetryAction(null);
    setNotice(failed ? '测试结果和缺陷已保存' : '测试结果已保存');
    setTestResult(''); setTestEvidence(''); setTestResultStatus('passed');
  };

  const saveTestCase = async () => {
    if (!testCaseName.trim() || !testCaseExpected.trim()) return;
    const result = await kyzon.createArtifact(projectId, 'test_case', `Test Case: ${testCaseId.trim() || '未命名'}`, JSON.stringify({
      id: testCaseId.trim(), name: testCaseName.trim(), type: 'functional',
      related_requirement: testCaseRequirement.trim(), description: testCaseName.trim(),
      steps: testCaseSteps.split('\n').map((item) => item.trim()).filter(Boolean),
      expected: testCaseExpected.trim(), environment: 'desktop workbench', priority: 'medium', status: 'ready',
    }), '桌面测试中心保存需求追踪用例');
    if (result.success) { setRetryAction(null); setTestCaseName(''); setTestCaseRequirement(''); setTestCaseSteps(''); setTestCaseExpected(''); await load(true); }
    if (result.success) setNotice('测试用例已保存并加入追踪矩阵');
    else { setNotice(result.error || '测试用例保存失败，可重试'); setRetryAction({ label: '保存测试用例', run: saveTestCase }); }
  };

  const saveValidationReport = async () => {
    const userValidation = (data?.phase2?.user_validation || {}) as Row;
    const report = {
      original_problem: String(data?.project?.goal || ''),
      tested_solution: String(data?.project?.name || ''),
      test_results_summary: data?.phase2?.testing || {},
      user_feedback: Array.isArray(userValidation.feedback) ? userValidation.feedback : [],
      success_metrics: validationMetrics.trim(),
      conclusion: validationConclusion,
      next_iteration: [],
    };
    const result = await kyzon.createArtifact(
      projectId,
      'validation_report',
      'Validation Report',
      JSON.stringify(report),
      '桌面端测试中心保存验证报告',
    );
    setNotice(result.success ? '验证报告已保存' : `验证报告保存失败：${result.error || '可补齐用户验证后重试'}`);
    if (result.success) { setRetryAction(null); await load(true); }
    else setRetryAction({ label: '保存验证报告', run: saveValidationReport });
  };

  const saveRegression = async () => {
    // A failed test writes both the result and the defect before refreshing the
    // canvas. Read the durable workspace here as well so a regression action
    // cannot race with an older in-memory snapshot.
    const latestWorkspace = await kyzon.getProjectWorkspace(projectId);
    const latestDefects = latestWorkspace.success && latestWorkspace.data
      ? (((latestWorkspace.data as Row).phase2 as Row | undefined)?.defects as unknown)
      : undefined;
    const defects = Array.isArray(latestDefects) ? latestDefects as Row[] : [];
    const defect = defects[defects.length - 1];
    if (!defect?.defect_id) {
      setNotice('暂无可回归的缺陷，请先记录一个失败结果');
      setRetryAction(null);
      return;
    }
    const regression = await kyzon.createArtifact(
      projectId,
      'test_result',
      `Regression: ${String(defect.defect_id)}`,
      JSON.stringify({
        test_case_id: defect.test_case_id || 'TC-DESKTOP-WORKBENCH',
        test_case_name: '原失败用例回归', result: 'passed',
        actual: regressionNotes.trim() || '修复后原用例通过',
        expected: defect.expected || '操作成功',
        regression_of: defect.defect_id, executed_by: 'user',
        timestamp: new Date().toISOString(),
      }),
      '桌面端缺陷回归通过',
    );
    if (!regression.success || !regression.data) {
      setNotice(regression.error || '回归结果保存失败，可重试');
      setRetryAction({ label: '保存原用例回归', run: saveRegression });
      return;
    }
    const fix = await kyzon.createArtifact(
      projectId,
      'defect_fix',
      `Fix: ${String(defect.defect_id)}`,
      JSON.stringify({
        defect_id: defect.defect_id,
        title: defect.title,
        fix: regressionNotes.trim() || '已修复并重新执行原失败用例',
        evidence: [regression.data.id],
        executed_by: 'user',
        timestamp: new Date().toISOString(),
      }),
      '记录缺陷修复与回归关联',
    );
    if (!fix.success) {
      setNotice(fix.error || '修复记录保存失败，可重试');
      return;
    }
    const resolved = await kyzon.createArtifact(
      projectId,
      'defect',
      String(defect.title || 'Desktop Workbench Defect'),
      JSON.stringify({ ...defect, artifact_id: undefined, version: undefined, status: 'resolved', fix: regressionNotes.trim() || '已修复并重新执行原失败用例', regression_result_id: regression.data.id }),
      '原失败用例回归通过，缺陷已解决',
    );
    setNotice(resolved.success ? '回归已通过，缺陷已解决' : resolved.error || '缺陷状态更新失败，可重试');
    if (resolved.success) { setRetryAction(null); setRegressionNotes(''); await load(true); }
    else setRetryAction({ label: '更新缺陷回归状态', run: saveRegression });
  };

  const exportProject = async () => {
    const result = await kyzon.exportProject(projectId);
    if (!result.cancelled) setNotice(result.success ? `已导出到 ${result.filePath}` : result.error || '导出失败');
  };

  return (
    <div className="absolute inset-0 z-30 bg-paper flex flex-col" data-testid="project-workspace-panel">
      <header className="flex items-center justify-between px-5 py-3 border-b border-line bg-surface">
        <div>
          <h2 className="font-display text-2xl leading-none">项目画布</h2>
          <p className="text-xs text-ink-faint mt-1">查看项目概览、记录决策与反馈、导出项目</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void exportProject()} className="btn-secondary text-xs">导出</button>
          <button type="button" onClick={() => void load()} className="btn-secondary text-xs">刷新</button>
          <button type="button" onClick={onClose} className="btn-ghost text-xs">关闭</button>
        </div>
      </header>
      {retryAction && <div role="alert" className="flex items-center justify-between gap-3 px-5 py-2 text-xs bg-warning-soft text-warning border-b border-warning/30"><span>上次操作失败：{retryAction.label}</span><button type="button" className="btn-secondary text-xs" onClick={() => { const action = retryAction; setRetryAction(null); void action.run(); }}>重试：{retryAction.label}</button></div>}
      <div role="tablist" aria-label="项目工作中心" className="flex border-b border-line bg-paper-sink overflow-x-auto px-3">
        {TABS.map(([key, label], index) => (
          <button
            key={key}
            id={`workbench-tab-${key}`}
            type="button"
            role="tab"
            aria-selected={tab === key}
            aria-controls="workbench-tab-panel"
            tabIndex={tab === key ? 0 : -1}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setTab(key); return; }
              if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1
                : (index + (event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : -1) + TABS.length) % TABS.length;
              const nextKey = TABS[next][0];
              setTab(nextKey);
              window.requestAnimationFrame(() => document.getElementById(`workbench-tab-${nextKey}`)?.focus());
            }}
            onClick={() => setTab(key)}
            className={`px-3 py-2 text-xs whitespace-nowrap border-b-2 ${tab === key ? 'border-accent text-accent font-medium' : 'border-transparent text-ink-faint hover:text-ink'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {notice && <div role="status" className="px-4 py-2 text-xs bg-accent-soft text-accent border-b border-line">{notice}</div>}
      <main id="workbench-tab-panel" role="tabpanel" aria-labelledby={`workbench-tab-${tab}`} className="flex-1 overflow-y-auto p-5">
        {!data ? <div className="text-sm text-ink-faint">{loadingSlow ? '项目资料较多，仍在整理中…' : '正在整理项目资料…'}</div> : (
          <div className="w-full max-w-5xl min-w-0 mx-auto space-y-4">
            {loading && <div className="text-xs text-ink-faint" aria-live="polite">{loadingSlow ? '正在刷新项目资料…' : '正在刷新…'}</div>}
            <div className="mb-2">
              <h3 className="font-display text-2xl">{TABS.find(([key]) => key === tab)?.[1]}</h3>
              <p className="text-xs text-ink-faint">{TABS.find(([key]) => key === tab)?.[2]}</p>
            </div>

            {tab === 'overview' && (
              <>
                <Section
                  title={String(data.project?.name || '项目概览')}
                  value={{ description: data.project?.description, goal: data.project?.goal, budget: data.project?.budget, risks: data.phase2?.risks, recent_decisions: (data.phase2?.decisions as unknown[] || []).slice(0, 5) }}
                />
                <section className="panel p-4" aria-labelledby="problem-brief-evidence-title">
                  <h3 id="problem-brief-evidence-title" className="font-display text-xl text-ink">Problem Brief 证据闭环</h3>
                  <p className="text-xs text-ink-faint mt-1 mb-3">支持和反对证据均保留原始引用；点击引用可定位到证据版本链。</p>
                  <EvidenceReferences
                    brief={data.phase2?.problem_brief as Row | null | undefined}
                    items={Array.isArray((data.phase2?.evidence as Row)?.items) ? (data.phase2!.evidence as Row).items as Row[] : []}
                    onOpen={openEvidenceReference}
                  />
                </section>
                <Section title="第二阶段验收状态" description="只有自动化、用户验证和（硬件项目）实物证据齐全后，项目才允许完成。" value={data.phase2?.phase2_completion || { ready: false, missing: ['尚未读取验收状态'] }} />
                <div className="grid gap-4 lg:grid-cols-3">
                  <div className="panel p-4">
                    <h3 className="font-display text-xl">项目类型</h3>
                    <p className="text-xs text-ink-faint mt-1 mb-3">问题探索完成前可调整；确认后按对应流程推进。</p>
                    <div className="flex gap-2 flex-wrap">
                      {([['software', '纯软件'], ['embedded', '嵌入式'], ['hybrid', '软硬件混合']] as const).map(([value, label]) => <button key={value} type="button" onClick={() => setProjectType(value)} className={`btn-secondary text-xs ${projectType === value ? 'border-accent text-accent' : ''}`}>{label}</button>)}
                    </div>
                    <button type="button" className="btn-primary text-xs mt-3" onClick={() => void confirmWorkflow()} disabled={Boolean(data.project?.type_confirmed && data.project?.project_type === projectType)}>确认流程</button>
                  </div>
                  <Section title="证据与研究" value={{ active_count: (data.phase2?.evidence as Row)?.active_count, source_count: (data.phase2?.research as Row)?.source_count }} />
                  <Section title="方案候选" value={(data.phase2?.solutions as Row)?.count || 0} />
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="panel p-4 space-y-3">
                    <h3 className="font-display text-xl">记录问题证据</h3>
                    <p className="text-xs text-ink-faint">保存原文和来源；没有证据时不会生成替代研究结果。</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <select className="input" value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)} aria-label="证据类型">
                        <option value="interview">访谈</option><option value="observation">观察</option><option value="survey">问卷</option><option value="screenshot">截图</option><option value="video">视频</option><option value="public_source">公开资料</option>
                      </select>
                      <input className="input" value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} placeholder="来源或参与者（可匿名）" />
                      <input className="input" value={evidenceSourceUrl} onChange={(event) => setEvidenceSourceUrl(event.target.value)} placeholder="来源链接（公开资料可填）" aria-label="证据来源链接" />
                      <input className="input" type="datetime-local" value={evidenceObservedAt} onChange={(event) => setEvidenceObservedAt(event.target.value)} aria-label="证据观察时间" />
                      <select className="input" value={evidenceConfidence} onChange={(event) => setEvidenceConfidence(event.target.value)} aria-label="证据可信度"><option value="low">可信度：低</option><option value="medium">可信度：中</option><option value="high">可信度：高</option></select>
                      <select className="input" value={evidenceClaimType} onChange={(event) => setEvidenceClaimType(event.target.value)} aria-label="证据分类"><option value="fact">事实</option><option value="opinion">用户观点</option><option value="inference">Agent 推断</option><option value="unknown">未知</option></select>
                      <input className="input" value={evidenceAudience} onChange={(event) => setEvidenceAudience(event.target.value)} placeholder="目标人群" aria-label="目标人群" />
                      <input className="input" value={evidenceQuestion} onChange={(event) => setEvidenceQuestion(event.target.value)} placeholder="关联问题" aria-label="关联问题" />
                    </div>
                    <input className="input" value={evidenceClaim} onChange={(event) => setEvidenceClaim(event.target.value)} placeholder="观察到的事实或用户原话" />
                    <textarea className="input" value={evidenceOriginal} onChange={(event) => setEvidenceOriginal(event.target.value)} placeholder="原文、截图说明或记录上下文" rows={2} />
                    <textarea className="input" value={evidenceCounter} onChange={(event) => setEvidenceCounter(event.target.value)} placeholder="反例或反对证据（每行一条，可选）" rows={2} aria-label="反例证据" />
                    <button type="button" className="btn-primary text-sm" disabled={!evidenceClaim.trim()} onClick={() => void saveEvidence()}>保存证据</button>
                  </div>
                  <div className="panel p-4 space-y-3">
                    <h3 className="font-display text-xl">运行市场研究</h3>
                    <p className="text-xs text-ink-faint">各来源独立记录成功、失败、限流或未配置状态；没有真实结果不会填充假数据。</p>
                    <input className="input" value={researchQuery} onChange={(event) => setResearchQuery(event.target.value)} placeholder="研究问题，例如 ESP32 串口遥测替代方案" />
                    <button type="button" className="btn-primary text-sm" disabled={researchBusy || !researchQuery.trim()} onClick={() => void runResearch()}>{researchBusy ? '研究运行中…' : '开始研究运行'}</button>
                    {(() => {
                      const research = (data.phase2?.research as Row) || {};
                      const sources = Array.isArray(research.sources) ? research.sources as Row[] : [];
                      return (
                        <>
                          <Section
                            title="最近研究状态"
                            description="每个来源独立记录成功、失败、限流和未配置；指标只基于已保存的真实来源。"
                            value={{
                              source_count: research.source_count,
                              source_coverage: research.source_coverage,
                              provider_status: research.provider_status,
                              citation_count: research.citation_count,
                              freshness: research.freshness,
                              fact_types: research.fact_types,
                              polarities: research.polarities,
                              conflict_count: research.conflict_count,
                              latest_run: Array.isArray(research.runs) ? research.runs[0] : null,
                            }}
                          />
                          <div className="border border-line rounded p-3 space-y-2" data-testid="research-source-list">
                            <h4 className="text-sm font-medium">已保存来源</h4>
                            {sources.length ? sources.map((source, index) => (
                              <div key={String(source.artifact_id || source.url || index)} className="min-w-0 border-l-2 border-l-accent pl-3 text-sm break-words">
                                {source.url ? <a className="block min-w-0 break-all text-accent underline underline-offset-2" href={String(source.url)} target="_blank" rel="noreferrer">{String(source.title || source.url)}</a> : <span>{String(source.title || '未命名来源')}</span>}
                                <div className="text-xs text-ink-faint">{String(source.source_type || 'web_page')} · {String(source.fact_type || 'unknown')} · {String(source.polarity || 'unknown')} · {String(source.publish_date || source.published_at || source.access_date || '日期未知')}</div>
                              </div>
                            )) : <p className="text-sm text-ink-ghost">尚无真实研究结果；未配置或失败来源不会生成替代数据。</p>}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
                <div className="panel p-4 space-y-3">
                  <h3 className="font-display text-xl">证据版本链</h3>
                  <p className="text-xs text-ink-faint">失效或合并前先查看影响范围；操作只创建新 Artifact 版本，不删除历史。</p>
                  {evidenceImpact && <Section title="最近影响预览" value={evidenceImpact} />}
                  {(() => {
                    const items = Array.isArray((data.phase2?.evidence as Row)?.items) ? (data.phase2!.evidence as Row).items as Row[] : [];
                    return items.length ? items.map((item) => {
                      const artifactId = String(item.artifact_id || '');
                      const invalid = item.status === 'invalid' || item.status === 'merged' || item.status === 'deleted';
                      return <div key={artifactId} id={`evidence-${artifactId}`} className="border border-line rounded p-3 space-y-2"><div className="text-sm font-medium">{String(item.claim || item.title || '未命名证据')}</div><div className="text-xs text-ink-faint">{String(item.evidence_type || '')} · {invalid ? (item.status === 'deleted' ? '已删除' : '已失效/已合并') : '有效'} · v{String(item.version || '')}</div><div className="flex gap-2 flex-wrap"><button type="button" className="btn-secondary text-xs" onClick={() => void editEvidence(item)}>编辑</button><button type="button" className="btn-secondary text-xs" onClick={() => void previewEvidenceImpact(artifactId)}>查看影响</button><button type="button" className="btn-secondary text-xs" onClick={() => void updateEvidenceStatus(artifactId, invalid ? 'active' : 'invalid', Number(item.version || 0))}>{invalid ? '恢复证据' : '标记无效'}</button>{!invalid && <><button type="button" className="btn-secondary text-xs" onClick={() => void deleteEvidence(artifactId, Number(item.version || 0))}>删除证据</button><select className="input text-xs" value={evidenceMergeTarget} onChange={(event) => setEvidenceMergeTarget(event.target.value)} aria-label={`合并证据 ${artifactId}`}><option value="">选择合并目标</option>{items.filter((candidate) => String(candidate.artifact_id) !== artifactId && candidate.status !== 'invalid' && candidate.status !== 'merged' && candidate.status !== 'deleted').map((candidate) => <option key={String(candidate.artifact_id)} value={String(candidate.artifact_id)}>{String(candidate.claim || candidate.title || candidate.artifact_id)}</option>)}</select><button type="button" className="btn-secondary text-xs" disabled={!evidenceMergeTarget} onClick={() => void mergeEvidence(artifactId, Number(item.version || 0), items)}>合并</button></>}</div></div>;
                    }) : <p className="text-sm text-ink-faint">尚无证据记录。</p>;
                  })()}
                </div>
                <div className="grid gap-4 lg:grid-cols-3">
                  <Section title="当前阶段" value={localSummary(data.local)['当前阶段'] || String(data.project?.current_stage || '未知')} />
                  <Section title="已形成资料" value={`${artifactCount()} 份`} />
                  <Section title="执行任务" value={`${data.tasks?.length || 0} 个`} />
                </div>
                <Section
                  title="当前类型对应的关键下一步"
                  description="软件显示实现/测试，嵌入式显示采购/装配/固件/串口，混合项目显示协议/模拟器/集成测试。"
                  value={data.phase2?.next_action || { project_type: data.project?.project_type, next_steps: data.project?.next_steps }}
                />
                {data.project?.project_type === 'hybrid' && (() => {
                  const tracks = (data.phase2?.parallel_tracks || {}) as Row;
                  const names: Record<string, string> = { software: '软件', hardware: '硬件', protocol: '协议', integration: '集成' };
                  return <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">混合项目并行轨道</h3><p className="text-xs text-ink-faint">软件、硬件、协议和集成轨道独立保存进度；每次推进都经过方案、协议和 Artifact 门禁。</p><div className="grid gap-2 md:grid-cols-2">{Object.entries(tracks).map(([track, value]) => { const item = (value || {}) as Row; const complete = item.state === 'completed'; const trackLabel = names[track] || TRACK_NAMES[track] || track; const currentStage = String(item.current_stage || item.next_stage || ''); return <div key={track} className="border border-line rounded p-3 space-y-2"><div className="flex items-center justify-between"><strong>{trackLabel}</strong><span className="text-xs text-ink-faint">{item.state === 'completed' ? '已完成' : item.state === 'active' ? '进行中' : item.state === 'blocked' ? '已阻塞' : '待启动'}</span></div><div className="text-xs text-ink-soft">当前：{currentStage ? (STAGE_NAMES[currentStage] || currentStage) : '等待方案确认'}</div><button type="button" className="btn-secondary text-xs" disabled={complete} onClick={() => void advanceHybridTrack(track)}>{complete ? '轨道已完成' : `推进${trackLabel}轨道`}</button></div>; })}</div><Section title="并行轨道详情" value={tracks} /></div>;
                })()}
                <Section title="本地成果" description="工作区中真实存在的软件、交付物与阶段记录" value={localSummary(data.local)} />
              </>
            )}
            {tab === 'decisions' && (
              <>
                <div className="panel p-4 space-y-3">
                  <h3 className="font-display text-xl">方案确认</h3>
                  <p className="text-xs text-ink-faint">未确认方案前，软件、硬件和协议实现均不可进入。候选方案必须来自真实研究结果；没有结果时不会生成替代数据。</p>
                  {solutionComparison ? (
                    <>
                      <div className="grid gap-2 md:grid-cols-3">
                        {((solutionComparison.solutions as unknown[]) || []).map((candidate, index) => {
                          const item = (candidate || {}) as Row;
                          const name = String(item.name || item.solution || `方案 ${index + 1}`);
                          return <div key={`${name}-${index}`} className="border border-line rounded p-3 space-y-2"><div className="font-medium text-sm">{name}</div><Value value={item.dimension_scores || item.summary || item.solution} /><button type="button" className="btn-primary text-xs" onClick={() => void saveSolution('select')}>确认此方案</button></div>;
                        })}
                      </div>
                      <div className="flex gap-2 flex-wrap"><button type="button" className="btn-secondary text-xs" onClick={() => void saveSolution('compose')}>组合并确认</button><button type="button" className="btn-secondary text-xs" disabled={planningBusy} onClick={() => void requestSolutionCandidates(true)}>{planningBusy ? '正在重新生成…' : '重新生成方案'}</button><button type="button" className="btn-secondary text-xs" onClick={() => void saveSolution('revoke')}>撤销当前确认</button><button type="button" className="btn-secondary text-xs" onClick={() => void saveSolution('reject')}>拒绝当前方案</button></div>
                    </>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-sm text-ink-faint">尚无方案比较。方案 Agent 会先检查真实研究和证据；资料不足时只报告阻塞原因，不生成替代数据。</p>
                      <button type="button" data-testid="request-solution-candidates" className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-45" disabled={planningBusy} onClick={() => void requestSolutionCandidates()}>
                        {planningBusy ? '正在请求方案 Agent…' : '请求方案 Agent 生成三案'}
                      </button>
                    </div>
                  )}
                </div>
                <div className="panel p-4 space-y-3">
                  <h3 className="font-display text-xl">记录项目决策</h3>
                  <input className="input" value={decision} onChange={(event) => setDecision(event.target.value)} placeholder="做出了什么决定？" />
                  <textarea className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="为什么这样决定？依据和取舍是什么？" rows={2} />
                  <button type="button" onClick={() => void saveDecision()} disabled={!decision.trim()} className="btn-primary text-sm">保存决策</button>
                </div>
                <Section title="决策记录" value={data.decisions} />
                <Section title="方案影响任务" description="确认方案后自动生成并持久化的 PRD、技术方案、采购、测试和文件任务。" value={(data.phase2?.solutions as Row)?.impacts || []} />
                <Section title="方案候选与证据闭环" value={{ solutions: data.phase2?.solutions, evidence: data.phase2?.evidence, research: data.phase2?.research }} />
              </>
            )}
            {tab === 'procurement' && (
              <>
                <Section title="当前硬件资料" value={data.phase2?.hardware || data.sections?.hardware} />
                <div className="panel p-4 space-y-3">
                  <h3 className="font-display text-xl">ESP32 硬件闭环</h3>
                  <p className="text-xs text-ink-faint">先只读发现设备，再由用户确认板卡、供电、LED/串口目标。没有设备时会明确显示 BLOCKED。</p>
                  <div className="border border-line rounded p-3 space-y-2"><h4 className="font-medium text-sm">工具链状态与修复</h4><p className="text-xs text-ink-faint">只读检查不会推断板卡已连接；缺少 Arduino CLI/PlatformIO 或板卡核心时可从这里重试修复。</p><div className="flex gap-2 flex-wrap"><button type="button" className="btn-secondary text-xs" disabled={toolchainBusy} onClick={() => void inspectToolchain()}>检查工具链</button><button type="button" className="btn-secondary text-xs" disabled={toolchainBusy} onClick={() => void repairToolchain()}>修复工具链</button><button type="button" className="btn-secondary text-xs" disabled={toolchainBusy} onClick={() => void installCores()}>安装板卡核心</button></div>{hardwareTools && <Section title="最近工具链状态" value={hardwareTools} />}</div>
                  <div className="grid gap-2 md:grid-cols-3"><input className="input" value={hardwareBoard} onChange={(event) => setHardwareBoard(event.target.value)} placeholder="板卡 FQBN，例如 esp32:esp32:esp32" /><input className="input" value={hardwarePort} onChange={(event) => setHardwarePort(event.target.value)} placeholder="串口，例如 /dev/cu.usbserial" /><input className="input" value="115200" readOnly aria-label="波特率" /></div>
                  <div className="flex gap-2 flex-wrap"><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runHardware('list_ports')}>只读发现设备</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runHardware('prepare_serial_probe')}>准备串口探针</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runHardware('compile')}>编译固件</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy || !hardwarePort} onClick={() => void runHardware('upload')}>上传固件</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy || !hardwarePort} onClick={() => void runHardware('monitor')}>串口观察</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runHardware('list_ports')}>拔插后重新发现</button></div>
                  <div className="border-t border-line pt-3 space-y-2"><h4 className="font-medium text-sm">协议模拟器 / 串口协议测试</h4><p className="text-xs text-ink-faint">仅发送用户确认的版本化 JSON；Fake 不接触设备，serial 需要真实串口。未定义 BLE/GATT/OTA。</p><div className="flex gap-2 flex-wrap"><select className="input" value={protocolTransport} onChange={(event) => setProtocolTransport(event.target.value as 'fake' | 'serial')} aria-label="协议传输方式"><option value="fake">Fake 模拟器</option><option value="serial">真实串口</option></select><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runProtocolMessage()}>执行协议测试</button><button type="button" className="btn-secondary text-sm" disabled={hardwareBusy} onClick={() => void runHardware('protocol_scenarios')}>运行六种模拟场景</button><button type="button" className="btn-primary text-sm" onClick={() => void confirmProtocol()}>确认此协议版本</button></div><textarea className="input font-mono text-xs" value={protocolMessage} onChange={(event) => setProtocolMessage(event.target.value)} rows={3} aria-label="版本化协议消息" /></div>{projectType === 'hybrid' && <div className="border-t border-line pt-3 space-y-2"><h4 className="font-medium text-sm">软硬件集成测试</h4><p className="text-xs text-ink-faint">协议场景通过后，记录应用、API、传输和设备之间的实际集成结果；Fake 结果不能替代 ESP32 实物证据。</p><textarea className="input" value={integrationTest} onChange={(event) => setIntegrationTest(event.target.value)} placeholder="集成测试步骤、实际结果、失败恢复和证据" rows={3} aria-label="集成测试记录" /><button type="button" className="btn-primary text-sm" disabled={!integrationTest.trim()} onClick={() => void saveIntegrationTest()}>保存集成测试记录</button></div>}
                  {hardwareResult && <Section title="最近一次硬件运行" value={hardwareResult} />}
                  <div className="border-t border-line pt-3 space-y-2"><h4 className="font-medium text-sm">Ask question：用户确认实际行为</h4><p className="text-xs text-ink-faint">请回答：LED/串口实际行为是否符合预期，且拔插后是否已恢复？选择“不符合/暂不确认”会明确保持 BLOCKED。只有板卡识别、编译、上传、串口观察和拔插后重新发现全部成功，且用户回答“符合”时，才允许保存实物确认。</p>{!physicalAcceptanceReady && <p className="text-xs text-warning">尚缺：{physicalAcceptanceMissing.join('、')}</p>}<textarea className="input" value={hardwareObserved} onChange={(event) => setHardwareObserved(event.target.value)} placeholder="请描述 LED/串口实际表现、拔插后是否恢复；没有实物时不要填写通过结论。" rows={2} /><div role="group" aria-label="硬件实际行为 Ask question" className="flex gap-2 flex-wrap"><button type="button" className={`btn-secondary text-sm ${hardwareQuestionAnswered && hardwareBehaviorConfirmed ? 'border-accent text-accent' : ''}`} onClick={() => answerHardwareQuestion(true)}>符合，拔插后已恢复</button><button type="button" className={`btn-ghost text-sm ${hardwareQuestionAnswered && !hardwareBehaviorConfirmed ? 'border-warning text-warning' : ''}`} onClick={() => answerHardwareQuestion(false)}>不符合/暂不确认</button></div><button type="button" className="btn-primary text-sm" disabled={!hardwareObserved.trim() || !hardwareQuestionAnswered || !hardwareBehaviorConfirmed || !physicalAcceptanceReady} onClick={() => void saveHardwareAcceptance()}>保存实物确认</button></div>
                </div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">硬件方案</h3><p className="text-xs text-ink-faint">先记录控制器、输入/输出、供电和安全边界，再进入 BOM 和接线。</p><textarea className="input" value={hardwareArchitecture} onChange={(event) => setHardwareArchitecture(event.target.value)} placeholder="控制器、传感器、输出、供电、通信和安全边界" rows={3} aria-label="硬件方案" /><button type="button" className="btn-primary text-sm" disabled={!hardwareArchitecture.trim()} onClick={() => void saveHardwareArchitecture()}>保存硬件方案</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">记录采购变化</h3><textarea className="input" value={procurement} onChange={(event) => setProcurement(event.target.value)} placeholder="型号、数量、供应商、采购状态或替代件" rows={3} /><button type="button" className="btn-primary text-sm" disabled={!procurement.trim()} onClick={() => void saveArtifact('hardware_bom', 'Desktop Procurement Update', procurement)}>保存采购记录</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">结构化 BOM 条目</h3><div className="grid gap-2 md:grid-cols-2"><input className="input" value={bomModel} onChange={(event) => setBomModel(event.target.value)} placeholder="精确型号" aria-label="精确型号" /><input className="input" value={bomQuantity} onChange={(event) => setBomQuantity(event.target.value)} inputMode="numeric" placeholder="数量" aria-label="数量" /><input className="input" value={bomPrice} onChange={(event) => setBomPrice(event.target.value)} placeholder="单价" aria-label="单价" /><input className="input" value={bomVendor} onChange={(event) => setBomVendor(event.target.value)} placeholder="供应商" aria-label="供应商" /><input className="input" value={bomAlternative} onChange={(event) => setBomAlternative(event.target.value)} placeholder="替代型号" aria-label="替代型号" /><input className="input" value={bomCompatibility} onChange={(event) => setBomCompatibility(event.target.value)} placeholder="兼容性" aria-label="兼容性" /><input className="input md:col-span-2" value={bomLink} onChange={(event) => setBomLink(event.target.value)} placeholder="采购链接" aria-label="采购链接" /></div><select className="input" value={bomStatus} onChange={(event) => setBomStatus(event.target.value)} aria-label="采购状态"><option value="not_purchased">未购买</option><option value="ordered">已下单</option><option value="in_transit">运输中</option><option value="delivered">已到货</option><option value="inspected">已检查</option><option value="installed">已安装</option><option value="already_owned">已有</option></select><button type="button" className="btn-primary text-sm" disabled={!bomModel.trim()} onClick={() => void saveBomItem()}>保存 BOM 条目</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">结构化接线设计</h3><p className="text-xs text-ink-faint">记录两端引脚、电压、电流方向、公共地/目标类型和禁止条件；保存后可刷新恢复。</p><div className="grid gap-2 md:grid-cols-2"><input className="input" value={wireDevice} onChange={(event) => setWireDevice(event.target.value)} placeholder="设备/元件" aria-label="接线设备" /><input className="input" value={wirePin} onChange={(event) => setWirePin(event.target.value)} placeholder="设备引脚" aria-label="设备引脚" /><input className="input" value={wireTarget} onChange={(event) => setWireTarget(event.target.value)} placeholder="目标引脚" aria-label="目标引脚" /><select className="input" value={wireTargetType} onChange={(event) => setWireTargetType(event.target.value)} aria-label="目标类型"><option value="controller">控制器</option><option value="power">电源</option><option value="gnd">公共地 GND</option><option value="sensor">传感器</option></select><input className="input" value={wireVoltage} onChange={(event) => setWireVoltage(event.target.value)} placeholder="电压，例如 3.3V" aria-label="接线电压" /><input className="input" value={wireCurrentDirection} onChange={(event) => setWireCurrentDirection(event.target.value)} placeholder="电流方向" aria-label="电流方向" /></div><textarea className="input" value={wireSafety} onChange={(event) => setWireSafety(event.target.value)} placeholder="安全/禁止条件（每行一条）" rows={2} aria-label="接线安全条件" /><button type="button" className="btn-primary text-sm" disabled={!wireDevice.trim() || !wirePin.trim() || !wireTarget.trim()} onClick={() => void saveWiring()}>保存接线设计</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">固件项目定义</h3><p className="text-xs text-ink-faint">先保存平台、板卡、版本和源码/文件，再执行编译、上传和串口观察；运行结果会回写到硬件记录。</p><div className="grid gap-2 md:grid-cols-2"><select className="input" value={firmwarePlatform} onChange={(event) => setFirmwarePlatform(event.target.value)} aria-label="固件平台"><option value="esp32">ESP32</option><option value="arduino">Arduino</option><option value="platformio">PlatformIO</option></select><select className="input" value={firmwareFramework} onChange={(event) => setFirmwareFramework(event.target.value)} aria-label="固件框架"><option value="arduino">Arduino</option><option value="esp-idf">ESP-IDF</option><option value="platformio">PlatformIO</option></select><input className="input" value={hardwareBoard} onChange={(event) => setHardwareBoard(event.target.value)} placeholder="板卡/FQBN" aria-label="固件板卡" /><input className="input" value={firmwareVersion} onChange={(event) => setFirmwareVersion(event.target.value)} placeholder="固件版本" aria-label="固件版本" /></div><input className="input" value={firmwareSource} onChange={(event) => setFirmwareSource(event.target.value)} placeholder="源码目录或仓库链接" aria-label="固件源码" /><textarea className="input" value={firmwareFiles} onChange={(event) => setFirmwareFiles(event.target.value)} placeholder="固件文件（每行一个）" rows={2} aria-label="固件文件" /><button type="button" className="btn-primary text-sm" disabled={!hardwareBoard.trim() || !firmwareVersion.trim()} onClick={() => void saveFirmware()}>保存固件定义</button></div>
              </>
            )}
            {tab === 'maker' && (
              <>
                <Section title="Maker 装配记录" value={(data.phase2?.hardware as Row)?.assembly_steps || (data.sections?.hardware as Row)?.assembly_steps} />
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">确认装配步骤</h3><textarea className="input" value={maker} onChange={(event) => setMaker(event.target.value)} placeholder="元件、动作、预期结果、安全提示、照片说明和完成确认" rows={3} /><button type="button" className="btn-primary text-sm" disabled={!maker.trim()} onClick={() => void saveArtifact('hardware_maker_step', 'Desktop Maker Step', maker)}>保存装配确认</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">结构化 Maker 步骤</h3><input className="input" value={makerComponent} onChange={(event) => setMakerComponent(event.target.value)} placeholder="涉及元件" aria-label="涉及元件" /><input className="input" value={makerAction} onChange={(event) => setMakerAction(event.target.value)} placeholder="装配动作" aria-label="装配动作" /><input className="input" value={makerExpected} onChange={(event) => setMakerExpected(event.target.value)} placeholder="预期结果" aria-label="预期结果" /><input className="input" value={makerSafety} onChange={(event) => setMakerSafety(event.target.value)} placeholder="安全提示" aria-label="安全提示" /><input className="input" value={makerPhoto} onChange={(event) => setMakerPhoto(event.target.value)} placeholder="照片路径或说明（可选）" aria-label="照片说明" /><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={makerConfirmed} onChange={(event) => setMakerConfirmed(event.target.checked)} />我已完成并确认此步骤</label><button type="button" className="btn-primary text-sm" disabled={!makerComponent.trim() || !makerAction.trim()} onClick={() => void saveMakerStep()}>保存结构化步骤</button></div>
              </>
            )}
            {tab === 'testing' && (
              <>
                <Section title="测试与缺陷" value={{ testing: data.phase2?.testing || data.sections?.testing, defects: data.phase2?.defects }} />
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">需求追踪测试用例</h3><p className="text-xs text-ink-faint">每个用例保存需求引用、前置步骤、预期结果和状态；刷新后继续显示在测试矩阵中。</p><div className="grid gap-2 sm:grid-cols-2"><input className="input" value={testCaseId} onChange={(event) => setTestCaseId(event.target.value)} placeholder="用例编号" aria-label="用例编号" /><input className="input" value={testCaseName} onChange={(event) => setTestCaseName(event.target.value)} placeholder="用例名称" aria-label="用例名称" /><input className="input sm:col-span-2" value={testCaseRequirement} onChange={(event) => setTestCaseRequirement(event.target.value)} placeholder="关联需求或 PRD 编号" aria-label="关联需求" /></div><textarea className="input" value={testCaseSteps} onChange={(event) => setTestCaseSteps(event.target.value)} placeholder="执行步骤（每行一步）" rows={2} aria-label="测试步骤" /><textarea className="input" value={testCaseExpected} onChange={(event) => setTestCaseExpected(event.target.value)} placeholder="预期结果" rows={2} aria-label="预期结果" /><button type="button" className="btn-primary text-sm" disabled={!testCaseName.trim() || !testCaseExpected.trim()} onClick={() => void saveTestCase()}>保存测试用例</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">记录测试结果</h3><div className="grid gap-2 sm:grid-cols-2"><select className="input" value={testResultStatus} onChange={(event) => setTestResultStatus(event.target.value)} aria-label="测试结果状态"><option value="passed">通过</option><option value="failed">失败</option><option value="error">错误</option><option value="skipped">跳过</option></select><input className="input" value={testDefectOwner} onChange={(event) => setTestDefectOwner(event.target.value)} placeholder="缺陷负责人（失败时）" aria-label="缺陷负责人" /></div><textarea className="input" value={testResult} onChange={(event) => setTestResult(event.target.value)} placeholder="实际结果；失败/错误会自动建立缺陷记录" rows={3} /><textarea className="input" value={testEvidence} onChange={(event) => setTestEvidence(event.target.value)} placeholder="测试证据（截图、日志或 Artifact ID，每行一项）" rows={2} aria-label="测试证据" /><button type="button" className="btn-primary text-sm" disabled={!testResult.trim()} onClick={() => void saveTest()}>保存测试结果</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">缺陷回归</h3><textarea className="input" value={regressionNotes} onChange={(event) => setRegressionNotes(event.target.value)} placeholder="修复说明和原用例实际结果" rows={2} /><button type="button" className="btn-secondary text-sm" onClick={() => void saveRegression()}>保存原用例回归通过</button></div>
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">保存验证报告</h3><p className="text-xs text-ink-faint">最终报告只允许四种结论，并且需要三名不同目标用户；每条反馈必须记录用户类型和实际验证任务。不足时接口会拒绝保存。</p><div className="grid gap-2 sm:grid-cols-2"><select className="input" value={validationConclusion} onChange={(event) => setValidationConclusion(event.target.value)} aria-label="验证结论"><option value="continue_release">继续发布</option><option value="release_after_fix">修复后发布</option><option value="reduce_scope">缩小范围</option><option value="stop_project">停止项目</option></select><input className="input" value={validationMetrics} onChange={(event) => setValidationMetrics(event.target.value)} placeholder="成功指标（例如 3/3 完成任务）" /></div><button type="button" className="btn-primary text-sm" onClick={() => void saveValidationReport()}>保存验证报告</button></div>
              </>
            )}
            {tab === 'improvements' && (
              <>
                <Section title="现有改进建议" value={data.sections?.improvement} />
                <div className="panel p-4 space-y-3"><h3 className="font-display text-xl">记录改进建议</h3><textarea className="input" value={improvement} onChange={(event) => setImprovement(event.target.value)} placeholder="建议、证据、预期收益、风险、工作量和接受/延期理由" rows={3} /><button type="button" className="btn-primary text-sm" disabled={!improvement.trim()} onClick={() => void saveImprovement()}>保存改进建议</button><p className="text-xs text-ink-faint">当前状态：{improvementStatus}</p><div className="flex gap-2 flex-wrap"><button type="button" className="btn-secondary text-xs" disabled={!improvement.trim()} onClick={() => void saveImprovement('accepted')}>接受</button><button type="button" className="btn-secondary text-xs" disabled={!improvement.trim()} onClick={() => void saveImprovement('ignored')}>忽略</button><button type="button" className="btn-secondary text-xs" disabled={!improvement.trim()} onClick={() => void saveImprovement('deferred')}>延期</button><button type="button" className="btn-secondary text-xs" disabled={!improvement.trim()} onClick={() => void saveImprovement('hidden')}>隐藏</button><button type="button" className="btn-secondary text-xs" disabled={!improvement.trim()} onClick={() => void saveImprovement('deleted')}>删除</button></div></div>
              </>
            )}
            {tab === 'feedback' && (
              <div className="space-y-3">
                <Section title="已有用户验证" value={data.phase2?.user_validation} />
                <div className="panel p-4 space-y-3">
                <h3 className="font-display text-xl">记录真实用户反馈</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input className="input" value={feedbackParticipantId} onChange={(event) => setFeedbackParticipantId(event.target.value)} placeholder="参与者编号（如 U-01，可匿名）" />
                  <input className="input" value={feedbackUserType} onChange={(event) => setFeedbackUserType(event.target.value)} placeholder="用户类型（例如 maker）" />
                  <input className="input" value={feedbackTask} onChange={(event) => setFeedbackTask(event.target.value)} placeholder="执行任务" />
                  <select className="input" value={feedbackCompleted} onChange={(event) => setFeedbackCompleted(event.target.value)} aria-label="任务是否完成">
                    <option value="unknown">完成情况未记录</option><option value="yes">任务完成</option><option value="no">任务未完成</option>
                  </select>
                  <input className="input" inputMode="numeric" value={feedbackDuration} onChange={(event) => setFeedbackDuration(event.target.value)} placeholder="耗时（秒）" />
                  <input className="input" inputMode="numeric" min="1" max="5" value={feedbackSatisfaction} onChange={(event) => setFeedbackSatisfaction(event.target.value)} placeholder="满意度（1-5）" />
                </div>
                <textarea className="input" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="用户完成了什么、遇到什么问题、是否愿意继续使用？" rows={3} />
                <textarea className="input" value={feedbackBlockers} onChange={(event) => setFeedbackBlockers(event.target.value)} placeholder="阻塞点（每行一项）" rows={2} />
                <textarea className="input" value={feedbackQuote} onChange={(event) => setFeedbackQuote(event.target.value)} placeholder="用户原话" rows={2} />
                <button type="button" onClick={() => void saveFeedback()} disabled={!feedback.trim()} className="btn-primary text-sm">保存反馈</button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
