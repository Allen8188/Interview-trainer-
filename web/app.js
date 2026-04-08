const state = {
  sessionId: null,
  currentQuestion: null,
  recognition: null,
  listening: false,
  recorder: null,
  recording: false,
  audioChunks: [],
};

const $ = (id) => document.getElementById(id);

function setLog(id, text) {
  $(id).textContent = text;
}

async function initPrivacyWizard() {
  try {
    const resp = await fetch("/api/privacy/wizard");
    if (!resp.ok) return;
    const data = await resp.json();
    $("llm-enabled").checked = !!data.defaults?.llm_enabled;
    $("llm-send-raw").checked = !!data.defaults?.llm_send_raw;
  } catch (_) {
    // ignore
  }
}

function applySessionData(data) {
  state.sessionId = data.session_id;
  state.currentQuestion = data.question;
  $("interview-card").classList.remove("hidden");
  $("question-text").textContent = data.question?.question || "暂无问题";
  renderDialog(data.dialog || []);
}

function renderDialog(dialog = []) {
  const box = $("chat-log");
  box.innerHTML = "";
  dialog.forEach((m) => {
    const div = document.createElement("div");
    let cls = "interviewer";
    let speaker = "面试官";
    if (m.role === "candidate") {
      cls = "candidate";
      speaker = "你";
    } else if (m.role === "interviewer_interrupt") {
      cls = "interviewer_interrupt";
      speaker = "面试官(打断)";
    }
    div.className = `msg ${cls}`;
    div.textContent = `${speaker}: ${m.text}`;
    box.appendChild(div);
  });
  box.scrollTop = box.scrollHeight;
}

async function uploadResume() {
  const fileInput = $("resume-file");
  if (!fileInput.files.length) {
    setLog("setup-log", "请先选择简历文件（docx/txt）。");
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  const resp = await fetch("/api/resume/upload", { method: "POST", body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `上传失败: ${err.detail || resp.statusText}`);
    return;
  }
  const data = await resp.json();
  $("resume").value = data.resume_text;
  setLog("setup-log", "简历解析成功，已自动填入文本框。");
}

async function createSession() {
  const payload = {
    company: $("company").value.trim(),
    role: $("role").value.trim(),
    mode: $("mode").value,
    pressure_level: $("pressure-level").value,
    interviewer_style: $("interviewer-style").value,
    session_label: $("session-label").value.trim(),
    llm_enabled: $("llm-enabled").checked,
    llm_provider: "openai_compatible",
    llm_model: $("llm-model").value.trim(),
    llm_base_url: $("llm-base-url").value.trim(),
    llm_mode: $("llm-mode").value,
    llm_api_key: $("llm-api-key").value.trim(),
    llm_send_raw: $("llm-send-raw").checked,
    rounds: Number($("rounds").value || 8),
    target_minutes: Number($("target-minutes").value || 35),
    resume_text: $("resume").value.trim(),
  };

  const resp = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `创建失败: ${err.detail || resp.statusText}`);
    return;
  }

  const data = await resp.json();
  applySessionData(data);
  setLog("setup-log", `会话已创建（${data.session_label}，模式: ${data.mode}，强度: ${data.pressure_level}，LLM: ${data.llm_enabled ? "开" : "关"}），题库候选 ${data.total_candidates} 道，计划轮数 ${data.round_limit}（建议 ${data.suggested_rounds}，目标 ${data.target_minutes} 分钟）。`);
}

async function applyLLMConfig() {
  if (!state.sessionId) {
    setLog("live-feedback", "请先创建会话。");
    return;
  }
  const payload = {
    llm_enabled: $("llm-enabled").checked,
    llm_provider: "openai_compatible",
    llm_model: $("llm-model").value.trim(),
    llm_base_url: $("llm-base-url").value.trim(),
    llm_mode: $("llm-mode").value,
    llm_api_key: $("llm-api-key").value.trim(),
    llm_send_raw: $("llm-send-raw").checked,
  };
  const resp = await fetch(`/api/session/${state.sessionId}/llm`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("live-feedback", `更新LLM设置失败: ${err.detail || resp.statusText}`);
    return;
  }
  const data = await resp.json();
  setLog("live-feedback", `LLM设置已更新：enabled=${data.llm_enabled}, model=${data.llm_model}, mode=${data.llm_mode}, key=${data.api_key_stored}`);
}

