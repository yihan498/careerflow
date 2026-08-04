import { Link } from 'react-router-dom'

const workflow = [
  { number: '01', title: '建立个人事实库', text: '上传 PDF 或 Word 简历，确认教育、经历、成果与技能。后续内容只使用你确认过的事实。' },
  { number: '02', title: '完成投递准备', text: '为每个岗位保存原始 JD，生成针对性简历、Cover Letter、证据映射和可审核的文档修改计划。' },
  { number: '03', title: '进入面试准备', text: '收到面试后继续调研公司与岗位，区分可靠事实、合理推断和暂时未知，并预判可能的问题。' },
  { number: '04', title: '记录结果与复盘', text: '保留实际问题、回答和感受，按岗位复盘，并同步沉淀到个人长期改进清单。' },
]

const features = [
  { label: '岗位隔离', title: '一份岗位，一条独立记录', text: 'JD、简历版本、审批、面试资料和复盘不会与其他岗位混用。' },
  { label: '原格式构建', title: '保留原有简历版式', text: '支持 PDF 与 DOCX，在批准修改计划后再构建新版本，并保留原文件。' },
  { label: '证据约束', title: '每个重要表述都有依据', text: '把简历事实映射到具体改写，无法支持的岗位要求会明确列为缺口。' },
  { label: '人工审批', title: '关键动作始终由你决定', text: 'Agent 只生成候选内容，不能替你审批、推进进度或发送求职邮件。' },
  { label: '面试调研', title: '从投递自然接到面试', text: '沿用已经确认的简历与 JD，不需要重新解释背景，再补充公司和岗位信息。' },
  { label: '经验沉淀', title: '把真实问题变成训练清单', text: '原始反馈不会被改写，系统只负责分类、汇总并提出后续训练动作。' },
]

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export default function Landing() {
  return <div className="landing">
    <header className="landing-header">
      <Link to="/" className="brand">CareerFlow</Link>
      <nav aria-label="主页导航">
        <button onClick={() => scrollTo('features')}>功能</button>
        <button onClick={() => scrollTo('workflow')}>流程</button>
        <button onClick={() => scrollTo('start')}>如何使用</button>
      </nav>
      <Link to="/auth" className="landing-login">登录 / 注册</Link>
    </header>

    <main>
      <section className="landing-hero">
        <div className="hero-copy">
          <p className="eyebrow">开源 · 自带 API Key · 关键步骤人工确认</p>
          <h1>把一次投递，变成一条可追踪的求职链路。</h1>
          <p className="hero-lead">CareerFlow 把简历修改、Cover Letter、邮件准备、面试调研和复盘串在一起。每个岗位独立保存，让 Agent 处理重复工作，让事实与决定仍然掌握在你手里。</p>
          <div className="hero-actions">
            <Link to="/auth" className="landing-primary">开始使用</Link>
            <button className="landing-secondary" onClick={() => scrollTo('workflow')}>查看完整流程</button>
          </div>
          <p className="hero-note">免费使用平台；模型调用费用由你自己的 API 服务商账户承担。</p>
        </div>
        <div className="flow-preview" aria-label="CareerFlow 岗位流程示意">
          <div className="preview-head"><span>示例岗位</span><span className="preview-status">面试准备中</span></div>
          <div className="preview-role"><small>某公司</small><strong>业务分析实习生</strong></div>
          <ol>
            <li className="done"><span>1</span><div><strong>投递材料</strong><small>简历与求职信已审批</small></div><b>完成</b></li>
            <li className="done"><span>2</span><div><strong>文档构建</strong><small>原格式版本已生成</small></div><b>完成</b></li>
            <li className="active"><span>3</span><div><strong>面试准备</strong><small>公司调研与问题预判</small></div><b>进行中</b></li>
            <li><span>4</span><div><strong>结果复盘</strong><small>等待面试反馈</small></div><b>待开始</b></li>
          </ol>
          <div className="preview-foot">每一步都有固定输入、校验与确认</div>
        </div>
      </section>

      <section className="landing-strip" aria-label="核心原则">
        <span>岗位之间完全隔离</span><span>原始文件始终保留</span><span>输出变化即重新审批</span><span>不会自动发送邮件</span>
      </section>

      <section className="landing-section" id="features">
        <div className="section-heading"><p className="eyebrow">核心功能</p><h2>不是一次性的内容生成器，而是完整的求职工作台。</h2><p>重复环节被流程化，需要判断的部分交给 Agent，但所有事实、版本和关键动作都有清晰边界。</p></div>
        <div className="feature-grid">
          {features.map(feature => <article className="feature-card" key={feature.title}><span>{feature.label}</span><h3>{feature.title}</h3><p>{feature.text}</p></article>)}
        </div>
      </section>

      <section className="landing-section workflow-section" id="workflow">
        <div className="section-heading"><p className="eyebrow">完整链路</p><h2>从第一次上传简历，到最后一次复盘。</h2><p>收到面试时不必重新开始，CareerFlow 会直接沿用这个岗位已经确认过的 JD、简历与证据。</p></div>
        <div className="workflow-list">
          {workflow.map(item => <article key={item.number}><span>{item.number}</span><div><h3>{item.title}</h3><p>{item.text}</p></div></article>)}
        </div>
      </section>

      <section className="landing-section start-section" id="start">
        <div className="start-card">
          <div><p className="eyebrow">如何开始</p><h2>准备一份简历和一个模型 API Key，就可以开始。</h2></div>
          <ol>
            <li><span>1</span><div><strong>创建账户</strong><p>完成邮箱验证，进入你的私有求职工作台。</p></div></li>
            <li><span>2</span><div><strong>配置模型</strong><p>选择服务商并填写自己的专用、低额度 API Key。</p></div></li>
            <li><span>3</span><div><strong>上传并确认</strong><p>上传 PDF 或 DOCX 简历，逐项确认事实，再建立第一个岗位。</p></div></li>
          </ol>
          <Link to="/auth" className="landing-primary">创建我的求职工作台</Link>
        </div>
        <aside className="boundary-card">
          <p className="eyebrow">使用边界</p>
          <h3>Agent 提建议，你做决定。</h3>
          <ul>
            <li>不会编造未经确认的经历</li>
            <li>不会直接覆盖原始简历</li>
            <li>不会代替你审批最终内容</li>
            <li>不会连接邮箱或自动投递</li>
          </ul>
          <p>简历与 JD 只会在你确认后发送给所选择的模型服务商。API Key 加密保存，且不会提供给文档处理服务。</p>
        </aside>
      </section>

      <section className="landing-cta">
        <p className="eyebrow">CareerFlow</p><h2>让每一次求职，都留下可以复用的经验。</h2><p>先把第一份岗位材料整理清楚，后面的面试与复盘自然接上。</p><Link to="/auth" className="landing-primary light">开始使用</Link>
      </section>
    </main>

    <footer className="landing-footer"><span>CareerFlow · 开源求职流程工具</span><a href="https://github.com/yihan498/careerflow" target="_blank" rel="noreferrer">查看 GitHub 项目</a></footer>
  </div>
}
