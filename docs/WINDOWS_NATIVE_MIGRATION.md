# Windows Native 迁移说明

## 仓库现状审计

迁移前的稳定 Docker 基线为 Git tag `docker-stable-v0.1.0`，开发分支为 `codex/windows-native-portable`。

可直接复用的核心模块：

- `app/main.py` 与 `app/static/`：FastAPI API 和现有 Web 界面；
- SQLite、患者/图片/ROI/审核/审计日志等业务逻辑；
- `knowledge/`：Schema、规则、提示词和字段顺序；
- `ocr/service.py`：PaddleOCR 服务实现；
- Ollama Provider、模型选择和模型导入逻辑。

原有 Docker 耦合主要来自：

- `ollama`、`ocr`、`host.docker.internal` 等容器网络地址；
- `/app/database`、`/app/workspace`、`/models/llm` 等容器绝对路径；
- Compose volume 和服务启动顺序；
- OCR 与 Ollama 由 Compose 创建并管理。

迁移没有重写上述业务模块。`RUNTIME_MODE`、portable/resource root 和环境变量负责选择 Docker 或 Windows Native 路径；Compose 明确传入 `RUNTIME_MODE=docker`，Windows 启动器明确传入 `windows_native`。

## Windows 启动流程

`app/native_launcher.py` 承担薄启动层职责：

1. 将数据库、工作区和模型路径设置到 Portable 根目录；
2. 启动同一可执行文件中的本地 OCR 子服务；
3. 检查已有 Windows Ollama；没有时启动 `runtime/ollama/ollama.exe`；
4. 启动现有 FastAPI 应用并打开浏览器；
5. 主进程退出时，仅停止本次由它启动的辅助进程，不关闭用户原本已运行的 Ollama。

Ollama 仍是独立组件。默认端口是 `11434`；测试或特殊部署可通过 `BCE_OLLAMA_PORT` 覆盖。推荐 Qwen3 8B，但模型名不写死。

## 开发与构建

Windows 开发运行：

```powershell
start-native.bat
```

构建 onedir：

```powershell
build-portable.bat
```

构建脚本会同步 `native` 依赖、初始化 OCR 权重、执行 PyInstaller、创建可写目录，并在本机发现 Ollama 时复制 standalone runtime。生成目录：

```text
dist/BreastCancerExtractor/
├─ BreastCancerExtractor.exe
├─ _internal/
├─ database/
│  └─ patients/<病案号>/
│     ├─ patient.sqlite
│     ├─ manifest.json
│     └─ sanitized/
├─ models/
├─ local_knowledge/
└─ runtime/
   ├─ ollama/
   └─ paddlex-cache/
```

## 已执行验证

- Windows 开发环境完整测试；
- Windows Native 开发模式健康检查；
- 开发模式真实 PaddleOCR 推理；
- PyInstaller onedir 构建；
- 打包后真实 PaddleOCR 推理；
- 打包后连接已有 Windows Ollama；
- 打包后在独立端口启动随包 Ollama fallback；
- Docker Compose 配置解析和 Docker 回归测试。

真正的“干净 Windows”验收仍应在没有 Python、uv、Docker、Ollama 的独立电脑或虚拟机执行，不能仅以开发电脑上的隔离测试替代。建议至少验证启动、OCR、导入本地模型、AI 抽取、数据库持久化、关闭后重启及整目录迁移。

## 发布注意事项

- 发布整个 onedir，不能只发布 exe；
- 发布前核对 Ollama 和模型的再分发许可；
- 不将真实病历、数据库、日志、GGUF 或 Ollama 模型权重提交到 Git；
- 升级时备份并保留 `database/`、`models/` 和 `local_knowledge/`；
- Windows Native 完成后继续保留 Docker 回归测试，避免两种运行方式漂移。