async function loadHistoryList() {
  const resp = await fetch("/api/history");
  if (!resp.ok) {
    setLog("setup-log", "历史记录加载失败。");
    return;
  }
  const data = await resp.json();
  const select = $("history-select");
  select.innerHTML = "";
  if (!data.items?.length) {
    const op = document.createElement("option");
    op.value = "";
    op.textContent = "暂无历史记录";
    select.appendChild(op);
    setLog("setup-log", "暂无历史记录。");
    return;
  }
  data.items.forEach((it) => {
    const op = document.createElement("option");
    op.value = it.id;
    op.textContent = `${it.session_label || "未命名"} | ${it.mode} | ${it.history_count}题 | ${it.redacted ? "已脱敏" : "未脱敏"}`;
    select.appendChild(op);
  });
  setLog("setup-log", `已加载 ${data.items.length} 条历史记录。`);
}

async function restoreHistory() {
  const id = $("history-select").value;
  if (!id) {
    setLog("setup-log", "请先选择历史记录。");
    return;
  }
  const resp = await fetch(`/api/history/${id}/restore`, { method: "POST" });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `恢复失败: ${err.detail || resp.statusText}`);
    return;
  }
  const data = await resp.json();
  applySessionData(data);
  setLog("setup-log", `已恢复历史记录（${data.session_label}，来源 ${data.restored_from}），新会话ID: ${data.session_id}`);
}

async function renameHistory() {
  const id = $("history-select").value;
  const newLabel = $("history-rename").value.trim();
  if (!id) {
    setLog("setup-log", "请先选择历史记录。");
    return;
  }
  if (!newLabel) {
    setLog("setup-log", "请输入新的会话名。");
    return;
  }
  const resp = await fetch(`/api/history/${id}/label`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_label: newLabel }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `重命名失败: ${err.detail || resp.statusText}`);
    return;
  }
  setLog("setup-log", `重命名成功: ${newLabel}`);
  await loadHistoryList();
}

