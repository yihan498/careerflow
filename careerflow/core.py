from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


STAGES = ["created", "drafted", "approved", "built", "interviewing", "closed"]
REQUIRED_PROFILE = ["id", "display_name", "headline", "education", "experiences", "skills"]
REVIEW_CATEGORIES = {
    "knowledge": "公司、行业与岗位知识",
    "resume": "简历经历表达与追问",
    "behavior": "行为面试与沟通",
    "case": "案例、技术或业务题",
    "delivery": "节奏、结构与临场表现",
    "process": "投递与面试流程",
}


class CareerFlowError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    return value.strip("-") or "item"


def read_text(path: Path) -> str:
    if not path.exists():
        raise CareerFlowError("File not found: %s" % path)
    if path.suffix.lower() not in {".md", ".txt", ".json"}:
        raise CareerFlowError(
            "Use UTF-8 .md/.txt/.json input. Convert PDF/DOCX to structured profile JSON first; "
            "see docs/USER_ONBOARDING.md."
        )
    return path.read_text(encoding="utf-8-sig")


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise CareerFlowError("Invalid JSON in %s: %s" % (path, exc))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


class Workspace:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    @classmethod
    def from_value(cls, value: Optional[str]) -> "Workspace":
        configured = value or os.environ.get("CAREERFLOW_HOME")
        return cls(Path(configured) if configured else Path.home() / ".careerflow")

    def bootstrap(self) -> Path:
        for name in ("users", "aggregate"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        marker = self.root / "workspace.json"
        if not marker.exists():
            write_json(marker, {"schema_version": 1, "created_at": utc_now()})
        return self.root

    def user_dir(self, user_id: str) -> Path:
        return self.root / "users" / slugify(user_id)

    def add_user(self, profile_file: Path, resume_file: Optional[Path] = None) -> Path:
        self.bootstrap()
        profile = load_json(profile_file)
        missing = [key for key in REQUIRED_PROFILE if not profile.get(key)]
        if missing:
            raise CareerFlowError("Profile is missing required fields: %s" % ", ".join(missing))
        if not isinstance(profile["experiences"], list) or not profile["experiences"]:
            raise CareerFlowError("Profile must include at least one confirmed experience.")
        user_dir = self.user_dir(str(profile["id"]))
        if user_dir.exists():
            raise CareerFlowError("User already exists: %s" % profile["id"])
        (user_dir / "profile").mkdir(parents=True)
        (user_dir / "applications").mkdir()
        write_json(user_dir / "profile" / "profile.json", profile)
        evidence = self._build_evidence(profile)
        write_json(user_dir / "profile" / "evidence.json", evidence)
        if resume_file:
            read_text(resume_file)
            shutil.copy2(str(resume_file), str(user_dir / "profile" / ("source-resume" + resume_file.suffix.lower())))
        return user_dir

    @staticmethod
    def _build_evidence(profile: Dict[str, Any]) -> Dict[str, Any]:
        facts: List[Dict[str, Any]] = []
        for exp in profile.get("experiences", []):
            if not all(exp.get(key) for key in ("id", "organization", "role", "bullets")):
                raise CareerFlowError("Every experience needs id, organization, role and bullets.")
            for index, bullet in enumerate(exp["bullets"], 1):
                facts.append({
                    "evidence_id": "%s-%s" % (exp["id"], index),
                    "source": exp["id"],
                    "claim": str(bullet),
                    "status": "user_confirmed",
                })
        return {"generated_at": utc_now(), "facts": facts}

    def profile(self, user_id: str) -> Dict[str, Any]:
        return load_json(self.user_dir(user_id) / "profile" / "profile.json")

    def create_application(self, user_id: str, company: str, role: str, jd_file: Path) -> Path:
        self.bootstrap()
        self.profile(user_id)
        jd = read_text(jd_file).strip()
        if len(jd) < 80:
            raise CareerFlowError("JD is too short. Provide the complete posting, not only a title or summary.")
        base = "%s-%s" % (slugify(company), slugify(role))
        parent = self.user_dir(user_id) / "applications"
        app_id = base
        counter = 2
        while (parent / app_id).exists():
            app_id = "%s-%d" % (base, counter)
            counter += 1
        app_dir = parent / app_id
        for name in ("input", "draft", "output", "interview", "review"):
            (app_dir / name).mkdir(parents=True, exist_ok=True)
        (app_dir / "input" / "jd.md").write_text(jd + "\n", encoding="utf-8")
        write_json(app_dir / "application.json", {
            "schema_version": 1,
            "application_id": app_id,
            "user_id": slugify(user_id),
            "company": company,
            "role": role,
            "stage": "created",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "history": [{"stage": "created", "at": utc_now()}],
        })
        return app_dir

    def find_application(self, app_id: str) -> Path:
        matches = list((self.root / "users").glob("*/applications/%s" % app_id))
        if not matches:
            raise CareerFlowError("Application not found: %s" % app_id)
        if len(matches) > 1:
            raise CareerFlowError("Application ID is ambiguous; use a unique ID.")
        return matches[0]

    def meta(self, app_dir: Path) -> Dict[str, Any]:
        return load_json(app_dir / "application.json")

    def transition(self, app_dir: Path, target: str, allowed: Iterable[str]) -> None:
        meta = self.meta(app_dir)
        if meta["stage"] not in set(allowed):
            raise CareerFlowError("Cannot move from %s to %s." % (meta["stage"], target))
        meta["stage"] = target
        meta["updated_at"] = utc_now()
        meta.setdefault("history", []).append({"stage": target, "at": utc_now()})
        write_json(app_dir / "application.json", meta)

    def list_applications(self) -> List[Dict[str, Any]]:
        rows = []
        for path in (self.root / "users").glob("*/applications/*/application.json"):
            rows.append(load_json(path))
        return sorted(rows, key=lambda item: item.get("updated_at", ""), reverse=True)


def keyword_tokens(text: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}|[\u4e00-\u9fff]{2,6}", text.lower())
    stop = {"负责", "工作", "相关", "岗位", "要求", "能力", "具有", "以及", "进行", "实习", "优先"}
    counts: Dict[str, int] = {}
    for word in words:
        if word not in stop:
            counts[word] = counts.get(word, 0) + 1
    return [item[0] for item in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]]


