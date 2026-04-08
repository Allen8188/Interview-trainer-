from __future__ import annotations

import io
import random
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx


BACKEND_CORE_QUESTIONS = [
    "解释一次完整的HTTP请求流程，并说明后端可以在哪些点做性能优化。",
    "MySQL联合索引最左匹配原则是什么？给一个会失效的反例。",
    "Redis缓存击穿、穿透、雪崩的区别与常用治理方案。",
    "讲一下你理解的幂等性，以及在接口设计里如何保证幂等。",
    "如果服务QPS突增，你会如何做限流、熔断、降级和扩容？",
]

HR_QUESTIONS = [
    "请做一个90秒自我介绍，重点说明你为何从流体力学转向后端研发。",
    "你为什么选择字节跳动和企业隐私与效率方向？",
    "讲一次你与同伴意见冲突的经历，你如何推动结果落地？",
    "过去一年你做过最难但最有成长的一件事是什么？",
    "如果实习任务不确定性很高，你如何管理压力与优先级？",
]

SYSTEM_DESIGN_QUESTIONS = [
    "设计一个企业内部面试训练平台，要求支持多用户并发、历史记录和审计追踪。",
    "设计一个权限校验中台，供多个业务系统调用，如何保证低延迟和高可用？",
    "设计一个语音转写服务，如何处理高并发、失败重试和成本控制？",
    "设计一个多Agent任务调度系统，如何做任务编排、去重和失败补偿？",
    "设计一个题库推荐系统，如何根据用户弱项动态生成下一题？",
]

PRIVACY_SECURITY_QUESTIONS = [
    "企业隐私与效率场景下，RBAC和ABAC分别适合什么场景？",
    "如果要做内部数据访问审计，你会记录哪些关键字段？",
    "如何设计一个权限校验中台，做到低延迟又可追溯？",
    "敏感字段脱敏在存储层、传输层、展示层分别如何实现？",
    "如何防止内部系统出现越权访问和批量数据导出风险？",
]

AGENT_AI_QUESTIONS = [
    "请设计一个Agent任务执行框架，说明编排、工具调用、重试和观测如何落地。",
    "RAG系统在企业场景中如何处理召回质量、时效和权限隔离？",
    "如何评估一个Agent系统是否真正提升效率？请给核心指标。",
]

KEYWORD_TO_QUESTIONS = {
    "mpi": [
        "MPI是什么？它与多线程并行模型的核心区别是什么？",
        "你项目里MPI用了哪些通信原语？为什么这么选？",
    ],
    "openmp": [
        "OpenMP的并行for如何避免数据竞争？",
    ],
    "fortran": [
        "Fortran在数值计算里为什么常见？相比C++优缺点是什么？",
    ],
    "python": [
        "Python里GIL会影响什么场景？如何处理CPU密集任务？",
    ],
    "agent": [
        "多Agent系统如何避免循环调用和失控？",
        "如果Agent调用外部工具失败，如何设计重试与补偿？",
    ],
    "linux": [
        "线上Linux排障你最常用的三条命令是什么？",
    ],
    "navier": [
        "可压缩Navier-Stokes方程的数值稳定性约束通常怎么处理？",
    ],
    "碰撞": [
        "你提到O(N²)到O(N log N)优化，具体数据结构和边界条件是什么？",
    ],
}


@dataclass
class QAItem:
    question: str
    expected_keywords: list[str] = field(default_factory=list)
    category: str = "general"
    rubric_points: list[str] = field(default_factory=list)


def _truncate(text: str, n: int = 36) -> str:
    t = text.strip().replace("\n", " ")
    if len(t) <= n:
        return t
    return t[:n] + "..."


def extract_text_from_docx_bytes(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:p>", "\n")
    text = re.sub(r"<.*?>", "", xml)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("\u3000", " ")
    )
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def normalize_resume_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_keywords(resume_text: str) -> list[str]:
    lower = resume_text.lower()
    keys: list[str] = []
    for k in KEYWORD_TO_QUESTIONS:
        if k in lower or k in resume_text:
            keys.append(k)
    return keys


def suggest_session_label(
    company: str,
    role: str,
    mode: str,
    resume_text: str,
    custom_label: str = "",
) -> str:
    if custom_label and custom_label.strip():
        return custom_label.strip()[:60]

    parts = []
    if company.strip():
        parts.append(company.strip()[:12])
    if role.strip():
        parts.append(role.strip()[:16])
    if mode.strip():
        parts.append(mode.strip())

    kws = extract_keywords(resume_text)
    if kws:
        parts.append("+" + "+".join(kws[:2]))

    if not parts:
        return "面试练习会话"
    return " | ".join(parts)[:80]


def _build_expected_keywords(question: str, company: str, role: str) -> list[str]:
    q = question.lower()
    base = []
    if "权限" in question or "rbac" in q or "abac" in q:
        base.extend(["最小权限", "审计", "角色", "策略"])
    if "幂等" in question:
        base.extend(["唯一", "重试", "去重", "状态"])
    if "redis" in q:
        base.extend(["缓存", "穿透", "击穿", "雪崩"])
    if "mysql" in q:
        base.extend(["索引", "执行计划", "回表", "覆盖索引"])
    if "mpi" in q:
        base.extend(["通信", "同步", "并行", "性能"])
    if "agent" in q:
        base.extend(["编排", "工具", "重试", "观测"])
    if "系统" in question or "设计" in question:
        base.extend(["架构", "存储", "缓存", "限流", "高可用"])
    if "自我介绍" in question or "冲突" in question or "压力" in question:
        base.extend(["背景", "行动", "结果", "复盘"])
    if company:
        base.extend([w for w in re.split(r"[\s/,_，（）()]+", company) if len(w) >= 2][:2])
    if role:
        base.extend([w for w in re.split(r"[\s/,_，（）()]+", role) if len(w) >= 2][:3])
    return list(dict.fromkeys([x for x in base if x]))


