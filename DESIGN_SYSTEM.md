# Kyrozen 设计系统规范 —— 暖色手绘风

> 本文档是 Kyrozen 全端（桌面客户端 / kyrozen.chat 网页端）UI 的**唯一视觉标准**。
> 目标是让任何开发者或 AI 仅凭本文档，就能在任意技术栈（React/Vue/原生 HTML/Tailwind/纯 CSS）中 1:1 复现完全一致的视觉效果。
> 当前已在 `desktop/`（Electron 客户端）完整落地，落地代码即本文档第 9 章的参考实现。

---

## 1. 设计哲学

**一句话：在一张温暖的纸上，用墨手写产品。**

三个参考原点（色值均为实测提取，非估算）：

| 参考 | 借用了什么 | 实测值 |
|---|---|---|
| claude.ai | 主背景暖米色、界面气质 | 背景 `#F0EEE6`，文字 `#141413` |
| moraxcheng.me | 文字墨色体系、赭石功能色 | ink `#201B15`（oklch(.225 .014 70) 换算） |
| 手绘批注 | 荧光笔高亮、波浪下划线、手写标题 | 见第 6 章 |

**关键词**：暖色调、纸面质感、手绘批注感、编辑感、扁平、克制。

---

## 2. 硬性禁令（违反即错误）

| # | 禁令 | 说明 |
|---|---|---|
| 1 | **禁止任何渐变色** | `linear-gradient` / `radial-gradient` / `conic-gradient` 一律不允许，包括按钮、背景、卡片、头像、进度条。验收时用 grep 检查产物，见第 11 章。 |
| 2 | **禁止投影** | 不使用 `box-shadow`（包括 Tailwind `shadow-*`）。层级靠「底色差 + 1px 实线」表达。 |
| 3 | **禁止圆角卡片** | 卡片/面板圆角最大 2px；按钮/输入框等控件最大 4px。禁止 `rounded-lg/xl/2xl/3xl` 用于任何容器。 |
| 4 | **禁止暗色模式** | 全端只有这一套明亮暖色主题，`color-scheme: light`。不做主题切换。 |
| 5 | **禁止毛玻璃/半透明叠加** | 不用 `backdrop-blur`、不用彩色半透明蒙层做装饰。模态遮罩唯一例外：`--ink` 40% 不透明度的实色遮罩。 |
| 6 | **禁止第二套强调色** | 强调色只有深蓝 `#1E40AF`。不要把紫、青、橙等引入 UI（功能色除外，见 3.4）。 |

允许的小圆角例外（它们是「控件」不是「卡片」）：开关（toggle）轨道与滑块、步骤指示圆点、头像，可用 `rounded-full`。

---

## 3. 色彩系统

### 3.1 三主色（品牌骨架）

| 角色 | Token | 色值 | 用途 |
|---|---|---|---|
| 背景（纸） | `--paper` | `#F0EEE6` | 应用主背景，所有页面的底色 |
| 文字（墨） | `--ink` | `#201B15` | 主文字、标题、强调内容 |
| 强调（深蓝） | `--accent` | `#1E40AF` | 主按钮、链接、选中态描边、聚焦框 |

### 3.2 纸面色阶（背景层次）

| Token | 色值 | 用途 |
|---|---|---|
| `--paper` | `#F0EEE6` | 主背景（页面、聊天区、编辑器底） |
| `--paper-sink` | `#EAE8DC` | 「凹陷」区域：侧栏、代码/原始输出块、进度日志底 |
| `--paper-edge` | `#E1DED2` | 更深的边：悬停态底、未选中步骤点、toggle 关闭态 |
| `--surface` | `#FAF9F2` | 「浮起」区域：顶栏、卡片/面板、AI 消息气泡、模态 |

层次规则：**surface > paper > paper-sink > paper-edge**（亮 → 暗）。面板用 surface，页面底用 paper，侧栏用 paper-sink。禁止给这些底色加任何纹理或渐变。

### 3.3 墨色阶（文字层次）

| Token | 色值 | 用途 |
|---|---|---|
| `--ink` | `#201B15` | 主文字、标题 |
| `--ink-soft` | `#4E4841` | 次要文字、正文段落、label |
| `--ink-faint` | `#6E6862` | 辅助说明、时间戳、占位提示 |
| `--ink-ghost` | `#8A857E` | 输入框 placeholder、禁用态、极弱说明 |

### 3.4 功能色（暖调，仅表语义）

