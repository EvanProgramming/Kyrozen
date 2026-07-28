import { ConnectionState } from '../App';

interface Props {
  state: ConnectionState;
  message: string;
}

const colorMap: Record<ConnectionState, string> = {
  disconnected: 'bg-ink-ghost',
  connecting: 'bg-warning',
  connected: 'bg-success',
  error: 'bg-danger',
};

export function ConnectionStatus({ state, message }: Props) {
  return (
    <div className={`h-7 flex items-center px-3 text-xs text-white ${colorMap[state]}`}>
      <span className="font-medium mr-2">
        {state === 'connected' ? '已连接' : state === 'connecting' ? '连接中' : state === 'error' ? '连接错误' : '未连接'}
      </span>
      <span className="opacity-90 truncate">{message}</span>
    </div>
  );
}