def _build_rubric_points(question: str, category: str = "general") -> list[str]:
    q = (question or "").lower()
    points: list[str] = []
    if category in {"resume_deep_dive", "project", "external_domain"}:
        points.extend(["背景与目标", "个人职责边界", "技术方案与取舍", "量化结果", "复盘与改进"])
    if category in {"hr", "company_fit"}:
        points.extend(["动机真实", "与岗位匹配", "具体案例", "反思成长"])
    if "mpi" in q:
        points.extend(["进程模型vs线程模型", "通信原语与选择依据", "强缩放/弱缩放或加速比", "通信瓶颈定位"])
    if "openmp" in q:
        points.extend(["并发安全", "调度策略", "性能验证方法"])
    if "mysql" in q:
        points.extend(["索引原理", "失效场景", "执行计划验证"])
    if "redis" in q:
        points.extend(["击穿穿透雪崩区分", "治理方案", "降级兜底"])
    if "幂等" in question:
        points.extend(["幂等键设计", "去重或状态机", "重试语义"])
    if "rbac" in q or "abac" in q or "权限" in question:
        points.extend(["权限模型边界", "策略评估", "审计追踪"])
    if "system" in q or "设计" in question:
        points.extend(["容量与SLA", "核心链路", "高可用与故障预案", "观测指标"])
    if "agent" in q or "rag" in q:
        points.extend(["任务编排", "工具调用治理", "重试补偿", "评估指标"])
    if "你为什么选择" in question or "自我介绍" in question:
        points.extend(["行业动机", "公司理解", "可迁移能力", "落地计划"])
    return list(dict.fromkeys(points))


def _rubric_coverage(answer: str, rubric_points: list[str]) -> tuple[list[str], list[str], float]:
    ans = (answer or "").lower()
    if not rubric_points:
        return [], [], 0.0
    hits: list[str] = []
    miss: list[str] = []
    for p in rubric_points:
        tokens = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", p.lower()) if len(t) >= 2]
        if not tokens:
            miss.append(p)
            continue
        if any(t in ans for t in tokens):
            hits.append(p)
        else:
            miss.append(p)
    rate = round(len(hits) / max(1, len(rubric_points)), 2)
    return hits, miss, rate


def _build_company_fit_questions(company: str, role: str) -> list[str]:
    c = company.strip() or "目标公司"
    r = role.strip() or "目标岗位"
    return [
        f"你为什么选择 {c} 的 {r}？请从业务价值、个人能力匹配、未来一年目标三方面回答。",
        f"如果你加入 {c} 做 {r}，前90天你会优先做哪三件事？如何衡量自己达标？",
        f"你如何理解这个岗位所在行业的核心矛盾？在 {c} 的场景下你准备怎么解决？",
    ]


def _role_tags(role: str) -> set[str]:
    r = (role or "").lower()
    tags = set()
    if any(k in r for k in ["后端", "backend", "server", "platform"]):
        tags.add("backend")
    if any(k in r for k in ["隐私", "privacy", "security", "安全", "合规", "compliance"]):
        tags.add("privacy")
    if any(k in r for k in ["agent", "llm", "大模型", "ai", "智能体", "rag"]):
        tags.add("agent_ai")
    if any(k in r for k in ["hr", "人力", "人事", "招聘"]):
        tags.add("hr")
    return tags


