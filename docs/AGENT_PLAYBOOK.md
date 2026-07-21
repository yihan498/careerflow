# Agent Playbook

本手册把一次求职任务拆成 Agent 可以稳定执行的阶段。命令示例中的路径和 ID 必须替换为当前使用者自己的值。

## 0. 启动检查

读取顺序：

1. `AGENTS.md`
2. `docs/QUALITY_STANDARD.md`
3. `docs/USER_ONBOARDING.md`（首次使用者）
4. 当前岗位的 `application.json`（已有岗位）

确认运行目录在代码仓库之外。若用户未指定，使用 `~/.careerflow`。不得扫描或引用其他求职项目、其他用户目录或历史私人案例。

## 1. 新用户初始化

### 输入

- 原始简历正文；
- 用户确认的结构化 profile JSON；
- 可选原始 `.md` / `.txt` 简历副本。

### 动作

1. 从简历提取候选事实。
2. 对照原文和版面核查教育、公司、职位、日期、数字和结果。
3. 将未确认信息标为缺口，不得补写。
4. 让用户确认结构化 profile。
5. 执行 `careerflow user-add`。

### 完成标志

- `profile/profile.json` 存在；
- `profile/evidence.json` 中每项均为 `user_confirmed`；
- 没有混入其他用户资料。

## 2. 新建岗位

### 输入

- 公司名称；
- 岗位名称；
- 完整 JD。

### 动作

执行 `careerflow apply`。检查新岗位 ID 和 `application.json`，确认状态为 `created`。

### 禁止

- 只有标题或截图摘要时伪装成完整 JD；
- 把两个岗位写入同一个 application；
- 覆盖已经存在的岗位目录。

## 3. 投递准备

### 动作

执行 `careerflow draft --provider openai`；没有模型时可用 `rules` 验证流程，但必须说明其内容深度有限。

同时核查：

- `resume.md` 是否覆盖 JD 的核心优先级；
- `cover-letter.md` 是否以真实项目和经历为主体；
- `evidence-map.md` 是否能追溯主要表述；
- 硬性要求中的未知项是否保持为未知。

### 强制暂停点

把三份文件完整交给用户。只有用户明确批准三者，才能执行：

```text
careerflow approve ...
careerflow build ...
```

不得从“继续”“差不多”“只认可简历”等表达推定三份材料均获批准。

### 构建后检查

检查 manifest 和全部输出；打开 PDF 渲染结果，确认无重叠、截断、缺字、旧文字残留和异常分页。

## 4. 面试准备

### 触发条件

用户明确表示获得面试、进入面试流程或要求开始准备。未触发时不要提前产生大规模公司调研。

### 动作

执行 `careerflow interview --provider openai`。调研应包含：

- 公司业务、产品/服务、客户和收入逻辑；
- 与岗位相关的实际业务流程；
- JD 拆解与可能的评价标准；
- 最终简历中每段经历的追问；
- 岗位题、行为题、案例/技术题；
- 回答方向、薄弱点和最后检查清单；
- 来源台账与调研日期。

### 证据规则

优先官方公司、监管机构、交易所和权威一手材料。实时或公司专属事实必须有链接。无法取得正文时只能说明信息边界，不得把标题或简介写成原文结论。

## 5. 复盘

### 输入

- 结果：`rejected`、`withdrew`、`offer` 或 `pending`；
- 用户的真实感受、被问问题、卡点和有效做法。

### 动作

1. 原样保留用户观察的核心含义；
2. 分类到知识、简历、行为、案例/技术、表达或流程；
3. 执行 `careerflow review`；
4. 检查岗位内 `review.json` 和总 `aggregate/review-summary.md`。

单次问题先记录，不立即包装成稳定规律。相同问题跨岗位重复出现后，再升级为个人面试清单。

## 6. 状态回答

用户询问“目前进行到哪里”时，运行 `careerflow status`，按岗位报告：

- 岗位 ID；
- 当前状态；
- 已完成产物；
- 下一步动作；
- 是否在等待用户确认或外部面试机会。

## 7. 公共仓库维护

修改代码后依次执行：

```bash
python scripts/run_demo.py
pytest
python scripts/privacy_check.py
```

发布前查看 Git 状态和 staged diff。任何私人信息命中都必须先删除或替换为虚构数据。