async function deleteHistory() {
  const id = $("history-select").value;
  if (!id) {
    setLog("setup-log", "请先选择历史记录。");
    return;
  }
  const resp = await fetch(`/api/history/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `删除失败: ${err.detail || resp.statusText}`);
    return;
  }
  setLog("setup-log", "删除成功。");
  await loadHistoryList();
}

function exportHistory() {
  const id = $("history-select").value;
  if (!id) {
    setLog("setup-log", "请先选择历史记录。");
    return;
  }
  window.open(`/api/history/${id}/export`, "_blank");
}

async function importHistory() {
  const fileInput = $("history-import-file");
  if (!fileInput.files.length) {
    setLog("setup-log", "请先选择要导入的 JSON 文件。");
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  const resp = await fetch("/api/history/import", { method: "POST", body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("setup-log", `导入失败: ${err.detail || resp.statusText}`);
    return;
  }
  const data = await resp.json();
  setLog("setup-log", `导入成功，新ID: ${data.session_id}（来源: ${data.restored_from}）`);
  await loadHistoryList();
}

async function fetchMaterials() {
  if (!state.sessionId) {
    setLog("setup-log", "请先创建会话，再抓取素材。");
    return;
  }
  setLog("setup-log", "正在抓取 GitHub 开源面试素材...");
  const resp = await fetch(`/api/session/${state.sessionId}/materials?refresh=1`, { method: "POST" });
  const ul = $("materials");
  ul.innerHTML = "";

  if (!resp.ok) {
    setLog("setup-log", "素材抓取失败，请稍后再试。");
    return;
  }

  const data = await resp.json();
  if (!data.materials?.length) {
    const diag = data.diagnostic ? JSON.stringify(data.diagnostic) : "{}";
    setLog("setup-log", `未抓到素材。已尝试多源抓取（GitHub/Reddit/dev.to/Web）和二次放宽检索。诊断: ${diag}`);
    return;
  }

  data.materials.forEach((m) => {
    const li = document.createElement("li");
    li.innerHTML = `<a href="${m.url}" target="_blank" rel="noreferrer">${m.title}</a> - ${m.summary || ""}`;
    ul.appendChild(li);
  });
  const src = data.source_counts ? JSON.stringify(data.source_counts) : "{}";
  setLog("setup-log", `素材加载完成，共 ${data.materials.length} 条。${data.cached ? "（缓存）" : "（已刷新）"} 来源: ${src}`);
}

async function submitAnswer() {
  if (!state.sessionId || !state.currentQuestion) {
    setLog("live-feedback", "请先创建会话并开始面试。");
    return;
  }
  const answer = $("answer").value.trim();
  const resp = await fetch(`/api/session/${state.sessionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("live-feedback", `提交失败: ${err.detail || resp.statusText}`);
    return;
  }

  const data = await resp.json();
  const eva = data.evaluation;
  if (eva) {
    setLog(
      "live-feedback",
      `总分: ${eva.score}/10 (${eva.level})
技术: ${eva.dimensions.technical} 结构: ${eva.dimensions.structure} 沟通: ${eva.dimensions.communication} 岗位贴合: ${eva.dimensions.job_fit}
标准要点命中率: ${Math.round((eva.rubric_hit_rate || 0) * 100)}%
命中要点: ${(eva.rubric_hits || []).slice(0, 4).join("、") || "无"}
缺失要点: ${(eva.rubric_missing || []).slice(0, 4).join("、") || "无"}
是否打断: ${eva.interrupted ? "是" : "否"}
LLM增强: ${eva.llm_used ? "已使用" : "本地规则"}
LLM状态: ${eva.llm_error ? eva.llm_error : "ok"}
反馈: ${eva.feedback}
追问: ${eva.follow_up}`
    );
  }
  renderDialog(data.dialog || []);

  if (data.done) {
    $("question-text").textContent = "本轮已结束，请点击“结束并复盘”。";
    state.currentQuestion = null;
    return;
  }

  state.currentQuestion = data.next_question;
  $("question-text").textContent = data.next_question.question;
  $("answer").value = "";
}

async function reviewSession() {
  if (!state.sessionId) {
    setLog("live-feedback", "请先创建面试会话。");
    return;
  }
  const resp = await fetch(`/api/session/${state.sessionId}/review`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("live-feedback", `复盘失败: ${err.detail || resp.statusText}`);
    return;
  }

  const data = await resp.json();
  $("review-card").classList.remove("hidden");
  $("summary").textContent = JSON.stringify(data.summary, null, 2);
  renderDialog(data.dialog || []);

  const weakList = $("weak-list");
  weakList.innerHTML = "";
  const sysTemplate = $("sys-template");
  sysTemplate.innerHTML = "";
  if (!data.weak_points.length) {
    weakList.textContent = "当前没有明显弱项，建议继续提高回答的量化与工程细节。";
  } else {
    data.weak_points.forEach((item, idx) => {
      const block = document.createElement("div");
      block.className = "log";
      block.textContent = `弱项 ${idx + 1}
问题: ${item.question}
维度: 技术${item.dimensions.technical}/结构${item.dimensions.structure}/沟通${item.dimensions.communication}/贴合${item.dimensions.job_fit}
点评: ${item.feedback}
建议作答: ${item.ideal}`;
      weakList.appendChild(block);
    });
  }

  (data.system_design_template?.steps || []).forEach((s) => {
    const li = document.createElement("li");
    li.textContent = s;
    sysTemplate.appendChild(li);
  });
}

function setupVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    $("voice-btn").disabled = true;
    $("voice-btn").textContent = "当前浏览器不支持语音识别";
    return;
  }

  state.recognition = new SpeechRecognition();
  state.recognition.lang = "zh-CN";
  state.recognition.interimResults = true;
  state.recognition.continuous = true;

  state.recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    $("answer").value = ($("answer").value + " " + transcript).trim();
  };

  state.recognition.onend = () => {
    if (state.listening) {
      state.recognition.start();
    }
  };
}

