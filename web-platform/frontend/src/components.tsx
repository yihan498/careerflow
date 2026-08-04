import { PropsWithChildren, ReactNode } from 'react'

export function Button({ children, variant = 'primary', ...props }: PropsWithChildren<React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }>) {
  return <button className={`button ${variant}`} {...props}>{children}</button>
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}

export function Notice({ children, tone = 'info' }: PropsWithChildren<{ tone?: 'info' | 'error' | 'success' }>) {
  return <div className={`notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>
}

export function Spinner({ text = '处理中…' }: { text?: string }) {
  return <span className="spinner"><i />{text}</span>
}

export const stageLabels: Record<string, string> = {
  onboarding: '资料初始化', created: '已新建', drafted: '待审批', approved: '已审批', built: '已构建',
  submitted: '已投递', interviewing: '面试准备', closed: '已结束',
}

export function StageBadge({ stage }: { stage: string }) {
  return <span className={`stage stage-${stage}`}>{stageLabels[stage] || stage}</span>
}
