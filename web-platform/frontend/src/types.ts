export type Stage = 'onboarding' | 'created' | 'drafted' | 'approved' | 'built' | 'submitted' | 'interviewing' | 'closed'

export interface Provider {
  id: string
  label: string
  default_base_url: string
  default_model: string
  capabilities: string[]
  requires_endpoint_id: boolean
}

export interface DraftBundle {
  resume_markdown: string
  cover_letter_markdown: string
  evidence_map_markdown: string
}

export interface Application {
  id: string
  company: string
  role: string
  jd: string
  stage: Stage
  history: { stage: Stage; at: string }[]
  draft_bundle?: DraftBundle
  document_plan?: any
  active_output_version?: string
}

export interface CandidateProfile {
  display_name: string
  headline: string
  education: { school: string; program: string; period: string; source_text: string }[]
  experiences: {
    id: string
    organization: string
    role: string
    period: string
    bullets: string[]
    source_text: string
  }[]
  skills: string[]
  uncertainties: string[]
}