| 语义 | Token | 色值 | 浅色底 Token | 色值 | 用途 |
|---|---|---|---|---|---|
| 成功/已连接 | `--success` | `#3F7A44` | `--success-soft` | `#E0EAD9` | 成功提示、已连接状态、新增文件标记 |
| 警告/高危 | `--warning` | `#B5641E` | `--warning-soft` | `#F2E5D0` | 完全信任模式、变更文件、连接中 |
| 危险/错误 | `--danger` | `#B44434` | `--danger-soft` | `#F3DEDA` | 错误信息、停止按钮、退出登录 |
| 强调浅底 | — | — | `--accent-soft` | `#DCE5F7` | 选中项底色、更新提示条、拖拽悬停区 |

规则：功能色**只用于语义**，不作装饰。深色功能色配白字或用于文字；浅色底配同色系深字。

### 3.5 手绘荧光笔（装饰性，仅两处可用）

| Token | 色值 | 用途 |
|---|---|---|
| `--hl-green` | `#DCE7C5` | 行内实色高亮块（模拟荧光笔涂绿） |
| `--hl-blue` | `#D9E4F7` | 行内实色高亮块（模拟荧光笔涂蓝） |

只允许用于「正文中的行内短语强调」，不允许用于背景、按钮、大面积区块。

### 3.6 线条

| Token | 值 | 用途 |
|---|---|---|
| `--line` | `rgba(32, 27, 21, 0.14)` | 常规分隔线、面板边框（墨色的 14% 透明） |
| `--line-strong` | `rgba(32, 27, 21, 0.30)` | 输入框边框、强调分隔（墨色的 30% 透明） |

所有分区用 **1px 实线**，不用阴影。线是墨色透明化，不是灰色——这保证线条融入暖纸。

### 3.7 完整 CSS 变量定义

```css
:root {
  color-scheme: light;

  /* 纸面 */
  --paper: #f0eee6;
  --paper-sink: #eae8dc;
  --paper-edge: #e1ded2;
  --surface: #faf9f2;

  /* 墨色 */
  --ink: #201b15;
  --ink-soft: #4e4841;
  --ink-faint: #6e6862;
  --ink-ghost: #8a857e;

  /* 线条 */
  --line: rgba(32, 27, 21, 0.14);
  --line-strong: rgba(32, 27, 21, 0.3);

  /* 深蓝强调 */
  --accent: #1e40af;
  --accent-deep: #1e3a8a;
  --accent-soft: #dce5f7;

  /* 荧光笔 */
  --hl-green: #dce7c5;
  --hl-blue: #d9e4f7;

  /* 功能色 */
  --success: #3f7a44;
  --success-soft: #e0ead9;
  --warning: #b5641e;
  --warning-soft: #f2e5d0;
  --danger: #b44434;
  --danger-soft: #f3deda;

  /* 形状 */
  --radius: 4px;        /* 控件 */
  --radius-panel: 2px;  /* 面板/卡片 */
}
```

---

## 4. 字体系统

### 4.1 三个字体角色

| 角色 | 字体栈 | 用途 |
|---|---|---|
| **手绘标题** | `'Caveat', 'Long Cang', 'PingFang SC', cursive` | 品牌名、页面级大标题、面板标题（如「我的项目」「设置」「AI 执行计划」） |
| **正文** | `'Inter', system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif` | 一切正文、按钮、输入框、表格 |
| **等宽** | `'Spline Sans Mono', ui-monospace, 'SF Mono', Menlo, monospace` | 代码、文件路径、日志、版本号 |

- Caveat 覆盖拉丁字母/数字的手写体；Long Cang 覆盖中文手写体。两者必须同时声明，缺一不可。
- 正文字体选择逻辑：claude.ai 的界面字体（Styrene，商业字体不可得）气质是「干净的几何人文无衬线」，Inter 是最接近的免费替代；中文回退到系统黑体（苹方/雅黑）。
- 等宽字体与 moraxcheng.me 保持一致（Spline Sans Mono）。

### 4.2 加载方式（Google Fonts 一条请求）

```css
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@500;600;700&family=Inter:wght@400;500;600;700&family=Long+Cang&family=Spline+Sans+Mono:wght@400;500&display=swap');
```

注意：Long Cang 只有 400 一个字重；Caveat 用 500/600/700。离线环境下字体会回退到系统栈，布局不得依赖字体加载成功。

### 4.3 字级与用法