def evidence_score(experience: Dict[str, Any], keywords: List[str]) -> int:
    text = json.dumps(experience, ensure_ascii=False).lower()
    return sum(1 for keyword in keywords if keyword in text)


def render_rule_drafts(profile: Dict[str, Any], meta: Dict[str, Any], jd: str) -> Dict[str, str]:
    keywords = keyword_tokens(jd)
    ranked = sorted(profile["experiences"], key=lambda exp: evidence_score(exp, keywords), reverse=True)
    lines = ["# %s" % profile["display_name"], "", profile["headline"], ""]
    lines += ["## Target", "", "%s - %s" % (meta["company"], meta["role"]), ""]
    lines += ["## Education", ""]
    for edu in profile["education"]:
        lines.append("- %s | %s | %s" % (edu.get("school", ""), edu.get("program", ""), edu.get("period", "")))
    lines += ["", "## Relevant Experience", ""]
    for exp in ranked:
        lines.append("### %s - %s" % (exp["organization"], exp["role"]))
        if exp.get("period"):
            lines.append(exp["period"])
        for bullet in exp["bullets"]:
            lines.append("- %s" % bullet)
        lines.append("")
    lines += ["## Skills", "", ", ".join(profile["skills"]), ""]
    resume = "\n".join(lines)

    strongest = ranked[:3]
    body = []
    for exp in strongest:
        body.append(
            "At %s, I worked as %s and %s. This evidence is relevant to the role's focus on %s."
            % (exp["organization"], exp["role"], str(exp["bullets"][0]).rstrip("."), ", ".join(keywords[:3]) or "core responsibilities")
        )
    cover = "# Cover Letter\n\nDear Hiring Team,\n\nI am applying for the %s role at %s.\n\n%s\n\nSincerely,\n%s\n" % (
        meta["role"], meta["company"], "\n\n".join(body), profile["display_name"]
    )
    mapping = ["# Evidence Map", "", "JD keywords: %s" % ", ".join(keywords), ""]
    for exp in strongest:
        mapping.append("- **%s / %s**: %s" % (exp["organization"], exp["role"], exp["bullets"][0]))
    mapping.append("\nAll claims above come from user-confirmed profile evidence. Rule mode reorders facts but does not invent new ones.\n")
    return {"resume.md": resume, "cover-letter.md": cover, "evidence-map.md": "\n".join(mapping)}


def openai_response(prompt: str, use_web: bool = False) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise CareerFlowError("OPENAI_API_KEY is required for the openai provider.")
    payload: Dict[str, Any] = {
        "model": os.environ.get("CAREERFLOW_MODEL", "gpt-5-mini"),
        "input": prompt,
        "store": False,
    }
    if use_web:
        payload["tools"] = [{"type": "web_search"}]
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CareerFlowError("OpenAI request failed (%s): %s" % (exc.code, detail[:500]))
    texts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
    if not texts:
        raise CareerFlowError("Model returned no text output.")
    return "\n".join(texts)


