# 安装与维护参考

这页供需要排查问题或维护代码的人查看。第一次使用请先读[首页](../README.md)。

## 环境与兼容性

| 项目 | 要求或当前状态 |
| --- | --- |
| Codex | 能使用本地 Skill、读写本地文件；正文读取及自动化能力取决于当前运行环境 |
| Python | 3.9 或以上 |
| 浏览器 | 现代桌面浏览器；分词能力较弱的浏览器使用有限回退 |
| macOS | 已做原生端到端自检 |
| Windows | 已适配文件锁、UTF-8、PowerShell 路径及启动方式；API 分支已模拟验证，尚未做原生实机验收 |
| Linux | 使用 POSIX 文件锁；尚未在本轮做原生实机验收 |
| 时区数据 | 使用 IANA 时区；缺失时安装随包声明的 `tzdata`，Windows 通常需要 |

Codex 会协助检查依赖。维护者可在 Skill 目录执行隔离自检：

```sh
# macOS / Linux
python3 scripts/self_test.py
python3 scripts/quality_test.py
python3 scripts/next_step_test.py
```

```powershell
# Windows
py -3 scripts/self_test.py
py -3 scripts/quality_test.py
py -3 scripts/next_step_test.py
```

缺少时区数据时，应在同一 Python 环境安装 `requirements.txt` 中的依赖。自检只使用临时模拟数据，不读取个人聊天。quality_test 验证批次审查覆盖、证据引用、合法空结果和候选变更阻断；它不验证摘要的语义准确性。常规发布通过当前 Skill 的 release.py，详见 [整理与发布检查](../references/quality-review.md)。

## 数据放在哪里

- **安装目录**：Skill 说明、脚本与空白模板，不保存你的工作台内容。
- **你选定的工作台目录**：已收录正文、整理结果、配置、批次记录与数据备份。
- **当前浏览器**：收藏、接续确认与移出选择。普通刷新和重启通常保留；清除本站数据会丢失，换浏览器或地址不会自动同步。

本地服务只监听 `127.0.0.1`，只开放网页需要的资源。不要把使用中的工作台目录公开上传；分享本仓库即可。工作台数据备份不包含浏览器收藏。

网页搜索不调用远程模型。整理过程由你的 Codex 环境处理原文，因此**不代表 AI 整理完全离线**；Skill 不额外把原文发给其他 AI 或第三方整理服务。

## 使用边界

- 收录的是当前环境可访问且你授权的内容，不承诺自动拿到全账号历史。
- 窗口目录、摘要和截断内容不能冒充完整原文。无可用正文时会停在空模板，说明缺口，再使用你授权的导出或本地来源。
- 当前不收录 ChatGPT 对话、附件正文与工具执行日志。
- 搜索是本地词语线索与有限容错，不是任意语义都能理解；未收录内容无法被搜索出来。
- 接续状态根据已收录讨论判断，可能不知道其他窗口或线下进展，所以提供本地修正入口。
- 定时更新需要当前 Codex 环境支持自动化，且相关运行环境可用；电脑关机或应用离线时不保证执行。

## 仓库结构

```text
SKILL.md                 Skill 入口
agents/openai.yaml       显示名称与调用提示
references/              首次使用、整理标准、数据契约、更新与定时流程
scripts/                 初始化、发布校验与隔离自检
assets/template/         不含个人记录的绿色网页模板
requirements.txt         时区数据依赖
```

遇到问题可在 [Issues](https://github.com/LuKK351/lukk-codex-workbench/issues) 描述操作系统、操作步骤和错误提示。提交前去掉私人对话、路径中的个人信息及凭据，不上传完整个人工作台。
