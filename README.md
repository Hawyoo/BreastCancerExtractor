# Breast Cancer Extractor

完全本地运行、带证据定位与人工审核留痕的乳腺癌科研病历结构化工具。

> **推荐先看部署。** README 将“怎么运行”放在最前面；项目原理、隐私设计、知识库和开发说明统一放在后面。
>
> 当前项目定位为**科研数据抽取工具**，不用于临床诊断或治疗决策。

---

# 部署

目前支持两种运行方式：

1. **Windows Native / Portable：推荐普通 Windows 用户使用**
2. **Docker Compose：适合希望固定运行环境或继续使用现有 Docker 工作流的用户**

两种方式都从 GitHub 仓库的 ZIP 开始。

---

## 一、Windows Native / Portable（推荐）

Windows 版本使用 **PyInstaller onedir**。构建完成后，目标电脑运行 Portable 目录时不需要 Python、uv、Conda 或 Docker。

### 1. 下载项目 ZIP

在 GitHub 仓库页面点击：

```text
Code → Download ZIP
```

下载完成后**完整解压**，例如：

```text
D:\BreastCancerExtractor
```

不要直接在 ZIP 压缩包预览窗口内运行脚本，也不建议把项目放入 OneDrive、网盘或其他会自动上传的目录。

### 2. 首次从源码构建 Windows Portable

> 这一步只在“从 GitHub 源码 ZIP 自行构建 Portable”时需要。构建完成后的 Portable 文件夹可以直接复制到其他 Windows 电脑运行。

构建电脑需要先准备：

