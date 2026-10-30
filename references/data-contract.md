# 批次数据契约 v1

使用 UTF-8 JSON。正式文件服务于现有绿色网页；只通过 prepare/publish 更新。下面的省略号表示结构说明，不能写进实际 JSON。字符串数组可以为空，字段不能省略成 undefined。生成后先运行 validate。

## 顶层批次

- `version`: 1。
- `baseSha256`: 整理前正式 data.json 的 SHA-256。
- `provenance`: 非空采集清单。每条写 threadId、method、requestedStart/End、observedStart/End、status（complete/partial/failed）、gap、cursor/来源文件；只按实际证据填写。
- `threads`, `items`, `tasks`: 本批新增或更新的完整记录数组，可省略无变化的集合。
- `retireTasks`: `[{"id":"稳定任务ID","reason":"明确完成或放弃的依据","node":"证据节点ID"}]`。保留原历史事项。不能同批又 upsert 同一任务。
- `dailySummaries`: `{"YYYY-MM-DD|事项ID":"当天变化"}`，仅对应日期确有节点才允许。
- `snapshot`: 兼容旧版的整理日期 YYYY-MM-DD，不能比原快照早。
- `organizedAt`: 含时区的 ISO 具体时间；prepare 在候选内容发生变化时自动记录，表示这一版整理内容生成的时间。无变化重试不刷新。界面按工作台时区显示到分钟。旧记录无此字段时显示“时间未记录”，不补造 00:00。
- `collectionCutoff`: 含时区的本轮读取上界，通常是本轮开始时刻；不是所有窗口均已收全的承诺，具体缺口仍在 scopeDescription/进度清单说明。不可晚于 organizedAt。补录旧范围时如没有新的读取上界，沿用既有值。
- 历史时间修复只能依据匹配当前数据哈希的发布记录等证据显式提供 organizedAt；不能用重启服务、网页刷新或文件修改时间冒充整理时间。
- `checked`: 用户可读的累计采集日期范围。
- `scopeDescription`: 累计实际收录范围、限制及部分失败说明，不应写成计划。

不支持删除线程/事项。用户明确要求删除敏感内容时作为单独迁移处理，不伪装成普通增量批次。

## thread

```json
{"id":"真实窗口ID","title":"原始窗口标题","date":"2026-10-28T09:00:00+08:00","checked":"2026-10-28","messages":[{"id":"真实稳定消息ID","role":"user","text":"原文","date":"2026-10-28T09:00:00+08:00","timePrecision":"轮次开始时间"}]}
```

role 只允许 user/assistant。date 是实际来源时间，不是采集时刻。thread.date 必须等于合并后已收录最新消息时间。同 ID 的已有消息必须一致，不静默改写。增量可只提供新增 messages，脚本合并旧记录。按日期升序传入。

## item

```json
{"id":"稳定事项ID","title":"对象与目标","description":"目标背景","status":"有证据的进展","summary":"两三句当前小结","recap":"取舍过程","openQuestion":"尚未明确的部分，没有则空字符串","nextUse":"有依据的回看用途，没有则空字符串","date":"2026-10-28T09:00:00+08:00","type":"coding-tools","terms":["搜索别名"],"related":[],"workBranches":[],"collection":"main","nodes":[],"decisions":[]}
```

实际事项至少应有一个有证据节点。date 必须等于合并后该事项最新相关节点时间；补历史不回退摘要。related 只引用已存在或同批新增的事项 ID。type 必须在用户配置内，用户 overrides 优先。nodes 按日期排序；脚本按 ID 保留历史节点，decisions 和 terms 追加去重。分支、关联等其他数组由完整 upsert 保留。

## node 与 decision

```json
{"id":"窗口ID:消息ID","ref":"窗口ID:消息ID","title":"本轮变化","event":"对变化的概括","branch":"讨论","quote":"对应消息的完整原文","quoteRole":"user","date":"2026-10-28T09:00:00+08:00","sourceTitle":"原始窗口标题","thread":"窗口ID","messageId":"消息ID","context":[],"timePrecision":"轮次开始时间"}
```

context 是同窗口前后文消息数组，字段与 messages 的 id/role/text/date 完全相同。原文不等于摘要；日期和角色必须一致。节点 ID 在同一事情内唯一。

decision：`{"text":"用户明确的决定或有标注的变化","label":"明确采用","node":"节点ID","date":"节点日期"}`。

## task

```json
{"id":"稳定目标ID","item":"事项ID","node":"证据节点ID","thread":"来源窗口ID","sourceTitle":"原始窗口标题","date":"节点日期","checked":"2026-10-28","title":"具体目标","stop":"目前停点","reason":"接续或待确认依据与范围","level":"状态待核实"}
```

level 只取“有明确接续”或“状态待核实”。网页会根据浏览器中用户的确认/移出选择改变显示，不从浏览器选择反推真实完成状态。

## 日期一致性检查

prepare、validate 和发布流程都会检查对话、事项与各自最新记录的日期关系，以及决定与所引证据节点的日期关系，比较实际时刻而非字符串顺序；等价时区写法可通过。错误会列出事项或对话 ID、当前日期与最新记录日期，并停止发布。新增讨论后更新所属记录的 date；补录旧讨论保留已有较晚 date。不要为了通过检查修改原文日期，也不要用同一窗口里无关消息的时间更新某个事项。旧版候选日期不一致时，修正完整批次后重新 prepare 和复核，不能只更新哈希或直接覆盖正式数据。
