/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 纸面（暖米色系，源自 claude.ai 背景）
        paper: {
          DEFAULT: '#f0eee6',
          sink: '#eae8dc',
          edge: '#e1ded2',
        },
        surface: '#faf9f2',
        // 墨色文字（源自 moraxcheng.me）
        ink: {
          DEFAULT: '#201b15',
          soft: '#4e4841',
          faint: '#6e6862',
          ghost: '#8a857e',
        },
        // 深蓝强调
        accent: {
          DEFAULT: '#1e40af',
          deep: '#1e3a8a',
          soft: '#dce5f7',
        },
        // 手绘荧光笔
        hl: {
          green: '#dce7c5',
          blue: '#d9e4f7',
        },
        // 功能色（暖调）
        success: { DEFAULT: '#3f7a44', soft: '#e0ead9' },
        warning: { DEFAULT: '#b5641e', soft: '#f2e5d0' },
        danger: { DEFAULT: '#b44434', soft: '#f3deda' },
      },
      borderColor: {
        line: 'rgba(32, 27, 21, 0.14)',
        'line-strong': 'rgba(32, 27, 21, 0.3)',
      },
      fontFamily: {
        display: ['Caveat', 'Noto Serif SC', 'Songti SC', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['Spline Sans Mono', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      borderRadius: {
        sm: '2px',
        DEFAULT: '4px',
      },
      // 扁平化：全项目禁用投影
      boxShadow: {
        none: 'none',
      },
    },
  },
  plugins: [],
};