def _has_pat(text: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


def _is_education_like_line(line: str) -> bool:
    s = line.strip()
    lower = s.lower()
    school_pats = [
        r"(大学|学院|研究所|研究院|school|university|college|institute)",
        r"(教育背景|学历|毕业|专业)",
    ]
    degree_pats = [r"(本科|硕士|博士|bachelor|master|phd|m\.?s\.?|b\.?s\.?)"]
    score_pats = [r"\bgpa\b", r"(排名|rank)\s*[:：]?\s*\d+"]
    date_pats = [r"20\d{2}[./-]?\d{0,2}\s*[-~至]\s*20\d{2}[./-]?\d{0,2}", r"\b20\d{2}\b"]

    school_hit = _has_pat(s, school_pats)
    degree_hit = _has_pat(lower, degree_pats)
    score_hit = _has_pat(lower, score_pats)
    date_hit = _has_pat(s, date_pats)
    # Typical education lines include at least two of these signals.
    return sum([school_hit, degree_hit, score_hit, date_hit]) >= 2


def _line_concepts(line: str) -> set[str]:
    s = line.strip()
    pats: dict[str, list[str]] = {
        "mpi": [r"mpi", r"消息传递", r"分布式并行", r"多进程并行"],
        "openmp": [r"openmp", r"共享内存并行", r"多线程并行"],
        "fortran": [r"fortran"],
        "python": [r"python", r"脚本", r"自动化"],
        "euler_lagrange": [r"欧拉[\-— ]?拉格朗日", r"euler[\- ]?lagrange"],
        "dem": [r"\bdem\b", r"离散元", r"颗粒碰撞", r"接触模型"],
        "ghost": [r"\bghost\b", r"ghost区域", r"幽灵单元", r"halo( exchange)?"],
        "load_balance": [r"动态负载均衡", r"load balancing", r"重分区", r"迁移开销"],
        "shock_supersonic": [r"激波", r"超音速", r"爆炸", r"supersonic", r"shock"],
        "eos": [r"\beos\b", r"状态方程", r"材料库"],
        "solver": [r"求解器", r"\bsolver\b", r"navier", r"n[\- ]?s方程", r"通量", r"重构"],
        "ai_coding": [r"claude\s*code", r"copilot", r"cursor", r"vibe\s*coding", r"ai编程", r"llm辅助编码"],
    }
    out = set()
    for k, ps in pats.items():
        if _has_pat(s, ps):
            out.add(k)
    return out


def _resume_lines(resume_text: str) -> list[str]:
    lines = []
    for raw in (resume_text or "").splitlines():
        line = raw.strip(" \t-:：•")
        if not line:
            continue
        if len(line) < 8:
            continue
        # skip headings and non-project profile lines
        if any(h in line for h in ["教育背景", "项目经历", "IT技能", "论文", "自我评价", "获奖"]):
            continue
        if _is_education_like_line(line):
            continue
        if re.fullmatch(r"[A-Za-z0-9@+().,\-_/ ]+", line) and " " not in line:
            continue
        lines.append(line)
    return lines


def _is_project_like_line(line: str) -> bool:
    if _is_education_like_line(line):
        return False
    keys = ["项目", "开发", "优化", "设计", "实现", "搭建", "并行", "模型", "系统", "算法", "提升", "验收", "负责", "落地"]
    if any(k in line for k in keys):
        return True
    if len(_line_concepts(line)) >= 2:
        return True
    if re.search(r"\b20\d{2}\b", line):
        return True
    if re.search(r"O\(.*\)", line):
        return True
    return False


def _is_skill_like_line(line: str) -> bool:
    keys = ["熟练掌握", "掌握", "熟悉", "精通", "了解", "技能", "工具", "语言", "框架"]
    return any(k in line for k in keys)


def _is_research_or_award_line(line: str) -> bool:
    keys = ["论文", "发表", "接收", "专利", "竞赛", "一等奖", "二等奖", "三等奖", "奖学金"]
    return any(k in line for k in keys)


def _line_keywords(line: str, company: str, role: str) -> list[str]:
    words = re.split(r"[^\w\u4e00-\u9fff]+", line)
    picked = [w for w in words if len(w) >= 2][:6]
    base = _build_expected_keywords(line, company, role)
    return list(dict.fromkeys(base + picked))


def _extract_line_terms(line: str, limit: int = 4) -> list[str]:
    text = line.strip()
    en = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+.#\-]{1,24}", text)]
    zh = re.findall(r"[\u4e00-\u9fff]{2,12}", text)
    stop = {
        "项目",
        "经历",
        "负责",
        "实现",
        "优化",
        "设计",
        "开发",
        "系统",
        "能力",
        "方向",
        "研究",
        "主要",
        "熟练掌握",
        "掌握",
        "熟悉",
    }
    out: list[str] = []
    for t in zh + en:
        if len(t) < 2 or t in stop:
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def _generic_line_question(line: str, kind: str = "project") -> str:
    short = _truncate(line, 42)
    terms = _extract_line_terms(line, limit=3)
    focus = " / ".join(terms) if terms else "关键技术点"
    if kind == "skill":
        return (
            f"你在简历里写到“{short}”。请围绕“{focus}”选一个最近真实场景，说明："
            "你具体做了什么、为什么这样做、结果如何量化、遇到的问题如何修复。"
        )
    if kind == "research":
        return (
            f"你在简历里写到“{short}”。请围绕“{focus}”说明："
            "你的原创贡献是什么、证据是什么、有哪些边界条件、还能怎么改进。"
        )
    return (
        f"你在简历里写到“{short}”。请围绕“{focus}”展开："
        "关键决策、替代方案取舍、验证方法、量化结果与复盘。"
    )


def _skill_line_special_question(line: str) -> str:
    concepts = _line_concepts(line)
    if "mpi" in concepts:
        return "你写了MPI并行计算。请回答：1) MPI进程模型与线程模型本质差异；2) 你在项目里具体用了哪些通信原语（如Allreduce/Isend/Irecv）及原因；3) 你如何定位并行瓶颈并量化加速比。"
    if "openmp" in concepts:
        return "你写了OpenMP。请结合一个循环并行场景说明：线程安全怎么保证、schedule策略怎么选、以及你如何验证并行收益不是伪加速。"
    if "fortran" in concepts:
        return "你写了Fortran。请讲一个你实际维护过的Fortran数值模块：数据布局、性能瓶颈、与Python/C++交互方式，以及你做过的一个性能优化。"
    if "python" in concepts:
        return "你写了Python。请讲你如何用Python做科研/工程自动化：任务编排、性能热点定位、以及CPU密集部分如何绕开GIL限制。"
    if "euler_lagrange" in concepts:
        return "你写了欧拉-拉格朗日耦合。请说明：耦合项如何离散、时间推进如何同步、数值稳定性怎么控制，以及你如何验证耦合精度。"
    if "dem" in concepts:
        return "你写了DEM离散元。请详细讲接触模型选型（软球/硬球）、时间步长约束、邻域搜索复杂度优化，以及误差与稳定性的取舍。"
    if "ghost" in concepts:
        return "你写了Ghost区域通信。请讲清数据交换时序、边界一致性保证、通信与计算重叠策略，以及一次你遇到的数据错位排障经历。"
    if "load_balance" in concepts:
        return "你写了动态负载均衡。请说明负载指标定义、迁移触发阈值、迁移成本控制，以及优化前后的并行效率变化。"
    if re.search(r"vibe\s*coding", line, flags=re.IGNORECASE):
        return "你写了Vibe Coding。请明确它在你项目中的定义、使用边界、质量保障机制（测试/回归/代码评审），并给一个成功和一个失败案例。"
    return ""


def _project_line_special_question(line: str) -> str:
    s = line.strip()
    concepts = _line_concepts(line)
    if "ai_coding" in concepts and "mpi" in concepts:
        return "你写了用AI编程工具加速MPI并行开发。请讲：1) 你把AI用于哪一段（代码生成/重构/测试/调优）；2) 你如何验证生成代码在并行语义上正确（死锁、竞态、一致性）；3) 最终对开发效率和性能分别提升了多少。"
    if "mpi" in concepts:
        return "你这条涉及MPI并行。请具体回答：并行划分策略、核心通信原语选择、性能瓶颈定位方法，以及至少一组可复现的加速比数据。"
    if "shock_supersonic" in concepts and "dem" in concepts:
        return "你这条是爆炸-超音速-颗粒耦合场景。请讲：1) 控制方程和耦合项如何组织；2) 激波捕捉和时间推进怎么做稳定性控制；3) 你如何设计算例验证尺度律/相图结论的可信度。"
    if "euler_lagrange" in concepts:
        return "你项目里用了欧拉-拉格朗日框架。请具体说明：气相与颗粒相的信息交换变量、耦合频率、以及在高颗粒浓度下如何避免数值振荡。"
    if "dem" in concepts:
        return "你项目有DEM/碰撞模型。请讲清：邻域搜索数据结构、接触力模型、时间步长约束，以及你如何把复杂度和精度做工程取舍。"
    if "ghost" in concepts:
        return "你写了Ghost区域通信。请画出一次迭代中的通信时序：边界打包、异步发送、重叠计算、同步收敛；再讲一个你遇到的错位或死锁问题如何定位。"
    if "load_balance" in concepts:
        return "你做了动态负载均衡。请说明：负载度量指标、触发重分区条件、迁移开销评估，以及优化前后并行效率和尾延迟变化。"
    if "mpi" in concepts and _has_pat(s, [r"亿级网格", r"大规模", r"分布式", r"强缩放", r"弱缩放"]):
        return "你提到MPI分布式和亿级网格。请给一个实际并行配置（进程数/网格规模），并说明强缩放或弱缩放曲线、通信占比、以及你的瓶颈优化路径。"
    if "eos" in concepts:
        return "你提到材料库与EOS。请讲：不同EOS适用工况、参数标定来源、以及EOS不确定性对结果的敏感性分析。"
    if "solver" in concepts:
        return "你提到自主求解器。请拆解一轮时间步：重构、通量计算、源项耦合、边界处理、收敛判据；并说说你做过哪一层性能优化最有效。"
    return ""


def build_resume_deep_dive_questions(resume_text: str, company: str, role: str, limit: int = 8) -> list[QAItem]:
    lines = _resume_lines(resume_text)
    project_lines = [ln for ln in lines if _is_project_like_line(ln)]
    skill_lines = [ln for ln in lines if _is_skill_like_line(ln)]
    research_lines = [ln for ln in lines if _is_research_or_award_line(ln)]
    selected = project_lines[:limit] if project_lines else lines[: min(4, limit)]

    # Mix in non-project lines so the interview feels more human, but keep project deep dive first.
    tail_pool = [ln for ln in (skill_lines + research_lines) if ln not in selected]
    selected.extend(tail_pool[: max(0, limit - len(selected))])

    items: list[QAItem] = []
    for line in selected:
        short = _truncate(line, 42)
        if _is_skill_like_line(line):
            special = _skill_line_special_question(line)
            if special:
                q = special
            else:
                q = _generic_line_question(line, kind="skill")
        elif _is_research_or_award_line(line):
            q = _generic_line_question(line, kind="research")
        else:
            special = _project_line_special_question(line)
            if special:
                q = special
            else:
                q = _generic_line_question(line, kind="project")
        items.append(
            QAItem(
                question=q,
                expected_keywords=_line_keywords(line, company, role),
                category="resume_deep_dive",
                rubric_points=_build_rubric_points(q, "resume_deep_dive"),
            )
        )
    return items


def build_question_bank(resume_text: str, company: str, role: str, mode: str = "mixed") -> list[QAItem]:
    resume_bank: list[QAItem] = []
    role_bank: list[QAItem] = []
    bank: list[QAItem] = []

    normalized_mode = (mode or "mixed").strip().lower()
    enable_backend = normalized_mode in {"backend", "mixed"}
    enable_hr = normalized_mode in {"hr", "mixed"}
    enable_sys = normalized_mode in {"system_design", "mixed"}

    if enable_backend:
        for q in BACKEND_CORE_QUESTIONS:
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="backend",
                    rubric_points=_build_rubric_points(q, "backend"),
                )
            )

    tags = _role_tags(role)
    if normalized_mode != "hr" and "privacy" in tags:
        for q in PRIVACY_SECURITY_QUESTIONS:
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="privacy",
                    rubric_points=_build_rubric_points(q, "privacy"),
                )
            )

    if normalized_mode != "hr" and "agent_ai" in tags:
        for q in AGENT_AI_QUESTIONS:
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="agent_ai",
                    rubric_points=_build_rubric_points(q, "agent_ai"),
                )
            )

    if enable_hr:
        for q in HR_QUESTIONS:
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="hr",
                    rubric_points=_build_rubric_points(q, "hr"),
                )
            )

    if enable_backend or enable_sys:
        resume_bank.extend(build_resume_deep_dive_questions(resume_text, company, role, limit=8))

    if enable_backend:
        for key in extract_keywords(resume_text):
            for q in KEYWORD_TO_QUESTIONS.get(key, []):
                resume_bank.append(
                    QAItem(
                        question=q,
                        expected_keywords=_build_expected_keywords(q, company, role) + [key],
                        category="resume_deep_dive",
                        rubric_points=_build_rubric_points(q, "resume_deep_dive"),
                    )
                )

    if enable_sys:
        for q in SYSTEM_DESIGN_QUESTIONS:
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="system_design",
                    rubric_points=_build_rubric_points(q, "system_design"),
                )
            )

    if normalized_mode == "mixed":
        for q in _build_company_fit_questions(company, role):
            role_bank.append(
                QAItem(
                    question=q,
                    expected_keywords=_build_expected_keywords(q, company, role),
                    category="company_fit",
                    rubric_points=_build_rubric_points(q, "company_fit"),
                )
            )

    # Interview flow: resume deep dive first, then role/domain questions.
    bank.extend(resume_bank)
    bank.extend(role_bank)

    seen = set()
    deduped = []
    for item in bank:
        if item.question in seen:
            continue
        seen.add(item.question)
        deduped.append(item)
    return deduped