| 场景 | 类/样式 | 规格 |
|---|---|---|
| 品牌名（顶栏、登录页） | `.font-hand` + `text-2xl`~`text-4xl` | 手绘体，登录页最大（text-4xl） |
| 页面/弹窗标题 | `.font-hand` + `text-2xl` | 手绘体，leading-none |
| 面板小标题（侧栏分区） | `.font-hand` + `text-lg` 或正文 `text-sm font-medium` | 大分区用手绘，小分区用正文半粗 |
| 正文 | `text-sm`（14px）为主 | 行高 1.6 |
| 辅助说明 | `text-xs`（12px）+ `--ink-faint` | — |
| 手绘体使用限制 | 只用于「标题」，**绝不用于正文、按钮、长段落** | 手绘体大面积使用会破坏可读性 |

`.font-hand` 定义：

```css
.font-hand {
  font-family: 'Caveat', 'Long Cang', 'PingFang SC', cursive;
  font-weight: 600;
  letter-spacing: 0.01em;
}
```

---

## 5. 形状、边框与质感

| 元素 | 圆角 | 边框 | 阴影 |
|---|---|---|---|
| 按钮 / 输入框 / 下拉框 | 4px（`--radius`） | 见组件章 | 无 |
| 面板 / 卡片 / 模态 / 消息气泡 | 2px（`--radius-panel`） | 1px `var(--line)` | 无 |
| 标签 chip / 徽章 | 2px | 1px `var(--line-strong)`（可选） | 无 |
| toggle 轨道与滑块 / 步骤圆点 / 头像 | `rounded-full` | 滑块 1px `var(--line-strong)` | 无 |
| 全局 | — | 分区一律 1px 实线 | **全站无阴影** |

其他质感规则：

- **选中文字颜色**：`::selection { background: var(--hl-blue); color: var(--ink); }`——选中即荧光笔涂蓝。
- **滚动条**：8px 细条，thumb 用 `--paper-edge`，hover 用 `--ink-ghost`，track 透明。
- **模态遮罩**：`background: rgba(32, 27, 21, 0.4)`（ink 40%），模态本体 `panel` 样式，无阴影。
- **悬停反馈**：只用「底色变化」（如 `paper-edge` / `paper-sink`），不用位移、放大、阴影变化。过渡 `transition-colors 150ms`。

---

## 6. 手绘元素（本系统签名式的三个细节）

### 6.1 荧光笔行内高亮

实色块，微 padding，用于正文行内短语：

```css
.hl-green { background-color: var(--hl-green); padding: 0 0.15em; }
.hl-blue  { background-color: var(--hl-blue);  padding: 0 0.15em; }
```

```html
<!-- 示例：AI 消息里的行内强调 -->
告诉我你要做什么，比如「<span class="hl-green">帮我写一个读取湿度的函数</span>」。
```

### 6.2 手绘波浪下划线

用**实色描边的 SVG data-URI** 模拟手绘波浪线（注意：这不是渐变，是纯色矢量笔触）：

```css
.wavy-green {
  text-decoration: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='4' viewBox='0 0 24 4'%3E%3Cpath d='M0 2 Q3 0.5 6 2 T12 2 T18 2 T24 2' fill='none' stroke='%233f7a44' stroke-width='1.6'/%3E%3C/svg%3E");
  background-repeat: repeat-x;
  background-position: 0 100%;
  padding-bottom: 3px;
}
.wavy-blue {
  text-decoration: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='4' viewBox='0 0 24 4'%3E%3Cpath d='M0 2 Q3 0.5 6 2 T12 2 T18 2 T24 2' fill='none' stroke='%231e40af' stroke-width='1.6'/%3E%3C/svg%3E");
  background-repeat: repeat-x;
  background-position: 0 100%;
  padding-bottom: 3px;
}
```

绿色版 stroke 为 `--success`（#3f7a44 → `%233f7a44`），蓝色版为 `--accent`（#1e40af → `%231e40af`）。改色时同步改 SVG 里的 stroke。

### 6.3 手绘标题

见 4.3。品牌名和页面标题用手绘体，是「这张纸是人写的」的关键信号。但不要滥用——一个屏幕里手绘体出现 1~3 处为宜。

---

## 7. 组件规范

以下类名基于 CSS 组件类（见第 9 章完整代码），用 Tailwind 时直接组合工具类也可，但**视觉结果必须一致**。

### 7.1 按钮（5 个变体）

通用：4px 圆角、实色、无阴影、`px-4 py-2`、font-medium、禁用 `opacity-50`。

