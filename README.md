# Breast Cancer Extractor

完全本地运行、带证据定位与人工审核留痕的乳腺癌科研病历结构化工具。

> 用于科研数据抽取，不用于临床诊断或治疗决策。

---

# Windows 极简版

Windows 版默认只需要 **OCR**，**Ollama / 本地 AI 是可选项**。

1. GitHub：`Code → Download ZIP`
2. 完整解压项目。
3. 构建电脑安装 `uv`。
4. 双击：

```text
build-portable.bat
```

5. 构建完成后进入：

```text
dist\BreastCancerExtractor\
```

6. 双击：

```text
BreastCancerExtractor.exe
```

浏览器会自动打开：

```text
http://127.0.0.1:8765
```

默认精简版**不携带 Ollama**。没有 Ollama 时仍可正常完成：

```text
图片导入 → 脱敏 → ROI → OCR → 手动录入 / 审核 → 导出
```

如果需要本地 AI，再单独安装 Ollama 即可。例如：

```powershell
ollama pull qwen3:8b
```

程序会自动连接本机 Ollama。

如果明确需要一个**自带 Ollama 的离线 Portable**，构建电脑先安装 Ollama，然后双击：

```text
build-portable-with-ollama.bat
```

> 必须保留整个 `dist\BreastCancerExtractor\` 文件夹，不要只复制单独的 exe。

---

# 部署方式

## 一、Windows Native / Portable（推荐）

Windows 版本使用 PyInstaller onedir。目标电脑运行构建后的 Portable 时不需要 Python、uv、Conda 或 Docker。

### 默认精简构建

构建电脑需要：

- 64 位 Windows；
- `uv`；
- 正常的 CPU / GPU 驱动。

运行：

```text
build-portable.bat
```

此版本包含主程序和 PaddleOCR，**不包含 Ollama**。

### 可选本地 AI

有两种方式：

**方式 A：系统 Ollama（推荐）**

单独安装并启动 Ollama，程序会连接：

```text
127.0.0.1:11434
```

用户原本已经运行的系统 Ollama 不会在 BreastCancerExtractor 退出时被关闭。

**方式 B：Portable 自带 Ollama**

构建电脑已安装 Ollama 时，运行：

```text
build-portable-with-ollama.bat
```

Ollama runtime 才会被复制到：

```text
runtime\ollama\
```

### Windows 数据目录

所有可写数据默认保存在 exe 同级目录：

```text
BreastCancerExtractor\
├─ BreastCancerExtractor.exe
├─ database\
├─ models\llm\
├─ local_knowledge\
├─ logs\
└─ runtime\
```

患者数据：

```text
database\patients\<病案号>\
```

升级或迁移前建议备份：

```text
database\
models\
local_knowledge\
```

详细说明：[`docs/WINDOWS_PORTABLE.md`](docs/WINDOWS_PORTABLE.md)

---

## 二、Docker Compose

下载并解压项目 ZIP 后，双击：

```text
install.bat
```

日常启动：

```text
启动 Docker Desktop
↓
双击 start.bat
↓
打开 http://127.0.0.1:8765
```

停止：

```text
stop.bat
```

同时退出 Docker Desktop / WSL2：

```text
stop-all.bat
```

手动启动：

```powershell
docker compose up -d --build
```

Docker 版 Ollama 模型可通过：

```powershell
docker compose exec ollama ollama pull qwen3:8b
```

> 不要随意执行 `docker compose down -v`，否则会删除 Ollama 模型卷。

---

# 基本使用流程

```text
新建患者
↓
批量导入病历图片
↓
裁剪 / 旋转 / 平移
↓
实心遮盖身份信息
↓
按需框选 ROI
↓
保存脱敏图
↓
OCR
↓
可选：本地 AI 结构化抽取
↓
人工补充 / 修改 / 确认
↓
患者级数据预览与导出
```

切换患者后，当前 OCR / AI 前端处理列表会清空，避免不同患者任务混在一起。

---

# 当前功能

- 患者科研编号管理；
- 批量图片和患者文件夹导入；
- 裁剪、平移、旋转、实心遮盖和多 ROI；
- PaddleOCR 本地识别；
- 可选 Ollama 本地 AI 抽取；
- 无 Ollama 时仅 OCR 模式；
- AI 字段人工修改与手动补充；
- 患者回顾侧栏，可随时重新查看来源图片；
- 人工确认与审计留痕；
- 患者级宽表预览与 CSV 导出；
- Windows Portable 与 Docker Compose。

---

# 隐私边界

**未经脱敏的原始图片不作为患者长期数据保存，也不发送给 OCR / LLM 后端。**

```text
原始图片
↓ 浏览器临时读取
裁剪 + 遮盖 + ROI
↓
重新编码 PNG
↓
本地保存脱敏图
↓
OCR
↓
可选本地 LLM
↓
人工审核
```

原始文件名不会自动写入患者数据库。实心遮盖会真实修改输出像素，而不是仅做网页视觉覆盖。

---

# OCR 与 AI

OCR 是基础能力，Ollama 是可选增强能力：

```text
OCR：识别文字
LLM：理解并结构化
规则：检查结果
人工：最终确认
```

没有 Ollama 时，可以直接使用 OCR 结果并手动录入字段。

推荐起始模型：

```text
Qwen3 8B
```

也可以把合法获得的 GGUF 放入：

```text
models\llm\
```

然后在模型管理中导入和切换。

---

# 数据与迁移

患者目录：

```text
database\patients\<7位病案号>\
```

不同电脑之间可复制完整患者目录，然后在首页使用“扫描患者目录”。如果目标电脑已经存在同一病案号，请使用软件提供的冲突处理流程，不要直接覆盖。

建议备份：

```text
database\
models\llm\
local_knowledge\
```

---

# 本地开发

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

Windows Native：

```text
start-native.bat
```

测试：

```powershell
uv run pytest
uv run ruff check .
```

Windows Portable：

```text
build-portable.bat
```

带 Ollama 的可选构建：

```text
build-portable-with-ollama.bat
```

---

# Git 安全

`.gitignore` 已排除患者数据、数据库、模型、日志、GGUF、离线镜像和本机配置等内容。

提交前请确认不存在：

- 病历图片；
- 患者身份信息；
- 患者数据库；
- 本地模型权重；
- 机构内部知识库。
