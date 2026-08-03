import { useEffect, useState } from 'react';

type PlanKey = 'free' | 'lite' | 'pro' | 'ultimate';

interface MembershipModalProps {
  currentPlan?: string;
  onClose: () => void;
  onRefresh?: () => Promise<void>;
  afdianCallbackVersion?: number;
}

const plans: Array<{
  key: PlanKey;
  name: string;
  price: string;
  projects: string;
  credit: string;
  conversations: string;
  frequency: string;
  note: string;
}> = [
  { key: 'free', name: '免费', price: '¥0', projects: '同时1个 / 月创建1个', credit: '每周1,000', conversations: '每月20次', frequency: '5小时250 Credit', note: '适合体验完整流程' },
  { key: 'lite', name: 'Lite', price: '¥24/月', projects: '同时5个 / 月创建5个', credit: '每周3,000', conversations: '不限', frequency: '5小时750 Credit', note: '适合个人持续使用' },
  { key: 'pro', name: 'Pro', price: '¥140/月', projects: '同时20个 / 月创建20个', credit: '每周10,000', conversations: '不限', frequency: '不限制', note: '额度用尽后安全收尾' },
  { key: 'ultimate', name: 'Ultimate', price: '¥2,999/月', projects: '不限', credit: '不限制（每日频控）', conversations: '不限', frequency: '每日预算 + 4并发', note: '可添加3个家庭成员' },
];

export function MembershipModal({ currentPlan, onClose, onRefresh, afdianCallbackVersion = 0 }: MembershipModalProps) {
  const [notice, setNotice] = useState('');
  const [checkoutId, setCheckoutId] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PlanKey | null>(null);

  useEffect(() => {
    if (!checkoutId || !window.kyrozen) return undefined;
    const poll = async () => {
      const result = await window.kyrozen!.getAfdianPaymentStatus(checkoutId);
      if (result.status === 'paid') {
        setNotice('付款已确认，会员权益已开通。');
        setCheckoutId(null);
        await onRefresh?.();
      } else if (result.status === 'expired') {
        setNotice('付款会话已超时，请重新选择方案。');
        setCheckoutId(null);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => window.clearInterval(timer);
  }, [checkoutId, onRefresh]);

  useEffect(() => {
    if (afdianCallbackVersion > 0 && pendingPlan) {
      const plan = pendingPlan;
      setPendingPlan(null);
      void choosePlan(plan);
    }
  }, [afdianCallbackVersion]);

  const choosePlan = async (plan: PlanKey) => {
    if (plan === currentPlan) return;
    if (!window.kyrozen || plan === 'free') return;
    setNotice('正在创建爱发电付款会话…');
    try {
      const checkout = await window.kyrozen.startAfdianCheckout(plan);
      if (checkout.error) {
        if (checkout.error.includes('绑定')) {
          setPendingPlan(plan);
          const connect = await window.kyrozen.startAfdianConnect();
          setNotice(connect.error ? connect.error : '请在打开的爱发电页面完成授权，授权后回到 Kyrozen 再点击购买。');
        } else {
          setNotice(checkout.error);
        }
        return;
      }
      if (checkout.id) {
        setCheckoutId(checkout.id);
        setNotice('已打开爱发电付款页面，付款后 Kyrozen 会自动确认并刷新权益。');
      }
    } catch (error: any) {
      setNotice(error?.message || '付款会话创建失败，请稍后重试。');
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-labelledby="membership-title">
      <div className="panel w-full max-w-5xl max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h2 id="membership-title" className="font-display text-3xl text-ink">会员功能</h2>
            <p className="text-sm text-ink-soft mt-1">首个测试版暂不开放会员购买和升级。</p>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost text-xl leading-none px-2" aria-label="关闭会员页面">×</button>
        </div>

        {notice && <div role="status" className="mb-4 border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent">{notice}</div>}

        <div className="mb-4 border border-warning/40 bg-warning-soft px-3 py-3 text-sm text-warning">
          当前版本除开发者账号外，所有用户统一按免费方案使用：同时 1 个项目、每月创建 1 个项目、每周 1,000 Credit、每月 20 次对话，并受 5 小时 250 Credit 频率限制。会员方案将在后续版本开放。
        </div>

        <div className="overflow-x-auto border border-line">
          <table className="w-full min-w-[760px] text-sm border-collapse">
            <thead>
              <tr className="bg-paper-sink text-left">
                <th className="p-3 border-b border-line font-medium">权益</th>
                {plans.map((plan) => (
                  <th key={plan.key} className={`p-3 border-b border-line min-w-[150px] ${plan.key === currentPlan ? 'bg-accent-soft' : ''}`}>
                    <div className="font-display text-xl">{plan.name}</div>
                    <div className="font-medium text-ink mt-1">{plan.price}</div>
                    {plan.key === currentPlan && <div className="text-xs text-accent mt-1">当前方案</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th className="p-3 border-b border-line text-left font-normal text-ink-soft">项目额度</th>
                {plans.map((plan) => <td key={plan.key} className="p-3 border-b border-line">{plan.projects}</td>)}
              </tr>
              <tr className="bg-paper-sink/40">
                <th className="p-3 border-b border-line text-left font-normal text-ink-soft">每周 Credit</th>
                {plans.map((plan) => <td key={plan.key} className="p-3 border-b border-line">{plan.credit}</td>)}
              </tr>
              <tr>
                <th className="p-3 border-b border-line text-left font-normal text-ink-soft">对话次数</th>
                {plans.map((plan) => <td key={plan.key} className="p-3 border-b border-line">{plan.conversations}</td>)}
              </tr>
              <tr className="bg-paper-sink/40">
                <th className="p-3 border-b border-line text-left font-normal text-ink-soft">频率限制</th>
                {plans.map((plan) => <td key={plan.key} className="p-3 border-b border-line">{plan.frequency}</td>)}
              </tr>
              <tr>
                <th className="p-3 text-left font-normal text-ink-soft">说明</th>
                {plans.map((plan) => <td key={plan.key} className="p-3">{plan.note}</td>)}
              </tr>
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="btn-primary text-sm">知道了</button>
        </div>
      </div>
    </div>
  );
}
