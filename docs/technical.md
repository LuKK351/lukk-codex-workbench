# 安装与维护参考

这页供需要排查问题或维护代码的人查看。第一次使用请先读[首页](../README.md)。

## 环境与兼容性

| 项目 | 要求或当前状态 |
| --- | --- |
| Codex | 能使用本地 Skill、读写本地文件；正文读取及自动化能力取决于当前运行环境 |
| Python | 3.9 或以上 |
| 浏览器 | 现代桌面浏览器；分词能力较弱的浏览器使用有限回退 |
| macOS | 已做原生端到端自检 |
| Windows | Windows CI 已验证文件锁、发布、Unicode 快捷方式实际调用、登录入口创建与撤销；未做完整注销/重启验收 |
| Linux | Linux CI 已通过初始化、发布、文件锁、服务恢复等隔离测试；不提供桌面入口/登录启动安装器 |
| 时区数据 | 使用 IANA 时区；缺失时安装随包声明的 `tzdata`，Windows 通常需要 |

Codex 会协助检查依赖。维护者可在 Skill 目录执行隔离自检：

```sh
# macOS / Linux
python3 scripts/self_test.py
python3 scripts/quality_test.py
python3 scripts/date_consistency_test.py
python3 scripts/organization_time_test.py
python3 scripts/next_step_test.py
python3 scripts/launcher_test.py
```

```powershell
# Windows
py -3 scripts/self_test.py
py -3 scripts/quality_test.py
py -3 scripts/date_consistency_test.py
py -3 scripts/organization_time_test.py
py -3 scripts/next_step_test.py
py -3 scripts/launcher_test.py
```

缺少时区数据时，应在同一 Python 环境安装 `requirements.txt` 中的依赖。自检只使用临时模拟数据，不读取个人聊天。quality_test 验证批次审查覆盖、证据引用、合法空结果和候选变更阻断；它不验证摘要的语义准确性。date_consistency_test 验证事项/对话日期与各自最新记录一致、旧记录补录、时区等价和无关消息不改变事项日期，并检查错误候选不能发布且正式数据不变。常规发布通过当前 Skill 的 release.py，详见 [整理与发布检查](../references/quality-review.md)。

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

## 打开入口与登录启动

macOS 使用用户桌面 `.app` 与可选 `~/Library/LaunchAgents`；Windows 使用桌面 `.lnk` 与用户 Startup 文件夹，不安装系统级服务。桌面入口检查原工作台身份和固定 URL，再后台启动阅读服务；健康检查只返回工作台标识、目录哈希和进程号，不返回原路径或聊天内容。默认不启用登录启动。具体操作与撤销方式见 [打开与维护](../references/maintenance.md)。

`launcher_test.py` 验证父进程结束后仍可访问、重复/并发打开、退出后恢复、占用冲突、配置与浏览器失效、入口修复与撤销。Windows 主机上会实际创建并读取 `.lnk`、触发无浏览器启动；其他系统上跳过该实机分支，只验证 Windows 参数生成。`desktop_native_test.py` 在 macOS GUI 会话中真实调用 LaunchServices 和 launchd，使用临时工作台与模拟浏览器、自动清理；这不等于实际注销/重启验收。

GitHub Actions 对 macOS、Windows、Linux 运行隔离测试，[2026-10-30 三系统通过记录](https://github.com/LuKK351/lukk-codex-workbench/actions/runs/40989545973)。CI 的通过记录只覆盖相应测试，不代表所有用户桌面策略、系统登录项设置或整机重启场景均已验证。

系统接口依据：[Windows 快捷方式](https://learn.microsoft.com/en-us/windows/win32/shell/links)、[Windows 启动应用](https://support.microsoft.com/en-us/windows/experience/startup-boot/configure-startup-applications-in-windows)、macOS 本机 `man launchd.plist`（RunAtLoad、AbandonProcessGroup）。

最近整理显示 `organizedAt`（生成这一版整理内容的具体时间）；本轮读取截止显示 `collectionCutoff`。二者均按工作台时区展示，启动/刷新网页不会更新时间。旧版没有具体时间时明确显示未记录，不补造零点；实际覆盖及缺口仍以收录范围为准。


## 界面与动效

绿色界面使用 C 方向的连续线图形，页头仅显示「Codex 对话整理工作台」。图形随样式内嵌，不依赖外部图片服务。页面包含轻量入场、标签切换、卡片与按钮反馈；顶部线条仅在进入时播放一次，收藏等状态操作不会重复触发页面入场。遵循系统“减少动态效果”设置，页面转入后台时停止动画。

视觉升级仅替换 `index.html`、`style.css`、`app.js`；保留原有地址、`data.json`、配置和浏览器存储。README 图片来自同一界面，示例文字经过脱敏替换。
