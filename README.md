# Breast Cancer Extractor

完全本地运行、带证据定位与人工审核留痕的乳腺癌科研病历结构化工具。

> 用于科研数据抽取，不用于临床诊断或治疗决策。

---

# 我到底该双击哪个脚本？

如果你是在 Windows 上下载了项目源码 ZIP，并且只是想**直接运行 Breast Cancer Extractor**：

```text
start-native.bat
```

**日常直接运行源码版，就双击 `start-native.bat`。** 第一次运行时它会自动在项目目录内安装 uv、准备 Python 环境和依赖；以后仍然继续双击这个文件即可。

其他脚本只在对应场景使用：

| 目的 | 应该运行 |
|---|---|
| Windows 直接运行源码 / Native 版 | **`start-native.bat`** |
| 制作可复制到其他电脑的 Windows Portable | `build-portable.bat` |
| 制作自带 Ollama 的 Windows Portable | `build-portable-with-ollama.bat` |
| Docker 第一次安装 | `install.bat` |
| Docker 日常启动 | `start.bat` |

> **不要为了日常运行源码版去执行 `build-portable.bat`。** `build-portable.bat` 是“打包程序”，不是普通启动程序。

---

# Windows 极简版

Windows 版默认只需要 **OCR**，**Ollama / 本地 AI 是可选项**。

> [!CAUTION]
> **严重警告：Windows Native / Portable 请务必放在纯英文（ASCII）路径下运行。**
> 
> 不要把程序放在包含中文、日文、韩文或其他非 ASCII 字符的目录中。PaddleOCR / PaddleX 在 Windows 下可能能够看到模型目录，却在底层推理阶段无法正常打开 `inference.json` 等模型文件，最终表现为 **`OCR unavailable: 500 Internal Server Error`**。
> 
> **错误示例：** `F:\临床数据提取\BreastCancerExtractor\`
> 
> **推荐示例：** `F:\BreastCancerExtractor\`、`D:\BCE\`
> 
> 如果同一份 `dist` 在本地英文路径可以 OCR，但复制到移动硬盘后 OCR 失败，请首先检查**完整路径中是否包含中文或其他非 ASCII 字符**。不要先重装 PaddleOCR，也不要先删除模型。

## 直接运行源码版（推荐用于本机使用）

1. GitHub：`Code → Download ZIP`
2. 完整解压项目到纯英文路径。
3. 双击：

```text
start-native.bat
```

首次运行如果项目内还没有 uv，脚本会自动把 uv 安装到项目目录 `.uv-local\`，并使用项目根目录的 `uv.toml` 通过 CERNET PyPI 镜像下载 Python 依赖。不会修改用户的全局 PATH，也不会写入用户级 uv 配置。

以后再次运行，仍然只需要双击：

```text
start-native.bat
```

## 制作 Windows Portable

只有在你需要**打包一个可复制到其他电脑运行的版本**时，才双击：

```text
build-portable.bat
```

构建完成后进入：

```text
dist\BreastCancerExtractor\
```

双击：

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

> [!CAUTION]
> **Windows 路径要求：请使用纯英文 / ASCII 路径。** 例如 `F:\BreastCancerExtractor\`。如果将同一 Portable 移动到 `F:\临床数据提取\BreastCancerExtractor\` 等含中文目录的路径后出现 OCR 500、`Cannot open ... inference.json`、模型文件明明存在却无法读取等问题，应先把整个目录移回纯英文路径再重试。

### Windows Native 直接启动

日常运行源码版：

```text
start-native.bat
```

它会使用项目内 uv bootstrap：缺少 uv 时自动安装，然后执行 `uv run --group native` 启动程序。

### 默认精简构建

仅当需要制作 Portable 时运行：

```text
build-portable.bat
```

构建电脑需要：

- 64 位 Windows；
- 首次构建时可访问网络；
- 正常的 CPU / GPU 驱动。

`build-portable.bat` 会自动准备项目自己的 uv。uv 可执行文件、uv 管理的 Python 和缓存均保留在项目目录中，不要求提前安装系统级 uv。

此版本包含主程序和 PaddleOCR，**不包含 Ollama**。

### 可选本地 AI

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

### Windows 目录约定

```text
BreastCancerExtractor\
├─ BreastCancerExtractor.exe
├─ database\                 # 只保存患者数据，可整体搬运和拼接
│  └─ patients\
│     └─ <7位病案号>\
│        ├─ patient.sqlite
│        ├─ manifest.json
│        └─ sanitized\
├─ config\                   # 本机设置：runtime_config.json、instance.json
├─ runtime\                  # 可重建索引/缓存：catalog.sqlite、OCR缓存等
├─ models\llm\
├─ local_knowledge\
└─ logs\
```

**患者资料只需要备份 `database\`。** `runtime\catalog.sqlite` 只是可重建索引，删除后程序会从 `database\patients\*\patient.sqlite` 自动恢复患者总索引。

把另一台电脑中不同病案号的患者目录直接复制进 `database\patients\`，下次启动会自动纳入本机索引。相同病案号若内容不同不会静默覆盖，应通过患者目录冲突流程处理。

旧版本首次启动会自动迁移：

```text
database\catalog.sqlite      → runtime\catalog.sqlite
database\runtime_config.json → config\runtime_config.json
database\instance.json       → config\instance.json
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