| 变体 | 背景 | 文字 | 边框 | 用途 |
|---|---|---|---|---|
| `.btn-primary` | `--accent`，hover `--accent-deep` | 白 | 无 | 主操作（发送/保存/登录/授权） |
| `.btn-secondary` | `--surface`，hover `--paper-sink` | `--ink-soft` → `--ink` | 1px `--line-strong` | 次操作（设置/关闭/重新授权） |
| `.btn-ghost` | 透明，hover `--paper-sink` | `--ink-faint` → `--ink` | 无 | 轻操作（导入/预览工具条） |
| `.btn-danger` | `--danger`，hover `#96362a` | 白 | 无 | 停止/删除 |
| `.btn-success` | `--success`，hover `#356639` | 白 | 无 | 引导流程的「下一步/完成」 |

### 7.2 输入框 `.input`

`surface` 底 + 1px `--line-strong` 边框 + 4px 圆角；placeholder 用 `--ink-ghost`；聚焦时边框变为 `--accent`（不加 ring、不发光）；`px-3 py-2 text-sm`。

### 7.3 面板 `.panel`

`surface` 底 + 1px `--line` 边框 + 2px 圆角，无阴影。所有「卡片」场景（Git 面板的分组块、登录卡、设置弹窗、提示条）统一用它。

### 7.4 列表选中态（签名模式）

侧边栏项目、文件树、搜索结果等列表的选中项，**不用实底反白**，而用「浅蓝底 + 左侧深蓝竖条」：

```
选中：background: var(--accent-soft); border-left: 2px solid var(--accent); color: var(--ink);
未选中：border-left: 2px solid transparent; color: var(--ink-soft); hover 底色 var(--paper-edge);
圆角：2px（rounded-sm）
```

### 7.5 聊天气泡

| 角色 | 样式 |
|---|---|
| 用户 | `--accent` 实底白字，2px 圆角，右对齐，max-width 80% |
| AI / 系统 | `surface` 底 + 1px `--line` 边框 + `--ink` 字，2px 圆角，max-width 80% |
| 原始输出块 | `paper-sink` 底 + 1px `--line` + 等宽字体 text-xs |

### 7.6 开关（toggle）

轨道 `w-8 h-4 rounded-full`：开启 = 语义色（信任模式用 `--warning`，普通开关用 `--accent`），关闭 = `--paper-edge`；滑块 `w-3 h-3 rounded-full` `surface` 底 + 1px `--line-strong` 边框，开启时 `translate-x-4`。

### 7.7 步骤指示器

圆点 `w-8 h-8 rounded-full`：已完成/当前 = `--accent` 底白字，未到 = `--paper-edge` 底 `--ink-faint` 字；连接线 `h-0.5`：已通过 `--accent`，未通过 `--paper-edge`。

### 7.8 状态徽章

文字徽章：浅色功能底（`--success-soft` 等）+ 同系深色字 + 2px 圆角，如「已连接」。

### 7.9 连接状态条（桌面端顶条）

高 28px（h-7），白字 text-xs，整条实色：已连接 `--success` / 连接中 `--warning` / 错误 `--danger` / 未连接 `--ink-ghost`。

### 7.10 链接

正文内链接：`--accent` 色 + `underline`，hover `--accent-deep`。消息中的本地预览地址同此。

---

## 8. 布局规范（桌面客户端应用壳）

```
┌──────────────────────────────────────────────────┐
│ 连接状态条 h-7（实色）                              │
├──────────────────────────────────────────────────┤
│ 顶栏 h-12：surface 底 + 底线                         │
│   左：手绘品牌名 + 项目下拉    右：设置按钮 + 头像K    │
├─────────┬────────────────────────────┬───────────┤
│ 侧栏     │ 主区                        │ 右栏       │
│ w-64    │  flex-1                     │ w-72      │
│ paper-  │  · 更新提示条 accent-soft    │ Git 面板   │
│ sink    │  · 当前项目条 surface        │ surface   │
│         │  · 执行计划条 surface        │           │
│ 项目列表 │  · 消息流 paper              │           │
│ 额度    │  · 输入区（input + 主按钮）   │           │
│ 信任开关 │                            │           │
│ 搜索    │                            │           │
│ 文件树  │                            │           │
│ 硬件链  │                            │           │
└─────────┴────────────────────────────┴───────────┘
```

- 分区全部由 1px `--line` 实线隔开，无任何阴影分层。
- 头像 `K`：7×7 方块，4px 圆角（不是圆形——圆形头像也可以，二选一，全端统一），`--accent` 实底白字。
- 登录/引导页：`paper` 底 + 居中 `panel` 卡（max-w-sm / max-w-md），卡内品牌名手绘体居中。