def _dimension_scores(question: QAItem, answer: str, matched: list[str]) -> dict[str, int]:
    answer_len = len(answer)
    structure_cues = 0
    for cue in ["首先", "其次", "最后", "第一", "第二", "第三", "1", "2", "3"]:
        if cue in answer:
            structure_cues += 1
    numbers = 1 if re.search(r"\d+", answer) else 0

    technical = min(10, len(matched) * 2 + numbers + (2 if question.category in {"backend", "system_design", "privacy", "agent_ai"} else 0))
    structure = min(10, (3 if answer_len >= 80 else 1) + min(structure_cues, 4))
    communication = min(10, (4 if answer_len >= 60 else 2) + (2 if "因为" in answer or "所以" in answer else 0))
    job_fit = min(10, len([k for k in matched if k]) * 2 + (2 if question.category in {"hr", "privacy"} else 1))
    return {
        "technical": technical,
        "structure": structure,
        "communication": communication,
        "job_fit": job_fit,
    }


def score_answer(question: QAItem, answer: str, pressure_level: str = "standard") -> dict[str, Any]:
    answer = answer.strip()
    pressure = (pressure_level or "standard").strip().lower()
    if not answer:
        empty_follow = "请先用1分钟定义这个概念，再结合你的项目举一个具体例子。"
        if pressure == "high":
            empty_follow = "你这题没有有效回答。现在给你30秒，按定义-方案-结果重答。"
        return {
            "score": 0,
            "level": "weak",
            "dimensions": {"technical": 0, "structure": 0, "communication": 0, "job_fit": 0},
            "matched_keywords": [],
            "feedback": "回答为空。建议先给定义，再给项目中的具体做法和结果数据。",
            "follow_up": empty_follow,
            "rubric_points": question.rubric_points or _build_rubric_points(question.question, question.category),
            "rubric_hits": [],
            "rubric_missing": question.rubric_points or _build_rubric_points(question.question, question.category),
            "rubric_hit_rate": 0.0,
        }

    if len(answer) <= 6:
        rubric_points = question.rubric_points or _build_rubric_points(question.question, question.category)
        return {
            "score": 0.8,
            "level": "weak",
            "dimensions": {"technical": 0, "structure": 1, "communication": 1, "job_fit": 1},
            "matched_keywords": [],
            "feedback": "回答过短，信息不足，无法评估真实能力。",
            "follow_up": "请直接作答，不要只给编号或单个词；至少覆盖定义/方案/结果。",
            "rubric_points": rubric_points,
            "rubric_hits": [],
            "rubric_missing": rubric_points,
            "rubric_hit_rate": 0.0,
        }

    matched = [k for k in question.expected_keywords if k and k in answer]
    rubric_points = question.rubric_points or _build_rubric_points(question.question, question.category)
    rubric_hits, rubric_missing, rubric_rate = _rubric_coverage(answer, rubric_points)
    dims = _dimension_scores(question, answer, matched)
    rubric_bonus = rubric_rate * 3.0
    score = round(
        min(
            10.0,
            dims["technical"] * 0.40
            + dims["structure"] * 0.25
            + dims["communication"] * 0.20
            + dims["job_fit"] * 0.15
            + rubric_bonus
            + min(1.2, len(matched) * 0.2)
        ),
        1,
    )

    if score >= 8:
        level = "strong"
        feedback = "回答结构和细节较好。下一步可以补充风险与边界条件，体现工程深度。"
        follow_up = "如果线上故障发生在高峰期，你会先看哪些监控并如何止损？请给3步动作。"
    elif score >= 5:
        level = "medium"
        feedback = "回答有主干，但量化结果或取舍理由不足。"
        follow_up = "请补充一组优化前后数据，并说明为何不选另一种方案。"
    else:
        level = "weak"
        feedback = "回答偏概念化，缺少可落地的工程方案。"
        follow_up = "请按“问题-方案-结果-复盘”四段式重答，至少包含1个失败或坑点。"

    if rubric_missing:
        focus = "、".join(rubric_missing[:3])
        if level == "strong":
            follow_up = f"加一道进阶：请补充你未展开的要点（{focus}），并说明取舍。"
        elif level == "medium":
            follow_up = f"请针对缺失要点补充：{focus}。每点给一句可验证证据。"
        else:
            follow_up = f"当前与题目不对齐。请围绕这题缺失要点重答：{focus}。"

    if pressure == "gentle":
        feedback = "方向是对的，继续把细节讲实一些会更好。 " + feedback
        follow_up = "我们放慢一点：" + follow_up
    elif pressure == "high":
        if level == "strong":
            follow_up = "回答不错，但还不够。请补充一个你做错过的决策及修正过程。"
        elif level == "medium":
            feedback = "回答可用但竞争力一般，缺少关键深度。"
            follow_up = "高压追问：给出可落地方案、关键指标、故障兜底，控制在90秒内。"
        else:
            feedback = "回答不达标，缺少可执行方案和技术取舍。"
            follow_up = "高压追问：现在按“问题-方案-指标-风险”重答，不要泛泛而谈。"

    return {
        "score": score,
        "level": level,
        "dimensions": dims,
        "matched_keywords": matched,
        "feedback": feedback,
        "follow_up": follow_up,
        "rubric_points": rubric_points,
        "rubric_hits": rubric_hits,
        "rubric_missing": rubric_missing,
        "rubric_hit_rate": rubric_rate,
    }


