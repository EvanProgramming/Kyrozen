# Kyrozen 文档索引

## 产品方案

- `Kyrozen 项目方案.pdf`：产品目标、用户流程、功能范围和长期愿景。
- `Kyrozen Development Plan.pdf`：分阶段开发目标、交付物和验收方向。
- `KYROZEN_MISSING_FEATURES_THREE_PHASE_PLAN.md`：当前缺失功能的三阶段优先级实施计划。
- `DESIGN_SYSTEM.md`：桌面端与 Web 端统一视觉和交互规范。

## 架构与部署

- `DESKTOP_CLIENT_ARCHITECTURE.md`：桌面客户端架构。
- `PHASE10_BETA_ARCHITECTURE_DESIGN.md`：Beta 产品化架构设计。
- `DEPLOYMENT.md`：本地与生产部署指南。
- `SELFHOSTED_DEPLOYMENT.md`：自托管部署指南。
- `PRODUCTION_SERVER.md`：当前生产服务器信息和操作约束。
- `CLOUDFLARE_TUNNEL.md`：停用的旧网络方案，仅作历史记录。

## 审计、测试与历史交付

- `Kyrozen_Full_Architecture_Audit_Report.md`：完整架构审计。
- `Kyrozen_Full_System_Audit_Report.md`：完整系统审计。
- `DESKTOP_CLIENT_KNOWN_GAPS.md`：桌面客户端历史缺口。
- `DESKTOP_FINAL_TEST_REPORT.md`：桌面客户端历史最终测试报告。
- `TEST_PLAN.md`：测试计划。
- `TEST_REPORT.md`：测试结果和缺陷记录。
- `PHASE1_` 至 `PHASE10_` 开头的文件：阶段计划、集成分析和交付报告。这些文件用于历史追溯，不代表当前版本已经通过真实用户验收。

## 存放规则

- 产品方案、架构说明、部署指南、审计报告、测试报告和阶段计划统一写入本目录。
- 仓库根目录只保留 `README.md` 作为项目入口，保留 `AGENTS.md` 作为仓库级贡献规则。
- 文档引用使用相对路径，禁止写入个人电脑的绝对 `file://` 路径。