- 64 位 Windows；
- [uv](https://docs.astral.sh/uv/getting-started/installation/)；
- 正常的显卡驱动；
- 如希望生成的 Portable **自带 Ollama runtime**，建议构建电脑同时准备可用的 `ollama.exe`。构建脚本会优先从本机 PATH 中寻找并复制 Ollama；如果没有找到，仍可完成程序构建，但目标电脑需要使用已安装的 Ollama，或后续手工补充 `runtime/ollama/`。

然后在项目根目录双击：

```text
build-portable.bat
```

脚本会自动：

1. 同步 Windows Native / 打包依赖；
2. 初始化并验证 PaddleOCR；
3. 使用 PyInstaller 构建 `onedir`；
4. 尝试打包 Ollama standalone runtime；
5. 写入构建信息。

构建结果位于：

```text
dist\BreastCancerExtractor\
```

### 3. 运行 Windows Portable

进入：

```text
dist\BreastCancerExtractor\
```

然后双击：

```text
BreastCancerExtractor.exe
```

必须保留并复制**整个 `BreastCancerExtractor` 文件夹**，不要只复制单独的 exe。

启动时程序会：

1. 检查 `127.0.0.1:11434` 是否已有 Ollama；
2. 如果已有 Ollama，直接使用；
3. 如果没有运行中的 Ollama，则尝试启动：

```text
runtime\ollama\ollama.exe
```

4. 自动启动 Portable 内的本地 PaddleOCR；
5. 启动本地 Web 服务；
6. 浏览器打开：

```text
http://127.0.0.1:8765
```

如果 Ollama 暂时不可用，程序本体仍应能够启动；图片整理、脱敏、ROI 等非 LLM 功能仍可使用。

### 4. 安装 / 选择 LLM

推荐模型：

```text
Qwen3 8B
```

但程序**不会把模型名称写死**，以后可以更换其他 Ollama 兼容模型。

#### 方法 A：使用本机已经安装的 Ollama 模型

如果 Windows 上已经运行 Ollama，并已有模型，Portable 会优先连接该服务。

可在 Ollama 中准备模型，例如：

```powershell
ollama pull qwen3:8b
ollama list
```

然后重新打开 BreastCancerExtractor，在 Web 端模型管理中选择相应模型。

#### 方法 B：手工维护 GGUF，适合离线使用

将合法获得的 `.gguf` 文件放入 Portable 目录中的：

```text
models\llm\
```

例如：

```text
models\llm\qwen3-8b.gguf
```

打开软件后，在 Web 端“模型管理”中扫描并导入 Ollama，再选择为当前模型。

不要直接修改 Ollama 自己的内部模型目录。

### 5. Windows Portable 的数据放在哪里

所有可写数据默认保存在 `BreastCancerExtractor.exe` 同级目录中，方便整体复制、备份和迁移：

```text
BreastCancerExtractor\
├─ BreastCancerExtractor.exe
├─ database\
├─ models\
│  ├─ llm\
│  └─ ollama\
├─ local_knowledge\
├─ logs\
├─ runtime\
│  └─ ollama\
└─ ...
```

患者数据位于：

```text
database\patients\<病案号>\
```

每名患者目录内保存患者数据库、manifest 和**已经完成脱敏的图片**。

### 6. 日常使用

以后只需要：

```text
打开 BreastCancerExtractor 文件夹
↓
双击 BreastCancerExtractor.exe
↓
浏览器自动打开
```

关闭启动窗口或按 `Ctrl+C` 会停止本次 Portable 主程序及由它启动的辅助服务。

### 7. Windows Portable 更新 / 迁移

更新程序前建议先备份：

```text
database\
models\
local_knowledge\
```

如果换电脑，可以复制整个 Portable 目录；也可以只迁移上述持久化目录到新的 Portable 版本。

详细的 Windows Portable 说明见：

- [`docs/WINDOWS_PORTABLE.md`](docs/WINDOWS_PORTABLE.md)
- [`docs/WINDOWS_NATIVE_MIGRATION.md`](docs/WINDOWS_NATIVE_MIGRATION.md)

---

## 二、Docker Compose

Docker 版适合希望继续使用标准容器环境、固定依赖，或已经在 Docker 版上稳定工作的用户。

### 1. 下载项目 ZIP

在 GitHub 仓库页面点击：

```text
Code → Download ZIP
```

完整解压，例如：

```text
D:\BreastCancerExtractor
```

不要直接在压缩包中运行，也不要把包含患者数据的项目目录放在会自动上传的网盘目录中。

### 2. 最简单的安装方式：双击 `install.bat`

进入项目根目录，双击：

```text
install.bat
```

安装脚本会检查：

- Windows 环境；
- CPU 虚拟化；
- WSL2；
- Docker Desktop；
- Docker Compose；
- 本机配置；
- 项目容器构建与启动状态。

如果缺少 WSL2 或 Docker Desktop，脚本会在获得用户确认后尝试完成相应安装步骤。

如果 Windows 要求重启：

```text
重启电脑
↓
再次双击 install.bat
```

安装和容器健康检查完成后，浏览器会打开：

```text
http://127.0.0.1:8765
```

> 自动安装器不会修改 BIOS/UEFI，不会绕过管理员授权，也不会自动替机构接受 Docker Desktop 的许可条款。

### 3. 手动准备 Docker 环境（仅在自动安装失败时看）

建议环境：

- 64 位 Windows 10 / 11；
- BIOS/UEFI 已开启 CPU virtualization；
- WSL2；
- Docker Desktop；
- Docker Compose。

管理员 PowerShell 安装 WSL2：

```powershell
wsl --install
```

重启后可检查：

```powershell
wsl --update
wsl --version
wsl --status
```

Docker Desktop 安装完成并启动后，普通 PowerShell 检查：

```powershell
docker version
docker compose version
```

本项目运行 Linux containers，建议使用 Docker Desktop 默认的 WSL2 backend。

### 4. 本机配置

如果 `install.bat` 已完成配置，可直接跳过本节。

手工部署时，可以从示例配置复制：

```powershell
Copy-Item .env.example .env
```

默认配置示例：

```dotenv
APP_PORT=8765
OFFLINE_MODE=true
OLLAMA_URL=http://ollama:11434
OCR_URL=http://ocr:8001
DEFAULT_LLM_MODEL=
MAX_SANITIZED_IMAGE_MB=25
```

首次使用建议不要随意修改 Ollama / OCR 容器内部地址。

### 5. 第一次启动

确保 Docker Desktop 已运行，然后双击：

```text
start.bat
```

也可以在项目目录执行：

```powershell
docker compose up -d --build
```

打开：

```text
http://127.0.0.1:8765
```

检查容器：

```powershell
docker compose ps
```

正常应看到主要服务：

```text
app
ocr
ollama
```

健康检查：

```text
http://127.0.0.1:8765/api/health
```

如果页面打不开：

```powershell
docker compose logs --tail 200 app
docker compose logs --tail 200 ocr
docker compose logs --tail 200 ollama
```

### 6. Docker 版安装 LLM

Docker 版默认使用 Compose 中独立的 Ollama 容器。

推荐模型仍为：

```text
Qwen3 8B
```

#### 方法 A：联网下载

在允许联网的准备阶段：

```powershell
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama list
```

下载完成后，可以在处理真实病历前断开互联网。

#### 方法 B：导入本地 GGUF

把 `.gguf` 放到：

```text
models\llm\
```

然后在 Web 端“模型管理”中扫描、导入并选择模型。

`models/llm/` 是用户自己维护的 GGUF 仓库；Ollama 导入后的运行模型保存在 Docker 命名卷 `ollama_models` 中，两者可能同时占用磁盘空间。

### 7. 可选：Docker 使用 Windows 宿主机 Ollama

Web 端支持在以下模式间切换：

- `Docker Ollama`：默认；
- `Windows 宿主机 Ollama`：适合希望直接使用 Windows 原生 Ollama / GPU 的情况。

使用宿主机模式前，需要确保 Windows Ollama 可以被 Docker Desktop 的 WSL 虚拟网络访问，并正确设置 Windows 防火墙。

如果只是正常使用，优先保持默认的 `Docker Ollama`，不需要折腾这一项。

### 8. Docker 日常启动与停止

日常启动：

```text
启动 Docker Desktop
↓
双击 start.bat
↓
浏览器打开 http://127.0.0.1:8765
```

普通停止：

```text
stop.bat
```

或者：

```powershell
docker compose stop
```

如果希望连 Docker Desktop、WSL2 和 `vmmem` 一起停止，可以使用：

```text
stop-all.bat
```

`stop-all.bat` 会影响同机其他 WSL 任务；如果电脑上还有其他 WSL 工作，只使用普通 `stop.bat`。

> **不要随意执行 `docker compose down -v`。** `-v` 会删除 Ollama 模型卷。

### 9. Docker 更新

更新代码前先备份持久化数据。

更新源码后执行：

```powershell
docker compose up -d --build
```

程序升级、知识库升级和 LLM 模型升级彼此独立。不要因为更新程序而删除 `database/`、`models/` 或 `ollama_models`。

---

# 基本使用流程

部署完成后，两种运行方式使用的是同一套 Web 界面和核心业务逻辑。

典型流程：

```text
新建患者
↓
一次导入多张病历图片
↓
从上到下依次选择文档类型
↓
裁剪 / 旋转
↓
实心涂抹患者身份信息
↓
按需框选一个或多个 ROI
↓
确认脱敏图片
↓
OCR 与 AI 在后台依次处理
↓
人工审核 / 修改
↓
人工确认 VERIFIED
↓
患者级数据预览与导出
```

首次正式使用前，建议先使用**完全虚构、无真实身份信息的模拟病历图片**测试整个流程。

---

# 当前已实现

- 患者科研编号管理；
- 一次选择多张图片或患者文件夹；
- 浏览器端裁剪、旋转、实心遮盖、撤销和多个 ROI；
- 确认一张图片后自动进入下一张，OCR / AI 在后台队列继续处理；
- 原图 / 增强图切换，增强仅用于本地非生成式图像处理；
- PaddleOCR 本地识别并保存文字及坐标；
- Ollama 本地模型查询、GGUF 扫描与导入；
- 按乳腺癌字段字典进行结构化 AI 抽取；
- AI 原值、当前值、人工修改、人工确认分离保存；
- `UNPROCESSED → AI_PROCESSED / REVIEW_REQUIRED → VERIFIED` 状态；
- 已保存脱敏图片可重新 OCR / AI 处理；
- 患者级宽表预览；
- Excel 兼容 UTF-8 CSV 导出；
- Docker Compose 与 Windows Native 共用核心代码。

仍在继续完善：

- 更完整的 AJCC 确定性分期规则；
- OCR 文字框与字段 Evidence 的精确回链；
- 原生 XLSX 导出；
- 可直接交付医院的完整离线发行包。

---

# 数据、备份与跨电脑迁移

## 患者目录

患者数据采用可移动目录：

```text
database\
├─ catalog.sqlite
├─ instance.json
└─ patients\
   └─ 1234567\
      ├─ patient.sqlite
      ├─ manifest.json
      └─ sanitized\
```

不同电脑处理不同患者时，可以在软件停止后复制完整患者目录到另一台电脑，再在首页使用“扫描患者目录”。

如果目标电脑已经有同一病案号，不要直接覆盖；应按照软件提供的冲突处理流程决定保留、替换或合并审核。

## 建议备份

至少备份：

```text
database\
local_knowledge\
models\llm\
.env                  # Docker 使用时
```

Windows Portable 建议直接备份：

```text
database\
models\
local_knowledge\
```

备份 SQLite 前最好先停止程序，避免复制正在写入的数据库。

未经安全评估，不要把患者数据库或脱敏图片自动同步到普通网盘。

---

# 隐私设计

本项目最重要的边界是：

> **未经脱敏的原始图片不作为患者长期数据保存，也不发送给后端 OCR / LLM。**

处理流程：

```text
用户本地原图
  ↓ 浏览器临时读取
裁剪 + 实心遮盖 + ROI
  ↓
重新编码为 PNG
  ↓
本地后端再次解码 / 编码
  ↓
database/patients/<patient_code>/sanitized/
  ↓
OCR
  ↓
本地 LLM
  ↓
人工审核
```

原始文件名也不自动写入患者数据库，避免姓名或住院号从文件名泄露。

实心遮盖是对输出像素的真实修改，不是单纯在网页上覆盖一个可撤销的视觉图层。

需要注意：浏览器崩溃转储、系统交换文件、恶意软件、屏幕录制等属于操作系统层风险，无法仅由本 Web 应用绝对消除。医院环境仍建议配合受控账户、磁盘加密、终端安全策略和断网使用。

`OFFLINE_MODE=true` 时，项目按照本地 / 容器内部通信模式工作。当前代码不依赖 CDN、第三方字体、遥测或外部错误上报。

---

# AI、OCR 与人工审核

项目原则：

```text
OCR 负责认字
↓
LLM 负责理解和结构化
↓
规则系统负责检查
↓
人工负责最终确认
```

AI 处理后的字段可以人工修改；修改前后的值会分别保留。

只有人工确认后的字段进入：

```text
VERIFIED
```

AI 不会自行把结果标记为人工已确认。

每次 AI 处理会记录相应模型信息，后续更换模型不会自动修改已经保存的历史结果。

---

# 本地模型管理

推荐起始模型：

```text
Qwen3 8B
```

模型并非固定依赖。

用户可以：

- 使用 Ollama 已安装模型；
- 在 `models/llm/` 中自行维护 GGUF；
- 在 Web 模型管理页面导入、测试和切换模型；
- 后续升级为其他 Ollama 兼容模型。

模型升级和程序升级互不绑定。

---

# 知识库

公开知识库位于：

```text
knowledge\
```

本地授权、机构内部或不适合公开提交的资料放入：

```text
local_knowledge\
```

字段定义及需要根据医院实际口径补充的内容见：

```text
knowledge/manual/知识库手册.md
```

机器可读来源登记：

```text
knowledge/references/sources.yaml
```

知识库主要参考乳腺癌相关的中国临床指南、AJCC、WHO/IARC、CAP、ASCO，以及 NCIt / LOINC / RxNorm 等标准术语体系。

原则是：

- 病历明确记录优先于模型推断；
- 标准用于结构化、校验和辅助推断，不用于覆盖原始病历；
- 受版权或许可限制的全文内容不直接提交到公开仓库；
- 本地授权资料与公开仓库知识库分离。

<details>
<summary><strong>展开：主要知识来源</strong></summary>

- 国家卫生健康委员会《乳腺癌诊疗指南》；
- 中国抗癌协会乳腺癌诊治指南与规范；
- AJCC Cancer Staging System；
- WHO Classification of Tumours — Breast Tumours；
- CAP Breast Cancer Protocols；
- ASCO / CAP 乳腺癌生物标志物相关指南；
- NCI / NCIt；
- LOINC、RxNorm、ATC/DDD 等术语资源。

具体版本、用途、访问方式和许可边界以 `knowledge/references/sources.yaml` 为准。

</details>

---

# 医院完全离线版

当前仓库已经具备本地运行基础，但**尚未正式发布可直接交付医院的完整离线安装包**。

不要认为“把 GitHub ZIP 拷贝到断网电脑”就等于完成医院离线部署，因为目标电脑还可能缺少：

- Windows / WSL / Docker 运行环境（Docker 版）；
- Ollama runtime（Portable 未内置时）；
- OCR 模型缓存；
- LLM 模型权重。

计划中的医院离线发行将额外准备所需运行时、镜像 / 模型及离线说明，并在真正无缓存、无互联网的电脑上完成验收后再发布。

真实患者资料永远不属于任何发布包。

---

# 本地开发

项目 Python 环境使用 `uv` 管理。

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

Windows Native 开发入口：

```text
start-native.bat
```

测试：

```powershell
uv run pytest
uv run ruff check .
```

构建 Windows Portable：

```text
build-portable.bat
```

输出：

```text
dist\BreastCancerExtractor\
```

---

# Git 安全

`.gitignore` 已排除患者数据、数据库、模型、日志、GGUF、离线镜像和本机配置等内容。

提交前仍建议检查：

```powershell
git status --short
```

确认不存在：

- 病历图片；
- 患者身份信息；
- 患者数据库；
- 本地模型权重；
- 机构内部知识库；
- 其他不应公开的数据。