def ideal_answer_template(question: str) -> str:
    points = _build_rubric_points(question, "general")
    point_line = "；".join(points[:6]) if points else "定义、场景、方案、结果、复盘"
    return (
        "推荐答题结构：1) 先定义概念与目标；2) 讲你的实际场景；"
        "3) 给出设计/实现细节；4) 用量化结果收尾；5) 补充风险与优化计划。"
        f"\n本题标准要点：{point_line}。"
        f"\n针对本题可补充：{question} 的核心取舍、边界条件与故障兜底策略。"
    )


def build_interviewer_reply(
    question: QAItem,
    answer: str,
    evaluation: dict[str, Any],
    pressure_level: str = "standard",
    interviewer_style: str = "professional",
    turn_index: int = 0,
) -> str:
    pressure = (pressure_level or "standard").lower()
    style = (interviewer_style or "professional").lower()
    level = evaluation.get("level", "medium")
    dims = evaluation.get("dimensions", {})
    quote = _truncate(answer, 34) if answer.strip() else "（你刚才没有有效作答）"

    warm_openers = [
        "我先接住你这段回答。",
        "这段我听到了，先给你即时反馈。",
        "好，这题我们继续往深处走。",
    ]
    pro_openers = [
        "收到，我基于你的回答继续追问。",
        "这题我先给结论，再做追问。",
        "我记录下你的关键点了，继续。",
    ]
    hard_openers = [
        "我直接说问题。",
        "这题还没过线，我们加压。",
        "时间不多，我给你高压追问。",
    ]

    if pressure == "high":
        opener_pool = hard_openers
    elif style == "friendly":
        opener_pool = warm_openers
    else:
        opener_pool = pro_openers

    opener = opener_pool[turn_index % len(opener_pool)]
    tech = dims.get("technical", 0)
    struct = dims.get("structure", 0)

    if level == "strong":
        core = (
            f"你刚才提到“{quote}”，方向是对的。"
            f"技术点有竞争力（技术{tech}/10），但我还想看你的边界思维。"
        )
    elif level == "medium":
        core = (
            f"你说到“{quote}”，主线在，但深度还不够。"
            f"结构性一般（结构{struct}/10），需要更像线上方案。"
        )
    else:
        core = (
            f"你目前回答是“{quote}”，这还偏概念。"
            "如果是真实面试，这里会被连续追问。"
        )

    follow = evaluation.get("follow_up", "")
    if pressure == "high":
        closer = "我只给你90秒，请直接给可执行方案。"
    elif pressure == "gentle":
        closer = "不用急，我们按结构把这题答完整。"
    else:
        closer = "你可以按定义-方案-指标-风险来组织。"

    return f"{opener} {core} 追问：{follow} {closer}"