Docker 版同样把 `database/`、`config/`、`runtime/` 分开挂载。Ollama 模型可通过：

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
确认后自动整理只读派生字段
↓
患者级数据预览与导出
```

切换患者后，当前 OCR / AI 前端处理列表会清空，避免不同患者任务混在一起。

---

# TNM 与影像尺寸

当前项目**重点保存完整 cTNM/ycTNM 和 pTNM/ypTNM，不保存 AJCC Stage Group**。

完整 TNM 字符串是唯一可编辑主字段。例如：

```text
cT2N1M0
pT1cN0M0
```

人工确认完整 TNM 后，系统自动生成只读字段：

```text
cT2 | cN1 | cM0
pT1c | pN0 | pM0
```

这些拆分字段用于患者回顾、数据总览和结构化导出，**不能单独修改**；若有错误，应修改完整 TNM 主字段并重新确认，随后自动重算。

影像尺寸采用相同逻辑。完整表达例如：

```text
32×18×15 mm
```

作为可编辑主字段保留；人工确认后按原文顺序自动产生 3 个只读径线字段：

```text
32 | 18 | 15
```

若原文只有 `32×18 mm`，第 3 径保持空白，不复制、不臆测。cm 会在派生尺寸中统一换算为 mm。

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
- 完整 TNM / 影像尺寸人工确认后自动生成只读拆分字段；
- 人工确认与审计留痕；
- 患者级宽表预览与 CSV 导出；
- 可搬运患者数据包与可重建 runtime catalog；
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
├─ patient.sqlite
├─ manifest.json
└─ sanitized\
```

`database/` 是患者数据的便携边界。不同电脑之间直接复制不同病案号目录即可；启动时会自动把新增患者加入 `runtime/catalog.sqlite`。同一病案号存在不同内容时不要直接覆盖，应保留两个目录并使用冲突处理。

患者数据备份只需：

```text
database\
```

如需保留本机模型选择等设置，可额外备份：

```text
config\
models\llm\
local_knowledge\
```

`runtime/` 不需要备份。

---

# 本地开发

Windows Native 推荐直接双击：

```text
start-native.bat
```

该入口不要求系统提前安装 uv。

如果开发者已经自行安装了全局 uv，也可以继续直接运行：

```powershell
uv sync
uv run uvicorn app.main:app --reload
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

`.gitignore` 已排除患者数据、`config/`、`runtime/`、`.uv-local/`、uv 缓存、模型、日志、GGUF、离线镜像和本机配置等内容。

提交前请确认不存在：

- 病历图片；
- 患者身份信息；
- 患者数据库；
- 本地模型权重；
- 机构内部知识库。
