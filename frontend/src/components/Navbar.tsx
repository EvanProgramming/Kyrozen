import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { logout } from '../api/auth';

export function Navbar() {
  const user = useAuthStore((state) => state.user);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      clearAuth();
      navigate('/login');
    }
  };

  return (
    <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-warm-200">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-sky-500 flex items-center justify-center">
            <span className="text-white font-serif text-lg font-medium">K</span>
          </div>
          <span className="font-serif text-xl text-warm-900">Kyrozen</span>
        </Link>

        <div className="flex items-center gap-6">
          <Link
            to="/projects"
            className="text-sm font-medium text-warm-600 hover:text-warm-900 transition-colors"
          >
            项目
          </Link>
          <Link
            to="/dashboard"
            className="text-sm font-medium text-warm-600 hover:text-warm-900 transition-colors"
          >
            控制台
          </Link>

          <div className="flex items-center gap-3 pl-6 border-l border-warm-200">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-warm-900">
                {user?.name || user?.email}
              </p>
              <p className="text-xs text-warm-500">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="btn-secondary text-sm px-4 py-2"
            >
              退出
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