def detect_interruption(
    question: QAItem,
    answer: str,
    evaluation: dict[str, Any],
    pressure_level: str = "standard",
) -> dict[str, Any]:
    pressure = (pressure_level or "standard").lower()
    ans = (answer or "").strip()
    dims = evaluation.get("dimensions", {})
    score = float(evaluation.get("score", 0))

    reasons = []
    if len(ans) < 24:
        reasons.append("回答过短")
    if score < 5:
        reasons.append("有效信息不足")
    if dims.get("technical", 0) <= 3 and question.category in {"backend", "privacy", "system_design", "agent_ai"}:
        reasons.append("技术细节不足")
    if not re.search(r"\d+", ans):
        reasons.append("缺少量化指标")
    if any(w in ans for w in ["大概", "差不多", "可能", "应该", "我觉得就"]):
        reasons.append("表达不够确定")

    if pressure == "gentle":
        threshold = 3
    elif pressure == "high":
        threshold = 1
    else:
        threshold = 2

    interrupted = len(reasons) >= threshold
    if not interrupted:
        return {"interrupted": False, "message": "", "reasons": []}

    reason_text = "、".join(reasons[:3])
    if pressure == "high":
        msg = f"我先打断一下：你这段存在{reason_text}。请立刻给“方案+指标+风险”。"
    elif pressure == "gentle":
        msg = f"我先轻轻打断一下：目前有{reason_text}，我们一起补全。"
    else:
        msg = f"先打断到这里：你这段有{reason_text}，请给更可执行的回答。"
    return {"interrupted": True, "message": msg, "reasons": reasons}


def _role_alias(role: str) -> str:
    role_alias = role
    replacements = {
        "后端": "backend",
        "实习": "intern",
        "研发": "engineer",
        "隐私": "privacy",
        "效率": "productivity",
        "安全": "security",
        "智能体": "agent",
        "大模型": "llm",
    }
    for zh, en in replacements.items():
        role_alias = role_alias.replace(zh, en)
    return role_alias


def _resume_search_tokens(resume_text: str, limit: int = 8) -> list[str]:
    tokens = []
    # high-signal known keywords
    tokens.extend(extract_keywords(resume_text))
    # generic token extraction
    words = [w.lower() for w in re.split(r"[^\w\u4e00-\u9fff]+", resume_text) if len(w) >= 3]
    stop = {"project", "experience", "intern", "research", "负责", "实现", "优化", "开发", "系统"}
    for w in words:
        if w in stop:
            continue
        if w not in tokens:
            tokens.append(w)
        if len(tokens) >= limit:
            break
    return tokens[:limit]


def _auto_extract_profile_terms(company: str, role: str, resume_text: str, limit: int = 14) -> list[str]:
    text_company = company or ""
    text_role = role or ""
    text_resume = resume_text or ""

    # weighted text by repetition
    weighted_text = (text_company + " ") * 3 + (text_role + " ") * 3 + text_resume

    # candidate extraction: english technical tokens + chinese phrases
    english_tokens = re.findall(r"[A-Za-z][A-Za-z0-9+.#\-]{1,30}", weighted_text)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,16}", weighted_text)

    stop = {
        "项目",
        "经历",
        "负责",
        "实现",
        "优化",
        "开发",
        "研究",
        "主要",
        "方向",
        "岗位",
        "公司",
        "熟悉",
        "掌握",
        "能力",
        "结果",
        "背景",
        "问题",
        "方案",
        "目标",
        "教育背景",
    }

    freq: dict[str, int] = {}
    for tok in english_tokens:
        t = tok.strip().lower()
        if len(t) < 2:
            continue
        freq[t] = freq.get(t, 0) + 1
    for ck in chinese_chunks:
        c = ck.strip()
        if c in stop or len(c) < 2:
            continue
        freq[c] = freq.get(c, 0) + 1

    # boost explicit company and role fragments
    for t in re.split(r"[^\w\u4e00-\u9fff]+", text_company):
        if len(t) >= 2:
            freq[t.lower()] = freq.get(t.lower(), 0) + 4
    for t in re.split(r"[^\w\u4e00-\u9fff]+", text_role):
        if len(t) >= 2:
            freq[t.lower()] = freq.get(t.lower(), 0) + 3

    ranked = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
    terms = [k for k, _ in ranked[:limit]]
    return terms