def draft_application(workspace: Workspace, app_id: str, provider: str) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] not in {"created", "drafted"}:
        raise CareerFlowError("Drafting is only allowed before approval.")
    profile = workspace.profile(meta["user_id"])
    jd = read_text(app_dir / "input" / "jd.md")
    if provider == "rules":
        drafts = render_rule_drafts(profile, meta, jd)
    elif provider == "openai":
        prompt = (Path(__file__).with_name("prompts") / "application.md").read_text(encoding="utf-8")
        prompt += "\n\nPROFILE JSON:\n" + json.dumps(profile, ensure_ascii=False)
        prompt += "\n\nJOB JSON:\n" + json.dumps(meta, ensure_ascii=False)
        prompt += "\n\nFULL JD:\n" + jd
        raw = openai_response(prompt)
        try:
            parsed = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            drafts = {
                "resume.md": parsed["resume_markdown"],
                "cover-letter.md": parsed["cover_letter_markdown"],
                "evidence-map.md": parsed["evidence_map_markdown"],
            }
        except (AttributeError, KeyError, json.JSONDecodeError) as exc:
            raise CareerFlowError("Model output did not match the required JSON contract: %s" % exc)
    else:
        raise CareerFlowError("Unknown provider: %s" % provider)
    for name, content in drafts.items():
        (app_dir / "draft" / name).write_text(content.strip() + "\n", encoding="utf-8")
    workspace.transition(app_dir, "drafted", {"created", "drafted"})
    return app_dir


def approve_application(workspace: Workspace, app_id: str, confirmed_by: str) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] != "drafted":
        raise CareerFlowError("Only a drafted application can be approved.")
    files = list((app_dir / "draft").glob("*.md"))
    if len(files) != 3:
        raise CareerFlowError("Resume, cover letter and evidence map are all required.")
    write_json(app_dir / "approval.json", {
        "confirmed_by": confirmed_by,
        "confirmed_at": utc_now(),
        "draft_sha256": sha256_files(files),
    })
    workspace.transition(app_dir, "approved", {"drafted"})
    return app_dir


def markdown_to_html(markdown: str, title: str) -> str:
    body: List[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append("<li>%s</li>" % html.escape(line[2:]))
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if line.startswith("### "):
            body.append("<h3>%s</h3>" % html.escape(line[4:]))
        elif line.startswith("## "):
            body.append("<h2>%s</h2>" % html.escape(line[3:]))
        elif line.startswith("# "):
            body.append("<h1>%s</h1>" % html.escape(line[2:]))
        elif line:
            body.append("<p>%s</p>" % html.escape(line))
    if in_list:
        body.append("</ul>")
    return """<!doctype html><html><head><meta charset="utf-8"><title>{0}</title>
<style>@page{{size:A4;margin:14mm}}body{{font-family:Arial,'Noto Sans CJK SC','Microsoft YaHei',sans-serif;color:#1f2937;line-height:1.42;max-width:780px;margin:auto}}h1{{font-size:25px;margin-bottom:4px}}h2{{font-size:16px;border-bottom:1px solid #94a3b8;padding-bottom:3px;margin-top:18px}}h3{{font-size:14px;margin-bottom:2px}}p,li{{font-size:11px;margin:3px 0}}ul{{margin:4px 0 8px;padding-left:20px}}</style></head><body>{1}</body></html>""".format(html.escape(title), "\n".join(body))


def build_application(workspace: Workspace, app_id: str, no_pdf: bool = False) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] != "approved":
        raise CareerFlowError("Build requires explicit approval.")
    approval = load_json(app_dir / "approval.json")
    files = list((app_dir / "draft").glob("*.md"))
    if approval["draft_sha256"] != sha256_files(files):
        raise CareerFlowError("Draft changed after approval. Draft and approve again.")
    output = app_dir / "output"
    for path in files:
        shutil.copy2(str(path), str(output / path.name))
    resume = read_text(app_dir / "draft" / "resume.md")
    html_text = markdown_to_html(resume, "%s - Resume" % meta["role"])
    (output / "resume.html").write_text(html_text, encoding="utf-8")
    pdf_status = "skipped"
    if not no_pdf:
        from .pdf_export import export_pdf
        export_pdf(resume, output / "resume.pdf")
        pdf_status = "created"
    write_json(output / "manifest.json", {
        "application_id": app_id,
        "built_at": utc_now(),
        "approved_draft_sha256": approval["draft_sha256"],
        "pdf": pdf_status,
        "files": sorted(path.name for path in output.iterdir()),
    })
    workspace.transition(app_dir, "built", {"approved"})
    return output


