# 通用更新与恢复

## 找到已有工作台

读取 `config/workbench.json`（如存在）、`config/default-types.json`、`config/item-types.json` 和正式 `data.json`。没有初始化配置的旧工作台可以继续更新已有来源；补上时区、稳定 URL 和已知收录范围，不猜最初授权，不重新初始化。历史 `build_*.py` 只用于重放旧样本，不是实时更新入口。

脚本是工作台目录中的 `scripts/workbench.py`，需要 Python 3.9+ 与可用的 IANA 时区数据；Windows 使用 msvcrt 字节锁，macOS/Linux 使用 fcntl。优先使用 config/workbench.json 中的 pythonExecutable，否则检测本机解释器；将下方 python3 替换为该解释器。Windows 适配已实现，当前尚无 Windows 实机验证；自检入口见 first-use.md。脚本不调用模型或 Codex，不自动抓取对话；你负责读取、理解和构造有证据的批次。

## 1. 读取来源与保存进度

发现可用的 Codex `list_threads`、`read_thread` 或明确提供完整正文的工具。先从目录挑选候选，按消息/回合 ID 增量读取，分页到上次成功采集点；首次/新窗口到授权范围起点。目录更新时间不能当消息时间，也不能当全量覆盖证明。

检查每页是否截断。若 read_thread 只返回回合摘要，就只能作线索；不能把摘要写成用户原话。继续用可提供完整正文的接口或用户授权的导出、本地来源。对本地来源只读已选窗口所需文件，不扫描与任务无关的资料；不凭空假定本地日志覆盖云端窗口。

将当前读取结果与进度保存在工作台 `.workbench/runs/<唯一批次>/sources/`。保留真实消息 ID、角色、正文、日期。每个窗口单独登记读取状态和截止点，失败的窗口不推进游标。下次优先查看正式数据和已发布批次清单，不能仅凭某个未发布候选的日志跳过内容。

规范化结果使用数据契约中的 thread/messages 结构；没有真实 ID 的导出可在该导出固定文档内用稳定位置 ID，并明确来源为导出，不伪装成平台消息 ID。缺少窗口 UUID 的来源网页不会提供可点击的 Codex 跳转，不猜 UUID。

## 2. 整理成批次

读 curation.md。检索已有目标，更新对应事项。每个 upsert 是**完整记录**，已有节点与消息会按 ID 合并保留，但顶层摘要等字段以本批完整记录为准。只补历史时保持当前最新小结与 date，不将旧状态当最新。保留已有相关事项与分支。

`python3 scripts/workbench.py hash data.json` 得到 baseSha256，写入 batch.json；从读取这个基线开始整理。同批 `provenance` 记录每个已读/失败窗口及范围。`scopeDescription` 应准确描述累计实际覆盖，不宣称全量，不只写本次新增数。时间窗口固定在本次开始时刻。参照 data-contract.md。

缺失窗口不放虚构空消息；成功部分可以发布，但清楚说明部分完成，失败游标不推进。无新增且无整理修正时不用生成和发布空批次。首次历史范围外的补录需用户授权。

## 3. 候选、验证、发布

以下路径均相对于选定的工作台，命令参数按实际路径安全引用：

```sh
python3 scripts/workbench.py prepare . .workbench/runs/<批次>/batch.json .workbench/runs/<批次>/candidate
python3 scripts/workbench.py validate .workbench/runs/<批次>/candidate/data.json
python3 scripts/workbench.py publish . .workbench/runs/<批次>/candidate
```

prepare 不修改正式数据，会检查：唯一 ID、节点与原文/日期/角色一致、上下文、决定/任务/关联引用、有效分类、旧状态不能覆盖新状态。候选报告绑定基线、分类配置与候选文件哈希。publish 会加进程锁，检查基线是否变化，先备份再原子替换。

发布前核对报告：新增事项是否重复、原有 ID 是否保留、关键摘要和接续状态是否符合原文。需要修正候选时改 batch 并在**新的候选目录**重新 prepare，不手改候选文件绕过哈希。

发布成功将返回状态、备份位置及新哈希。保存返回结果为该运行目录 `published.json`，连同 candidate/report.json 用于继续。即使来不及写成功回执，也可比对正式文件与候选哈希确认是否已发布，不能盲目再执行。相同内容返回 unchanged，不制造额外备份。

## 4. 页面验收与完成

使用已保存的同一地址，刷新网页（不改端口、不清浏览器存储）。检查涉及的事项/来源、当天时间轴，挑一个关键词或记不清原话的搜索，确认可定位原文。初次还要检查空页到有内容的转换。不为了测试更改用户的真实收藏或移出选择。

报告实际更新量、覆盖终点、失败缺口，附本地地址。不要宣称脚本完成了语义判断，也不要承诺任何记忆偏差都能搜到。

## 恢复

- prepare/校验失败：正式数据不变；修正来源或批次，重建候选。已有消息正文改变会被拒绝，先查是否旧导出截断；不能仅为了通过而改原文。此版不自动纠正旧消息正文，需单独处理所有关联引用并审阅迁移。
- 基线变化：另一个批次已发布。重新读取正式数据并重新整理，不只改 baseSha256 强行覆盖。
- 磁盘满/写入失败：检查正式文件与备份，释放空间后重试；不能删除正式文件再写。
- 新数据发布后需回退：选择本工作台 `.workbench/backups/` 中确定的一份，先 validate，再 `python3 scripts/workbench.py rollback . <备份绝对路径>`。会先保留当前数据的备份，再恢复。回退数据不修改用户分类配置与浏览器存储；如配置曾变化，需一并核对兼容性。
- 中断：操作系统自动释放发布锁。不要以“有 update.lock 文件”为理由删除锁文件；文件存在不等于仍在写入。

Windows 如正式文件暂被其他进程占用，替换可能失败；现有数据保持，关闭占用后重新校验基线再重试，禁止先删正式文件。文件锁不依赖删除锁文件，进程退出后由操作系统释放。

实现依据：[Python msvcrt 锁文档](https://docs.python.org/3/library/msvcrt.html)、[zoneinfo 跨平台数据依赖](https://docs.python.org/3/library/zoneinfo.html)。