def _query_candidates(company: str, role: str, resume_text: str = "") -> list[str]:
    role_alias = _role_alias(role)
    terms = _auto_extract_profile_terms(company, role_alias, resume_text, limit=12)
    eng_terms = [t for t in terms if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+.#\-]{1,20}", t)]
    zh_terms = [t for t in terms if re.search(r"[\u4e00-\u9fff]", t)]
    eng_head = " ".join(eng_terms[:3])
    eng_tail = " ".join(eng_terms[3:6])
    zh_head = " ".join(zh_terms[:3])
    profile_text = f"{role_alias} {' '.join(terms)}".lower()
    backend_markers = ["backend", "java", "spring", "node", "golang", "redis", "mysql", "api", "微服务", "后端"]
    backendish = any(m in profile_text for m in backend_markers)

    qs = [
        f"{eng_head} simulation solver",
        f"{eng_head} {eng_tail} cfd",
        f"{role_alias} {eng_head}",
        f"{zh_head} 仿真",
    ]
    if backendish:
        qs.extend(
            [
                f"{company} {role} 面试题",
                f"{role_alias} interview questions",
                f"{role_alias} 技术面 题目",
            ]
        )
    else:
        qs.extend(
            [
                f"{company} {role} 技术问题",
                f"{role_alias} project simulation",
            ]
        )
    normalized = [re.sub(r"\s+", " ", q).strip() for q in qs if q.strip()]
    return [q for q in normalized if len(q) >= 8]


def _repo_relevance(
    full_name: str,
    desc: str,
    readme_text: str,
    profile_terms: list[str],
) -> int:
    text = f"{full_name}\n{desc}\n{readme_text}".lower()
    term_hits = sum(1 for t in profile_terms if t and t in text)
    head_hits = sum(1 for t in profile_terms[:4] if t and t in text)
    interview_hits = sum(1 for t in ["interview", "面经", "question", "questions", "技术面"] if t in text)
    score = head_hits * 8 + term_hits * 3 + interview_hits
    if head_hits == 0:
        score -= 5
    backend_bias_terms = ["backend", "node", "express", "spring", "java", "golang", "microservice"]
    profile_has_backend = any(t in {"backend", "node", "express", "spring", "java", "golang"} for t in profile_terms)
    if not profile_has_backend and any(t in text for t in backend_bias_terms):
        score -= 10
    return score


async def _fetch_ranked_repos(company: str, role: str, resume_text: str = "", limit: int = 12) -> list[dict[str, Any]]:
    queries = _query_candidates(company, role, resume_text=resume_text)
    profile_terms = _auto_extract_profile_terms(company, role, resume_text, limit=14)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "interview-trainer"}
    search_url = "https://api.github.com/search/repositories"

    async with httpx.AsyncClient(timeout=12.0) as client:
        candidates: list[dict[str, Any]] = []
        seen_repo = set()
        for query in queries[:3]:
            resp = await client.get(
                search_url,
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 8},
                headers=headers,
            )
            if resp.status_code == 403:
                break
            if resp.status_code != 200:
                continue
            for item in resp.json().get("items", []):
                full_name = item.get("full_name", "")
                if not full_name or full_name in seen_repo:
                    continue
                seen_repo.add(full_name)
                candidates.append(item)
            if len(candidates) >= 24:
                break

        ranked: list[dict[str, Any]] = []
        for repo in candidates:
            full_name = repo.get("full_name", "")
            desc = repo.get("description") or ""
            readme_text = ""

            relevance = _repo_relevance(
                full_name, desc, readme_text, profile_terms
            )
            ranked.append(
                {
                    "full_name": full_name,
                    "html_url": repo.get("html_url", ""),
                    "description": desc,
                    "readme_text": readme_text,
                    "relevance": relevance,
                }
            )

        ranked.sort(key=lambda x: x["relevance"], reverse=True)
        return ranked[: max(limit, 1)]


async def fetch_github_materials(company: str, role: str, resume_text: str = "", limit: int = 5) -> list[dict[str, str]]:
    ranked = await _fetch_ranked_repos(company, role, resume_text=resume_text, limit=max(10, limit))
    if not ranked:
        return []

    results: list[dict[str, str]] = []
    for repo in ranked[:limit]:
        snippet = (repo.get("description") or "").strip()[:180]
        lines = [ln.strip() for ln in (repo.get("readme_text") or "").splitlines() if ln.strip()]
        readme_snippet = " ".join(lines[:3])[:240]
        results.append(
            {
                "title": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "summary": (snippet + " " + readme_snippet).strip()[:280],
                "source": "github",
            }
        )
    return results


def _clean_text_for_extract(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _extract_ddg_results(html: str, limit: int = 10) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen = set()
    for m in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_url, raw_title = m.group(1), m.group(2)
        title = _clean_text_for_extract(raw_title)
        url = raw_url
        if "duckduckgo.com/l/?" in raw_url:
            qs = parse_qs(urlparse(raw_url).query)
            uddg = qs.get("uddg", [""])[0]
            if uddg:
                url = unquote(uddg)
        if not title or not url or url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url})
        if len(out) >= limit:
            break
    return out


def _extract_question_like_lines(markdown_text: str, limit: int = 20) -> list[str]:
    lines = [ln.strip(" -*#>\t") for ln in markdown_text.splitlines()]
    out: list[str] = []
    seen = set()
    for ln in lines:
        if not ln or len(ln) < 12 or len(ln) > 140:
            continue
        if ln in seen:
            continue
        lower = ln.lower()
        if any(x in lower for x in ["license", "contributing", "readme", "目录", "安装"]):
            continue
        is_q = ("?" in ln) or ("？" in ln) or lower.startswith("q:") or lower.startswith("question")
        interview_like = any(
            k in lower
            for k in [
                "mysql",
                "redis",
                "http",
                "tcp",
                "索引",
                "幂等",
                "缓存",
                "并发",
                "线程",
                "系统设计",
                "backend",
                "database",
                "api",
                "distributed",
            ]
        )
        if not (is_q or interview_like):
            continue
        seen.add(ln)
        out.append(ln)
        if len(out) >= limit:
            break
    return out