def prepare_interview(workspace: Workspace, app_id: str, provider: str) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] not in {"built", "interviewing"}:
        raise CareerFlowError("Interview preparation starts after the approved application package is built.")
    profile = workspace.profile(meta["user_id"])
    jd = read_text(app_dir / "input" / "jd.md")
    resume = read_text(app_dir / "draft" / "resume.md")
    if provider == "openai":
        prompt = (Path(__file__).with_name("prompts") / "interview.md").read_text(encoding="utf-8")
        prompt += "\n\nCOMPANY: %s\nROLE: %s\nJD:\n%s\n\nAPPROVED RESUME:\n%s\n\nCONFIRMED PROFILE:\n%s" % (
            meta["company"], meta["role"], jd, resume, json.dumps(profile, ensure_ascii=False)
        )
        brief = openai_response(prompt, use_web=True)
    elif provider == "rules":
        keywords = keyword_tokens(jd)
        questions = []
        for exp in profile["experiences"][:3]:
            questions.append("- What exactly did you own in %s, and what evidence supports the result?" % exp["organization"])
        brief = """# Interview Preparation: {company} - {role}

## Research boundary

Offline rule mode cannot verify current company facts. Complete the source ledger below or rerun with `--provider openai`. Missing sources must remain unknown, not negative evidence.

## Company source ledger

| Topic | Finding | Source URL | Published/updated | Confidence |
|---|---|---|---|---|
| Business model | TODO | TODO | TODO | unverified |
| Products and customers | TODO | TODO | TODO | unverified |
| Recent developments | TODO | TODO | TODO | unverified |
| Hiring team / process | TODO | TODO | TODO | unverified |

## Role interpretation

Priority JD terms: {keywords}

## Resume questions

{questions}

## Role questions

- Walk through how you would approach the role's most important deliverable.
- Which requirement is your strongest evidence match? Which is the largest gap?
- Describe a relevant decision, trade-off, or failure and what changed afterward.

## Answer worksheet

Use: context -> task -> action -> evidence -> result -> reflection. Do not memorize unsupported claims.
""".format(company=meta["company"], role=meta["role"], keywords=", ".join(keywords), questions="\n".join(questions))
    path = app_dir / "interview" / "interview-brief.md"
    path.write_text(brief.strip() + "\n", encoding="utf-8")
    workspace.transition(app_dir, "interviewing", {"built", "interviewing"})
    return path


def record_review(workspace: Workspace, app_id: str, outcome: str, notes_file: Path) -> Path:
    app_dir = workspace.find_application(app_id)
    meta = workspace.meta(app_dir)
    if meta["stage"] not in {"built", "interviewing", "closed"}:
        raise CareerFlowError("Review is only available after the application package was built.")
    notes = read_text(notes_file).strip()
    if not notes:
        raise CareerFlowError("Review notes cannot be empty.")
    category = "delivery"
    lowered = notes.lower()
    signals = {
        "knowledge": ["公司", "行业", "业务", "company", "industry"],
        "resume": ["简历", "经历", "项目", "resume", "experience"],
        "behavior": ["沟通", "行为", "冲突", "behavior", "communication"],
        "case": ["案例", "技术", "代码", "case", "technical"],
        "process": ["流程", "时间", "通知", "process", "schedule"],
    }
    best = 0
    for key, terms in signals.items():
        score = sum(1 for term in terms if term in lowered)
        if score > best:
            category, best = key, score
    review = {
        "application_id": app_id,
        "company": meta["company"],
        "role": meta["role"],
        "outcome": outcome,
        "category": category,
        "category_label": REVIEW_CATEGORIES[category],
        "notes": notes,
        "recorded_at": utc_now(),
    }
    path = app_dir / "review" / "review.json"
    write_json(path, review)
    aggregate_path = workspace.root / "aggregate" / "reviews.json"
    aggregate = load_json(aggregate_path) if aggregate_path.exists() else {"reviews": []}
    aggregate["reviews"] = [item for item in aggregate["reviews"] if item["application_id"] != app_id]
    aggregate["reviews"].append(review)
    write_json(aggregate_path, aggregate)
    lines = ["# Review Summary", ""]
    for key, label in REVIEW_CATEGORIES.items():
        items = [item for item in aggregate["reviews"] if item["category"] == key]
        lines += ["## %s" % label, ""]
        lines += ["- **%s / %s** (%s): %s" % (i["company"], i["role"], i["outcome"], i["notes"]) for i in items] or ["- No observations yet."]
        lines.append("")
    (workspace.root / "aggregate" / "review-summary.md").write_text("\n".join(lines), encoding="utf-8")
    if meta["stage"] != "closed":
        workspace.transition(app_dir, "closed", {"built", "interviewing"})
    return path