---

## 9. 参考实现（可直接复制的完整代码）

### 9.1 `index.css`（Tailwind 项目）

```css
@import url('https://fonts.googleapis.com/css2?family=Caveat:wght@500;600;700&family=Inter:wght@400;500;600;700&family=Long+Cang&family=Spline+Sans+Mono:wght@400;500&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    color-scheme: light;
    --paper: #f0eee6;  --paper-sink: #eae8dc;  --paper-edge: #e1ded2;  --surface: #faf9f2;
    --ink: #201b15;    --ink-soft: #4e4841;    --ink-faint: #6e6862;   --ink-ghost: #8a857e;
    --line: rgba(32, 27, 21, 0.14);
    --line-strong: rgba(32, 27, 21, 0.3);
    --accent: #1e40af; --accent-deep: #1e3a8a; --accent-soft: #dce5f7;
    --hl-green: #dce7c5; --hl-blue: #d9e4f7;
    --success: #3f7a44; --success-soft: #e0ead9;
    --warning: #b5641e; --warning-soft: #f2e5d0;
    --danger: #b44434;  --danger-soft: #f3deda;
    --radius: 4px;
    --radius-panel: 2px;
  }

  html {
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    margin: 0;
    background-color: var(--paper);
    color: var(--ink);
    line-height: 1.6;
  }

  button { font-family: inherit; }

  ::selection { background-color: var(--hl-blue); color: var(--ink); }

  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb { background: var(--paper-edge); border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--ink-ghost); }
  ::-webkit-scrollbar-track { background: transparent; }
}

@layer components {
  .font-hand {
    font-family: 'Caveat', 'Long Cang', 'PingFang SC', cursive;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  .font-mono {
    font-family: 'Spline Sans Mono', ui-monospace, 'SF Mono', Menlo, monospace;
  }

  .btn {
    @apply inline-flex items-center justify-center px-4 py-2 font-medium transition-colors duration-150 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed;
    border-radius: var(--radius);
    border: 1px solid transparent;
  }
  .btn-primary { @apply btn text-white; background-color: var(--accent); }
  .btn-primary:hover:not(:disabled) { background-color: var(--accent-deep); }
  .btn-secondary { @apply btn; background-color: var(--surface); border-color: var(--line-strong); color: var(--ink-soft); }
  .btn-secondary:hover:not(:disabled) { background-color: var(--paper-sink); color: var(--ink); }
  .btn-ghost { @apply btn; color: var(--ink-faint); }
  .btn-ghost:hover:not(:disabled) { background-color: var(--paper-sink); color: var(--ink); }
  .btn-danger { @apply btn text-white; background-color: var(--danger); }
  .btn-danger:hover:not(:disabled) { background-color: #96362a; }
  .btn-success { @apply btn text-white; background-color: var(--success); }
  .btn-success:hover:not(:disabled) { background-color: #356639; }

  .input {
    @apply w-full px-3 py-2 text-sm transition-colors focus:outline-none;
    background-color: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius);
    color: var(--ink);
  }
  .input::placeholder { color: var(--ink-ghost); }
  .input:focus { border-color: var(--accent); }
  .input:disabled { opacity: 0.5; }

  .label { @apply block text-sm font-medium mb-1; color: var(--ink-soft); }

  .panel {
    background-color: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-panel);
  }

  .hl-green { background-color: var(--hl-green); padding: 0 0.15em; }
  .hl-blue  { background-color: var(--hl-blue);  padding: 0 0.15em; }

  .wavy-green {
    text-decoration: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='4' viewBox='0 0 24 4'%3E%3Cpath d='M0 2 Q3 0.5 6 2 T12 2 T18 2 T24 2' fill='none' stroke='%233f7a44' stroke-width='1.6'/%3E%3C/svg%3E");
    background-repeat: repeat-x; background-position: 0 100%; padding-bottom: 3px;
  }
  .wavy-blue {
    text-decoration: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='4' viewBox='0 0 24 4'%3E%3Cpath d='M0 2 Q3 0.5 6 2 T12 2 T18 2 T24 2' fill='none' stroke='%231e40af' stroke-width='1.6'/%3E%3C/svg%3E");
    background-repeat: repeat-x; background-position: 0 100%; padding-bottom: 3px;
  }

  .text-success { color: var(--success); }
  .text-warning { color: var(--warning); }
  .text-danger  { color: var(--danger); }
}
```

