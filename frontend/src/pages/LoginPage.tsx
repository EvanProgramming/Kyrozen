import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { login } from '../api/auth';
import { useAuthStore } from '../stores/authStore';
import { handleApiError } from '../api/client';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const setAuth = useAuthStore((state) => state.setAuth);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const response = await login({ email, password });
      setAuth(response.user, response.access_token, response.refresh_token);
      navigate('/dashboard');
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-warm-50 flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="w-12 h-12 rounded-xl bg-sky-500 flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-serif text-2xl font-medium">K</span>
          </div>
          <h1 className="text-3xl mb-2">欢迎回到 Kyrozen</h1>
          <p className="text-warm-500">登录你的账户，继续产品开发之旅</p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="email" className="label">邮箱</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="label">密码</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
                required
              />
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="btn-primary w-full disabled:opacity-60"
            >
              {isLoading ? '登录中...' : '登录'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-warm-500">
            还没有账户？{' '}
            <Link to="/register" className="text-sky-600 hover:text-sky-700 font-medium">
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
