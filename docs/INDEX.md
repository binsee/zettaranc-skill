# docs/INDEX — 文档入口

v4.3+ 起，所有文档以本文件为导航入口。

## 快速路径

| 我想知道… | 去看 |
|---|---|
| 怎么用 CLI / 安装依赖 / 第一次运行 | [README.md](../README.md) → [USER_GUIDE.md](USER_GUIDE.md) |
| 怎么配置环境变量、数据源 key、回测参数 | [CONFIG_GUIDE.md](CONFIG_GUIDE.md) |
| 想参与开发 / 提 PR / 写新指标 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 哪个版本改了什么 / 迁移要点 | [CHANGELOG.md](CHANGELOG.md) |
| 历史 superpowers 工作流（Darwin / 模拟器 / Rust 重构） | [_archive/superpowers-2026q2q3/](_archive/superpowers-2026q2q3/) |
| 技能入口（角色协议）| [../SKILL.md](../SKILL.md) |
| 知识库（zettaranc 体系）| [../knowledge/](../knowledge/) |
| 语料调研 / 原始 reference | [../references/](../references/) |

## 文档清单

- `USER_GUIDE.md` — 用户手册（CLI、子命令、--json 输出、典型工作流）
- `CONFIG_GUIDE.md` — 环境变量、`.env`、数据源切换、缓存策略
- `CONTRIBUTING.md` — 提交流程、测试、lint、发布 checklist
- `CHANGELOG.md` — 全量变更历史（append-only）
- `IMPROVEMENT_SYSTEM_SUMMARY.md` — 自我改进系统设计摘要
- `STATISTICS_VALIDATION.md` — 回测统计显著性检验（夏普 t-test / permutation / sub-period）
- `intent-router-design.md` — 意图路由（实验性）
- `_archive/README.md` — 历史归档索引
- `_archive/superpowers-2026q2q3/` — 2026 Q2-Q3 工作流产物

## 维护规则

- 改 `pyproject.toml` 的 `version` → 同步改 `skill.json` / `SKILL.md` / `README.md` badge
- 新增 CLI 子命令 → 更新 `USER_GUIDE.md` 对应章节
- 改模块边界 → 更新 `INDEX.md` 与 `_archive/README.md`（如归档）
- 不再维护的文档 → 移至 `_archive/`，保留 git 历史可回溯