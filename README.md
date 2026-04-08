# Interview Trainer (MVP)

一个用于模拟视频面试训练的本地系统：

- 输入简历、公司、岗位，自动生成题库（后端 + 简历深挖 + 企业隐私场景）
- 支持模式切换：`后端技术面` / `系统设计面` / `HR行为面` / `混合模式`
- 支持追问强度档位：`温和` / `标准` / `高压`
- 支持“本地规则/LLM增强”二选一（或混合），用户可自带 API key
- 支持语音转文字（浏览器 Web Speech API）
- 可选接入本地 Whisper 服务端转写（稳定性更高，开源可复用）
- 每题多维打分（技术、结构、沟通、岗位贴合）与追问拷打
- 轮次结束后输出复盘报告
- 可拉取 GitHub 开源面试素材做学习补充
- GitHub 素材默认仅用于学习补充，不直接替代“简历深挖主线题”
- 题库会自动融合外部公开面试资料（默认插入在前几道简历题之后），提升专业性
- 支持本地历史记录：自动保存会话、列表查看、恢复继续训练
- 支持素材缓存：同岗位24小时内优先走本地缓存，自动过期更新

## 1. 一键启动（推荐，不污染本机环境）

前提：已安装 Docker Desktop（或 Linux Docker Engine + Compose）。

平台入口：

- Windows (CMD): 双击 `scripts\start.bat`，停止 `scripts\stop.bat`
- Windows (双击入口): 双击仓库根目录 `Start-Interview-Trainer.bat`，停止 `Stop-Interview-Trainer.bat`
- Windows (PowerShell): 运行 `.\scripts\start.ps1`，停止 `.\scripts\stop.ps1`
- macOS: 双击 `scripts/start.command`，停止 `scripts/stop.command`
- Linux: 运行 `./scripts/start.sh`，停止 `./scripts/stop.sh`
- WSL: 在 WSL 运行 `./scripts/start.sh`（需 Windows Docker Desktop + WSL Integration）

启动后访问：`http://localhost:8000`

默认自动拉起浏览器。如需禁用自动打开：设置 `IT_OPEN_BROWSER=0` 再启动。

## 1.1 Windows Release（下载即用）

- 在 GitHub Releases 下载：`InterviewTrainer-Windows.zip`
- 解压后双击：`Launch-Interview-Trainer.bat`
- 停止时双击：`Stop-Interview-Trainer.bat`

说明：
- 该包使用 Docker 运行，不要求本机安装 Python。
- 首次使用只需要安装 Docker Desktop。

### Windows 免 Docker 版本

- 在 GitHub Releases 下载：`InterviewTrainer-Windows-Portable.zip`
- 解压后双击：`Launch-Interview-Trainer-NoDocker.bat`
- 停止时双击：`Stop-Interview-Trainer-NoDocker.bat`

说明：
- 该包不依赖 Docker。
- Python 运行时已打包进 `InterviewTrainer.exe`。

### 启动前自动检查

- `start.sh` / `start.bat` 会先检查：
  - Docker 命令是否存在
  - Docker Compose 是否可用
  - Docker daemon 是否已启动
- 若未安装 Docker，会提示并可打开 Docker 下载页。

### WSL 说明

- 可以在 WSL 使用本项目，但推荐在 Windows 安装 Docker Desktop。
- 需在 Docker Desktop 打开：`Settings -> Resources -> WSL Integration`，并启用当前发行版。
- 启动后在 Windows 浏览器访问：`http://localhost:8000`（通常可直接访问）。
- 若脚本未能自动拉起浏览器（个别 WSL 配置会禁用 Windows 互操作），请手动在 Windows 打开：`http://localhost:8000`。

## 2. 本地开发安装（可选）

```bash
cd /home/allen/Article/interview-trainer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开：

- http://127.0.0.1:8000/

## 4. 运行测试

```bash
pytest -q
```

## 5. 注意事项

- 浏览器语音识别依赖浏览器（推荐 Chrome）与麦克风权限。
- 本地Whisper是可选增强，不安装也能完整运行项目。
- GitHub 素材抓取使用公开 API，可能触发限流。
- 历史记录与素材缓存默认保存在用户主目录：`~/.interview-trainer/data`（可用 `IT_DATA_DIR` 覆盖）。
- 持久化默认脱敏：手机号、邮箱、证件号会自动掩码保存。
- 仓库已忽略 `data/`，避免敏感记录误提交。
- LLM key 只保存在内存会话，不会写入历史文件。
- 运行策略默认 `assist_only`：LLM仅做补充，不接管主流程；质量不达标自动回退本地规则。

## 6. 隐私与数据控制

- 查看隐私状态：`GET /api/privacy/status`
- 删除单条历史：`DELETE /api/history/{session_id}`
- 导出历史：`GET /api/history/{session_id}/export`
- 导入历史：`POST /api/history/import`（上传导出的 json）
- 隐私向导建议：`GET /api/privacy/wizard`

## 7. 可选：启用本地 Whisper 转写

```bash
cd /home/allen/Article/interview-trainer
python3 -m pip install --user -r requirements-whisper.txt
```

可选环境变量：

- `WHISPER_MODEL`：默认 `small`，可选 `tiny/base/small/medium/large-v3`
- `WHISPER_DEVICE`：默认 `cpu`，可设置为 `cuda`
- `WHISPER_COMPUTE_TYPE`：默认 `int8`

前端选择 `本地Whisper服务端` 后，点击 `开始录音上传` 即可转写。

## 8. 可扩展方向

- 接入本地 Whisper 实现稳定 STT
- 增加题库来源（LeetCode/面经库/RAG）
- 引入真实 LLM 评估（多维打分：逻辑、细节、沟通）
- 增加“HR面试模式”和“系统设计白板模式”

## 9. 发布说明（维护者）

- 打 tag 并发布 Release 后，GitHub Actions 会自动生成并上传 `InterviewTrainer-Windows.zip`：
  - 工作流：`.github/workflows/release-windows.yml`
- 本地手动打包命令：

```bash
./scripts/package-windows-release.sh
```
