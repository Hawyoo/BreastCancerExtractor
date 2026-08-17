# Breast Cancer Extractor

完全本地运行、带证据定位与人工审核留痕的乳腺癌科研病历结构化工具。

当前版本是首个可运行 MVP，重点把最危险也最基础的边界做实：**未经脱敏的原图不发送给后端，也不保存到磁盘**。用户在浏览器内完成裁剪、不可逆实心遮盖和多个信息区域（ROI）标注；浏览器只把重新编码的脱敏 PNG 传给本地服务。

## 当前已实现

- 患者科研编号管理；
- 浏览器端原图读取、裁剪、实心遮盖、撤销与多个 ROI；
- 只接受重新编码 PNG 的脱敏图片接口，服务端再次解码/编码并清除元数据；
- 原始文件名不自动写入数据库，避免文件名中的姓名或住院号泄露；
- SQLite 表：`patients`、`documents`、`regions`、`observations`、`audit_log`、`model_runs`；
- `UNPROCESSED → AI_PROCESSED / REVIEW_REQUIRED → VERIFIED` 状态基础；
- AI 原值、当前值、人工修改和人工确认分离保存；
- Ollama 已安装模型查询、本地 `models/llm/*.gguf` 扫描和导入接口；
- Docker Compose 本地部署，Ollama 不向宿主机公开端口；
- 乳腺癌病理 Schema、IHC 规则和 Prompt 的首版骨架。

尚未完成的模块包括 PaddleOCR/PP-Structure 实际推理、LLM 自动抽取任务队列、证据文字框精确回链、Excel 导出和医院离线镜像打包。代码结构已为这些阶段保留边界，但 README 不把骨架描述成已完成功能。

## 隐私模型

```text
用户本地原图
  ↓ 仅浏览器内存
裁剪 + 实心遮盖 + ROI
  ↓ Canvas 重新编码 PNG（删除 EXIF）
本地 FastAPI
  ↓ 再次解码/编码
workspace/patients/<patient_code>/sanitized/<uuid>.png
```

注意：浏览器崩溃转储、操作系统交换文件、屏幕录制等属于操作系统层面的风险，无法仅靠 Web 应用绝对消除。医院部署仍应配合加密磁盘、受控账户和禁用外网策略。

`OFFLINE_MODE=true` 时程序只允许连接 `ollama`、`localhost` 或回环地址，同时前端 CSP 将网络请求限制到当前本地站点。当前代码没有遥测、CDN、第三方字体或外部错误上报。

## Docker 运行

要求：Windows 11/10、WSL2、Docker Desktop。

1. 复制 `.env.example` 为 `.env`，按需修改端口；
2. 双击 `start.bat`，或运行：

```powershell
docker compose up -d --build
```

3. 打开 <http://127.0.0.1:8765>；
4. 停止时双击 `stop.bat`。

持久化目录会在首次启动时自动出现：

```text
database/       SQLite（禁止提交）
workspace/      脱敏图及运行文件（禁止提交）
models/llm/     用户维护的 GGUF 仓库（禁止提交）
```

Ollama 的运行模型位于 Docker 命名卷 `ollama_models`；不要直接修改该卷内部结构。将 `.gguf` 放入 `models/llm/` 后，通过后续模型管理页面或 `/api/models/import` 注册。

## 本地开发（uv）

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

本地开发时 Ollama 默认地址是 `http://127.0.0.1:11434`。执行测试：

```powershell
uv run pytest
uv run ruff check .
```

## 两种发布物

同一套源码产生两类包：

- GitHub 轻量版：源码、Compose、知识库和启动脚本；镜像与模型按需获取。
- Hospital Offline Edition：额外携带 `docker save` 导出的镜像 tar、已核对许可的 OCR/LLM 模型和离线安装说明。真实患者资料永远不属于发布物。

## Git 安全

`.gitignore` 已排除 `workspace/`、`database/`、`models/`、日志、数据库、GGUF 和离线镜像。提交前仍应运行：

```powershell
git status --short
```

确认不存在病历、患者标识、数据库或模型权重。