### 9.2 `tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper:   { DEFAULT: '#f0eee6', sink: '#eae8dc', edge: '#e1ded2' },
        surface: '#faf9f2',
        ink:     { DEFAULT: '#201b15', soft: '#4e4841', faint: '#6e6862', ghost: '#8a857e' },
        accent:  { DEFAULT: '#1e40af', deep: '#1e3a8a', soft: '#dce5f7' },
        hl:      { green: '#dce7c5', blue: '#d9e4f7' },
        success: { DEFAULT: '#3f7a44', soft: '#e0ead9' },
        warning: { DEFAULT: '#b5641e', soft: '#f2e5d0' },
        danger:  { DEFAULT: '#b44434', soft: '#f3deda' },
      },
      borderColor: {
        line: 'rgba(32, 27, 21, 0.14)',
        'line-strong': 'rgba(32, 27, 21, 0.3)',
      },
      fontFamily: {
        hand: ['Caveat', 'Long Cang', 'PingFang SC', 'cursive'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['Spline Sans Mono', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      borderRadius: { sm: '2px', DEFAULT: '4px' },
      boxShadow: { none: 'none' },
    },
  },
  plugins: [],
};
```

### 9.3 非 Tailwind 技术栈

把 9.1 的 `:root` 变量与组件类原样搬入纯 CSS（把 `@apply` 展开即可）；组件类的视觉规格以第 7 章表格为准。

---

## 10. 落地步骤（给执行者的操作清单）

1. **装字体**：在全局 CSS 顶部加入 4.2 的 `@import`。
2. **注入 token**：把 3.7 的 `:root` 变量写入全局 CSS；Tailwind 项目同步替换 `tailwind.config.js`（9.2）。
3. **写组件类**：把 9.1 的 `@layer components` 全部写入（含 `.btn-*` / `.input` / `.panel` / `.font-hand` / 荧光笔与波浪线）。
4. **改基座**：`body` 背景 `--paper`、文字 `--ink`、行高 1.6；写入 `::selection` 与滚动条样式。
5. **逐组件替换**：按第 7 章规范替换所有按钮、输入框、卡片、列表、开关、徽章；列表选中态用 7.4 签名模式。
6. **品牌触点**：品牌名、页面标题、弹窗标题改 `.font-hand`；正文保持 Inter。
7. **清理旧风格**：删除旧色系的全部工具类（如 slate/blue/red/green 数字色阶）、所有 `shadow-*`、所有大于 4px 的容器圆角。
8. **验收**：执行第 11 章检查清单。

原则：**只改样式，不动逻辑**——所有事件处理、数据流、IPC/API 调用保持原样。

---

## 11. 验收清单

```bash
# 1. 渐变必须为零（源码与构建产物都查）
grep -rn "linear-gradient\|radial-gradient\|conic-gradient" src/ dist/
# 2. 无投影
grep -rn "box-shadow\|shadow-\(sm\|md\|lg\|xl\|2xl\)" src/ | grep -v "shadow: { none"
# 3. 无大圆角容器（允许 rounded-sm / rounded / 控件的 rounded-full）
grep -rn "rounded-\(lg\|xl\|2xl\|3xl\)" src/
# 4. 无暗色模式
grep -rn "prefers-color-scheme\|dark:" src/
# 5. 构建通过
npm run build   # 或对应技术栈的构建命令
```

全部无输出（或仅命中允许项）且构建通过，即为合格。

---

## 12. 常见错误（Antipatterns）

| ❌ 错误 | ✅ 正确 |
|---|---|
| 主按钮用渐变蓝 | `--accent` 实色，hover 用 `--accent-deep` 实色 |
| 卡片 `rounded-2xl` + `shadow-xl` | `rounded-sm`(2px) + 1px `--line` 边框，无阴影 |
| 选中项用蓝底白字反白 | `--accent-soft` 浅蓝底 + 左侧 2px 深蓝竖条 + 墨色字 |
| 用灰色 `#999` 做辅助文字 | 用墨色阶 `--ink-faint`（暖调灰） |
| 分隔用阴影或双层线 | 1px `var(--line)` 实线 |
| 正文大段用手绘体 | 手绘体只用于标题；正文 Inter |
| 荧光笔大面积涂背景 | 荧光笔只涂行内短语 |
| 新增「暗色模式」开关 | 本系统只有明亮暖色一套 |

---

*版本：v1.0（2026-07-28）· 首次在 desktop/ 完整落地 · 后续网页端（frontend/）实施时也必须遵循本文档。*
