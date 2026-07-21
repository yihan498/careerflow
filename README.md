# CareerFlow

一套由 Agent 驱动、从投递准备延伸到面试复盘的完整求职工作流。

```text
个人资料初始化
  -> 新建岗位
  -> 按 JD 修改简历 + Cover Letter
  -> 用户确认
  -> 生成投递文件
  -> 收到面试后调研公司并预判问题
  -> 面试结果与经验复盘
  -> 汇总成下一次可复用的改进清单
```

CareerFlow 的重点不是一次生成一份简历，而是把每个岗位作为一个独立分支持续追踪。公开仓库只包含程序、规范和虚构示例；真实姓名、简历、JD、申请记录和面试反馈默认保存在仓库之外。

## 你会得到什么

每个岗位都有自己的目录和进度，主要产物包括：

- 与 JD 对齐的简历草稿；
- Cover Letter；
- “每一项表述来自哪段真实经历”的证据映射；
- 经用户确认后生成的 Markdown、HTML 和 PDF；
- 收到面试后的公司、业务、岗位和流程调研；
- 结合最终简历生成的面试追问和回答框架；
- 该岗位的复盘记录；
- 跨岗位累计的个人问题与改进汇总。

## 使用前要准备什么

首次使用需要：

1. 一份完整原始简历；
2. 一份结构化个人资料，包含已确认的教育、经历、日期、行动、数据和结果；
3. 每次申请的完整 JD；
4. 如需 AI 深度改写和联网公司调研，需要使用者自己的 OpenAI API Key。

如果原始简历是 PDF 或 Word，Agent 应先提取内容、对照原文件检查，再让用户确认关键事实。示例结构见 [`examples/demo/profile.json`](examples/demo/profile.json)，完整说明见 [`docs/USER_ONBOARDING.md`](docs/USER_ONBOARDING.md)。

## 安装

需要 Python 3.8 或更高版本：

```bash
git clone <repository-url>
cd careerflow
python -m venv .venv
```

激活环境并安装：

```bash
# Windows
.venv\Scripts\activate
pip install -e ".[dev]"

# macOS / Linux
source .venv/bin/activate
pip install -e ".[dev]"
```

## 先运行虚构示例

```bash
python scripts/run_demo.py
pytest
python scripts/privacy_check.py
```

示例会走完“初始化—投递—审批—构建—面试—复盘”全过程，所有数据均为虚构，并写入系统临时目录。

## 第一次使用

真实数据不要放进克隆下来的代码仓库。先指定一个独立的私人工作区：

```powershell
$env:CAREERFLOW_HOME = "D:\private-careerflow"
careerflow bootstrap
careerflow user-add --profile D:\private-input\profile.json --resume D:\private-input\resume.md
```

个人资料只初始化一次。不同使用者必须使用不同的用户 ID 和目录，不能共享证据库。

## 阶段一：新建岗位并准备投递

```powershell
careerflow apply `
  --user candidate-id `
  --company "Example Company" `
  --role "Example Intern" `
  --jd D:\private-input\jd.md

careerflow draft `
  --application example-company-example-intern `
  --provider openai
```

系统会同时生成 `resume.md`、`cover-letter.md` 和 `evidence-map.md`。Agent 必须把三份草稿完整交给用户检查，不能自行推定用户同意。

用户明确同意后：

```powershell
careerflow approve `
  --application example-company-example-intern `
  --confirmed-by "user-confirmed"

careerflow build --application example-company-example-intern
```

审批会锁定草稿哈希。审批后如果内容被改动，系统会拒绝构建，必须重新确认。生成 PDF 后仍需人工检查字体、换行、重叠、缺字和分页。

## 阶段二：收到面试后继续准备

没有面试时，岗位可以停留在投递阶段。用户只需告诉 Agent“这个岗位可以准备面试了”，Agent 就能沿用该岗位已经保存的 JD、最终简历和证据库继续：

```powershell
careerflow interview `
  --application example-company-example-intern `
  --provider openai
```

联网模式会调研最新公司资料并记录来源；离线模式只生成待核实的调研框架，不会把未搜索的内容伪装成公司事实。

## 阶段三：复盘并积累经验

面试未成功、主动退出、尚未出结果或成功拿到 Offer，都可以复盘：

```powershell
careerflow review `
  --application example-company-example-intern `
  --outcome rejected `
  --notes D:\private-input\review.md

careerflow status
```

反馈会同时保存在岗位目录，并按公司/行业知识、简历追问、行为沟通、案例技术、临场表达和流程问题汇总到总复盘中。

## 如果你让 Agent 操作

直接告诉 Agent：

> 请先阅读本项目的 AGENTS.md 和 docs/AGENT_PLAYBOOK.md，再按照 CareerFlow 流程帮我处理这个岗位。不要把我的私人文件写入代码仓库。

Agent 的输入契约、允许动作、停止条件和完成标准都写在 [`AGENTS.md`](AGENTS.md) 与 [`docs/AGENT_PLAYBOOK.md`](docs/AGENT_PLAYBOOK.md)，不需要依赖作者的个人环境或历史对话。

## 两种生成模式

- `rules`：完全离线、可测试，只重排已确认事实并生成标准框架，适合验证流程。
- `openai`：根据 JD 做语义匹配；面试阶段可联网搜索公司信息。通过环境变量提供 `OPENAI_API_KEY`，请求设置 `store: false`。

## 关于 PDF

CareerFlow 从已批准的结构化内容生成新 PDF，不宣称能无损编辑所有任意 PDF——不同 PDF 没有统一的可编辑字段和排版协议。如果必须保留某个专有模板，可在私人工作区添加该用户的渲染适配器，其他证据、审批、面试和复盘流程不需要改变。

## 文档导航

- [`AGENTS.md`](AGENTS.md)：Agent 必须遵守的执行契约；
- [`docs/AGENT_PLAYBOOK.md`](docs/AGENT_PLAYBOOK.md)：Agent 分阶段操作手册；
- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md)：整体架构和数据边界；
- [`docs/USER_ONBOARDING.md`](docs/USER_ONBOARDING.md)：新使用者初始化；
- [`docs/QUALITY_STANDARD.md`](docs/QUALITY_STANDARD.md)：每一步的合格标准；
- [`PRIVACY.md`](PRIVACY.md)：隐私与云端模型边界。

## License

MIT
