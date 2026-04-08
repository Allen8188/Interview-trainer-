from app.engine import QAItem, build_question_bank, extract_keywords, score_answer


def test_extract_keywords_detects_resume_terms():
    text = "熟练掌握 Fortran，Python，MPI并行计算，熟悉 Linux 和多Agent"
    keys = extract_keywords(text)
    assert "mpi" in keys
    assert "python" in keys
    assert "linux" in keys
    assert "agent" in keys


def test_build_question_bank_for_bytedance_role_contains_privacy_questions():
    text = "我做过MPI并行和Agent系统"
    bank = build_question_bank(text, "字节跳动", "后端研发实习生（企业隐私与效率）", mode="mixed")
    questions = [q.question for q in bank]
    assert any("RBAC" in q for q in questions)
    assert any("MPI是什么" in q for q in questions)


def test_score_answer_rewards_keywords_and_detail():
    item = QAItem(question="幂等性", expected_keywords=["唯一", "重试", "去重"])
    ans = "通过唯一请求ID和去重表来保证重试幂等，线上QPS 1200时错误率下降20%。"
    res = score_answer(item, ans)
    assert res["score"] >= 5
    assert res["level"] in {"medium", "strong"}
    assert "dimensions" in res
    assert res["dimensions"]["technical"] >= 1


def test_mode_switch_hr_only():
    text = "熟练掌握Python"
    bank = build_question_bank(text, "字节跳动", "后端研发实习生（企业隐私与效率）", mode="hr")
    cats = {q.category for q in bank}
    assert cats == {"hr"}


def test_generalization_non_bytedance_role_still_works():
    text = "I worked on distributed systems, Python and MPI"
    bank = build_question_bank(text, "Acme Corp", "Backend Intern - Privacy Security", mode="mixed")
    cats = {q.category for q in bank}
    assert "backend" in cats
    assert "privacy" in cats


def test_resume_questions_are_prioritized_in_mixed_mode():
    text = """项目经历
2025 高速气固求解器开发：负责MPI并行优化与性能提升
实现 O(N^2) 到 O(N log N) 的碰撞检测优化
"""
    bank = build_question_bank(text, "Acme", "Backend Intern", mode="mixed")
    assert bank
    assert bank[0].category == "resume_deep_dive"


def test_skill_line_uses_skill_style_question():
    text = "熟练掌握 Fortran，Python，MPI并行计算"
    bank = build_question_bank(text, "Acme", "Backend Intern", mode="mixed")
    resume_qs = [q.question for q in bank if q.category == "resume_deep_dive"]
    assert resume_qs
    assert any(("MPI进程模型" in q) or ("掌握程度" in q) for q in resume_qs)


def test_project_line_uses_domain_specific_question_when_dem_present():
    text = "多相流模型：欧拉-拉格朗日耦合、DEM离散元碰撞"
    bank = build_question_bank(text, "航天一院", "多相CFD仿真", mode="mixed")
    resume_qs = [q.question for q in bank if q.category == "resume_deep_dive"]
    assert resume_qs
    assert any(("DEM/碰撞模型" in q) or ("欧拉-拉格朗日框架" in q) for q in resume_qs)


def test_extract_question_like_lines_from_markdown():
    from app.engine import _extract_question_like_lines

    md = """
# Backend Interview
- Q: What is idempotency?
- Redis缓存击穿、穿透、雪崩怎么区分？
- Installation guide
"""
    lines = _extract_question_like_lines(md, limit=5)
    assert any("idempotency" in x.lower() for x in lines)
    assert any("缓存击穿" in x for x in lines)


def test_query_candidates_include_company_and_role():
    from app.engine import _query_candidates

    qs = _query_candidates("ByteDance", "后端研发实习")
    text = " ".join(qs).lower()
    assert "bytedance" in text
    assert "backend" in text


def test_clean_text_for_extract_removes_html():
    from app.engine import _clean_text_for_extract

    s = "<p>Hello <b>Interview</b></p>"
    assert _clean_text_for_extract(s) == "Hello Interview"


def test_extract_ddg_results_parse_redirect_url():
    from app.engine import _extract_ddg_results

    html = '<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpost">ByteDance Interview Experience</a>'
    items = _extract_ddg_results(html, limit=3)
    assert items
    assert items[0]["url"].startswith("https://example.com")


def test_query_candidates_include_resume_tokens():
    from app.engine import _query_candidates

    qs = _query_candidates("Acme", "Backend Intern", resume_text="mpi openmp fluid dynamics")
    merged = " ".join(qs).lower()
    assert "mpi" in merged or "openmp" in merged


def test_query_candidates_for_cfd_role_not_forced_backend_only():
    from app.engine import _query_candidates

    qs = _query_candidates("航天一院", "多相CFD仿真", resume_text="MPI 多相流 Navier Stokes")
    merged = " ".join(qs).lower()
    assert "cfd" in merged or "fluid" in merged


def test_auto_profile_terms_for_cfd_hpc_resume():
    from app.engine import _auto_extract_profile_terms

    terms = _auto_extract_profile_terms("航天一院", "多相CFD仿真", "MPI OpenMP Navier-Stokes solver", limit=12)
    merged = " ".join(terms).lower()
    assert "cfd" in merged or "navier" in merged
    assert "mpi" in merged or "openmp" in merged


def test_education_line_semantic_filter():
    from app.engine import _is_education_like_line

    line = "Tsinghua University Mechanical Engineering Master 2024-2027 GPA 3.8"
    assert _is_education_like_line(line) is True


def test_project_line_claude_mpi_not_fallback_template():
    text = "Claude code加速MPI并行计算 2026.01-2026.02项目"
    bank = build_question_bank(text, "Acme", "Backend Intern", mode="mixed")
    resume_qs = [q.question for q in bank if q.category == "resume_deep_dive"]
    assert resume_qs
    assert any("AI编程工具加速MPI" in q or "MPI并行" in q for q in resume_qs)
    assert not any("背景-目标-职责-技术方案-量化结果-复盘" in q for q in resume_qs)