function toggleVoice() {
  if ($("stt-engine").value !== "browser") {
    setLog("live-feedback", "当前选择的是本地Whisper，请使用“开始录音上传”按钮。");
    return;
  }
  if (!state.recognition) return;
  if (!state.listening) {
    state.listening = true;
    state.recognition.start();
    $("voice-btn").textContent = "停止语音识别";
  } else {
    state.listening = false;
    state.recognition.stop();
    $("voice-btn").textContent = "开始语音识别";
  }
}

async function uploadAudioToSTT(blob) {
  const form = new FormData();
  form.append("file", blob, "answer.webm");
  form.append("language", "zh");
  const resp = await fetch("/api/stt", { method: "POST", body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    setLog("live-feedback", `Whisper转写失败: ${err.detail || resp.statusText}`);
    return;
  }
  const data = await resp.json();
  if (!data.text) {
    setLog("live-feedback", "Whisper未识别到有效内容，请重试。");
    return;
  }
  $("answer").value = ($("answer").value + " " + data.text).trim();
  setLog("live-feedback", "Whisper转写成功，文本已填入回答框。");
}

async function initRecorderIfNeeded() {
  if (state.recorder) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    setLog("live-feedback", "当前浏览器不支持录音上传，请切换浏览器语音识别。");
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        state.audioChunks.push(event.data);
      }
    };
    rec.onstop = async () => {
      const blob = new Blob(state.audioChunks, { type: "audio/webm" });
      state.audioChunks = [];
      await uploadAudioToSTT(blob);
    };
    state.recorder = rec;
    return true;
  } catch (err) {
    setLog("live-feedback", `无法获取麦克风权限: ${err}`);
    return false;
  }
}

async function toggleRecordUpload() {
  if ($("stt-engine").value !== "local_whisper") {
    setLog("live-feedback", "当前选择的是浏览器语音识别，请使用“开始语音识别”。");
    return;
  }
  const ok = await initRecorderIfNeeded();
  if (!ok) return;
  if (!state.recording) {
    state.audioChunks = [];
    state.recording = true;
    state.recorder.start();
    $("record-btn").textContent = "停止录音并上传";
    setLog("live-feedback", "录音中，请作答后再次点击按钮结束。");
  } else {
    state.recording = false;
    state.recorder.stop();
    $("record-btn").textContent = "开始录音上传";
    setLog("live-feedback", "录音结束，正在上传到Whisper转写...");
  }
}

$("upload-btn").addEventListener("click", uploadResume);
$("create-btn").addEventListener("click", createSession);
$("materials-btn").addEventListener("click", fetchMaterials);
$("history-load-btn").addEventListener("click", loadHistoryList);
$("history-restore-btn").addEventListener("click", restoreHistory);
$("history-rename-btn").addEventListener("click", renameHistory);
$("history-delete-btn").addEventListener("click", deleteHistory);
$("history-export-btn").addEventListener("click", exportHistory);
$("history-import-btn").addEventListener("click", importHistory);
$("submit-btn").addEventListener("click", submitAnswer);
$("review-btn").addEventListener("click", reviewSession);
$("voice-btn").addEventListener("click", toggleVoice);
$("record-btn").addEventListener("click", toggleRecordUpload);
$("apply-llm-btn").addEventListener("click", applyLLMConfig);

setupVoice();
initPrivacyWizard();