async def fetch_external_interview_questions(company: str, role: str, resume_text: str = "", limit: int = 8) -> list[str]:
    ranked = await _fetch_ranked_repos(company, role, resume_text=resume_text, limit=10)
    out: list[str] = []
    for repo in ranked:
        seed = f"{repo.get('full_name', '')}\n{repo.get('description', '')}\n{repo.get('readme_text', '')}"
        candidates = _extract_question_like_lines(seed, limit=10)
        for c in candidates:
            if c not in out:
                out.append(c)
            if len(out) >= limit:
                return out[:limit]
    # fallback and enrichment from web posts
    web_qs = await fetch_web_interview_questions(company, role, resume_text=resume_text, limit=limit)
    for q in web_qs:
        if q not in out:
            out.append(q)
        if len(out) >= limit:
            break
    return out[:limit]


async def fetch_web_interview_materials(company: str, role: str, resume_text: str = "", limit: int = 6) -> list[dict[str, str]]:
    role_alias = _role_alias(role)
    profile_terms = _auto_extract_profile_terms(company, role, resume_text, limit=10)
    short_terms = []
    for t in profile_terms:
        if len(t) > 12:
            continue
        if t.lower() in {x.lower() for x in short_terms}:
            continue
        short_terms.append(t)
        if len(short_terms) >= 2:
            break
    query_terms = " ".join(short_terms)
    query = f"{company} {role} {query_terms} 面试".strip()
    query = re.sub(r"\s+", " ", query)
    headers = {"User-Agent": "interview-trainer/1.0"}
    out: list[dict[str, str]] = []
    seen = set()
    core_terms = [t.lower() for t in re.split(r"[^\w\u4e00-\u9fff]+", f"{company} {role_alias}") if len(t) >= 2]
    for t in profile_terms[:4]:
        tt = t.lower()
        if tt not in core_terms:
            core_terms.append(tt)

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        # DuckDuckGo HTML results (multi-site web search fallback)
        try:
            ddg = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query + " 面经 OR interview experience"},
                headers=headers,
            )
            if ddg.status_code == 200:
                parsed = _extract_ddg_results(ddg.text, limit=10)
                for item in parsed:
                    title = item["title"]
                    url = item["url"]
                    blob = f"{title} {url}".lower()
                    if core_terms and not any(t in blob for t in core_terms):
                        continue
                    if not title or not url or url in seen:
                        continue
                    seen.add(url)
                    out.append(
                        {
                            "title": f"web: {title}",
                            "url": url,
                            "summary": "External interview post/article from web search",
                            "source": "web",
                        }
                    )
                    if len(out) >= limit:
                        return out[:limit]
        except Exception:
            pass

        # Reddit search posts (JSON API)
        try:
            r = await client.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "sort": "relevance", "limit": 10},
                headers=headers,
            )
            if r.status_code == 200:
                children = r.json().get("data", {}).get("children", [])
                for ch in children:
                    d = ch.get("data", {})
                    title = d.get("title", "").strip()
                    permalink = d.get("permalink", "")
                    if not title or not permalink:
                        continue
                    url = "https://www.reddit.com" + permalink
                    summary = _clean_text_for_extract(d.get("selftext", ""))[:220]
                    blob = f"{title} {summary}".lower()
                    if core_terms and not any(t in blob for t in core_terms):
                        continue
                    if url in seen:
                        continue
                    seen.add(url)
                    out.append(
                        {
                            "title": f"reddit/{d.get('subreddit', 'unknown')}: {title}",
                            "url": url,
                            "summary": summary or "Reddit interview discussion thread",
                            "source": "reddit",
                        }
                    )
                    if len(out) >= limit:
                        return out[:limit]
        except Exception:
            pass

        # dev.to articles
        try:
            d = await client.get(
                "https://dev.to/api/articles",
                params={"per_page": 10, "tag": "interview"},
                headers=headers,
            )
            if d.status_code == 200:
                for art in d.json():
                    title = art.get("title", "").strip()
                    url = art.get("url", "")
                    desc = art.get("description", "") or ""
                    blob = f"{title} {desc}".lower()
                    role_tokens = [t.lower() for t in re.split(r"[^\w\u4e00-\u9fff]+", role_alias) if len(t) >= 3]
                    if role_tokens and not any(t in blob for t in role_tokens[:4]):
                        continue
                    if core_terms and not any(t in blob for t in core_terms):
                        continue
                    if not title or not url or url in seen:
                        continue
                    seen.add(url)
                    out.append(
                        {
                            "title": f"dev.to: {title}",
                            "url": url,
                            "summary": _clean_text_for_extract(desc)[:220],
                            "source": "dev.to",
                        }
                    )
                    if len(out) >= limit:
                        return out[:limit]
        except Exception:
            pass

    return out[:limit]


async def fetch_web_interview_questions(company: str, role: str, resume_text: str = "", limit: int = 6) -> list[str]:
    mats = await fetch_web_interview_materials(company, role, resume_text=resume_text, limit=max(limit, 6))
    out: list[str] = []
    for m in mats:
        lines = _extract_question_like_lines(f"{m.get('title', '')}\n{m.get('summary', '')}", limit=3)
        for ln in lines:
            if ln not in out:
                out.append(ln)
            if len(out) >= limit:
                return out[:limit]
    return out[:limit]


def build_profile_seed_materials(company: str, role: str, resume_text: str = "", limit: int = 5) -> list[dict[str, str]]:
    terms = _auto_extract_profile_terms(company, role, resume_text, limit=max(limit + 2, 8))
    out: list[dict[str, str]] = []
    seen = set()
    for t in terms:
        if len(t) < 2:
            continue
        q = f"{company} {role} {t} 面试 经验"
        url = f"https://duckduckgo.com/?q={quote_plus(q)}"
        if url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "title": f"profile-seed: {t} 相关面试检索",
                "url": url,
                "summary": f"自动根据简历/岗位画像生成的检索入口：{q}",
                "source": "profile_seed",
            }
        )
        if len(out) >= limit:
            break
    return out
