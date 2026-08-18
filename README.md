# Breast Cancer Extractor

完全本地运行、带证据定位与人工审核留痕的乳腺癌科研病历结构化工具。

> 当前项目定位为**科研数据抽取工具**，不用于临床诊断或治疗决策。

---

# Windows 极简版

只想先把程序跑起来，按下面做即可。

1. 在 GitHub 页面点击：

```text
Code → Download ZIP
```

2. 完整解压 ZIP，例如：

```text
D:\BreastCancerExtractor
```

3. 如果电脑还没有 `uv`，先安装 `uv`。

4. 如果电脑还没有 Ollama，先安装 Ollama，然后执行：

```powershell
ollama pull qwen3:8b
```

5. 回到项目根目录，双击：

```text
build-portable.bat
```

6. 构建完成后进入：

```text
dist\BreastCancerExtractor\
```

7. 双击：

```text
BreastCancerExtractor.exe
```

8. 浏览器打开后即可使用：

```text
http://127.0.0.1:8765
```

以后再次使用，只需要进入：

```text
dist\BreastCancerExtractor\
```

双击：

```text
BreastCancerExtractor.exe
```

> 必须保留整个 `dist\BreastCancerExtractor\` 文件夹，不要只复制单独的 exe。

需要换模型时，把 GGUF 放入：

```text
models\llm\
```

然后在软件的模型管理页面导入并选择即可。

---

# 部署详细说明

目前支持两种运行方式：

1. **Windows Native / Portable：推荐普通 Windows 用户使用**
2. **Docker Compose：适合希望固定运行环境或继续使用现有 Docker 工作流的用户**

两种方式都从 GitHub 仓库 ZIP 开始。

---

## 一、Windows Native / Portable（推荐）

Windows 版本使用 **PyInstaller onedir**。构建完成后，目标电脑运行 Portable 目录时不需要 Python、uv、Conda 或 Docker。

### 1. 下载项目 ZIP

在 GitHub 仓库页面点击：

```text
Code → Download ZIP
```

下载完成后完整解压，例如：

```text
D:\BreastCancerExtractor
```

不要直接在 ZIP 压缩包预览窗口内运行脚本，也不建议把项目放入 OneDrive、网盘或其他会自动上传的目录。

### 2. 首次从源码构建 Windows Portable

构建电脑需要：

- 64 位 Windows；
- `uv`；
- 正常的显卡驱动；
- 如希望 Portable 自带 Ollama runtime，构建电脑需要存在可用的 `ollama.exe`。

在项目根目录双击：

```text
build-portable.bat
```

构建结果位于：

```text
dist\BreastCancerExtractor\
```

### 3. 运行 Windows Portable

进入：

```text
dist\BreastCancerExtractor\
```

双击：

```text
BreastCancerExtractor.exe
```

必须复制和保留整个目录，不要只复制 exe。

程序会优先检查：

```text
127.0.0.1:11434
```

如果 Windows 已有 Ollama，则直接使用；否则会尝试启动 Portable 中的：

```text
runtime\ollama\ollama.exe
```

随后启动本地 OCR、本地 Web 服务并打开：

```text
http://127.0.0.1:8765
```

如果 Ollama 暂时不可用，图片整理、脱敏、ROI 等非 LLM 功能仍可使用。

### 4. LLM

推荐起始模型：

```text
Qwen3 8B
```

联网准备：

```powershell
ollama pull qwen3:8b
ollama list
```

也可以把合法获得的 GGUF 放入：

```text
models\llm\
```

然后在 Web 端模型管理中扫描、导入并选择模型。

不要直接修改 Ollama 内部模型目录。

### 5. Windows Portable 数据目录

所有可写数据默认保存在 `BreastCancerExtractor.exe` 同级目录中：

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

每名患者目录保存患者数据库、manifest 和已经完成脱敏的图片。

### 6. Windows 更新 / 迁移

更新程序或换电脑前建议备份：

```text
database\
models\
local_knowledge\
```

详细说明：

- [`docs/WINDOWS_PORTABLE.md`](docs/WINDOWS_PORTABLE.md)
- [`docs/WINDOWS_NATIVE_MIGRATION.md`](docs/WINDOWS_NATIVE_MIGRATION.md)

---

## 二、Docker Compose

### 1. 下载项目 ZIP

在 GitHub 仓库页面点击：

```text
Code → Download ZIP
```

完整解压，例如：

```text
D:\BreastCancerExtractor
```

### 2. 安装

进入项目根目录，双击：

```text
install.bat
```

如果 Windows 要求重启：

```text
重启电脑
↓
再次双击 install.bat
```

安装和健康检查完成后打开：

```text
http://127.0.0.1:8765
```

### 3. 日常启动

以后使用：

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

如果希望同时退出 Docker Desktop、关闭 WSL2 并释放 `vmmem`：

```text
stop-all.bat
```

如果电脑上还有其他 WSL 任务，不要使用 `stop-all.bat`。

### 4. 手动 Docker 启动

如果需要手工操作：

```powershell
docker compose up -d --build
```

检查：

```powershell
docker compose ps
```

正常应看到：

```text
app
ocr
ollama
```

健康检查：

```text
http://127.0.0.1:8765/api/health
```

日志：

```powershell
docker compose logs --tail 200 app
docker compose logs --tail 200 ocr
docker compose logs --tail 200 ollama
```

### 5. Docker 安装模型

联网准备：

```powershell
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama list
```

离线 GGUF：

```text
models\llm\
```

然后在 Web 端模型管理中扫描、导入并选择模型。

Docker Ollama 的运行模型保存在命名卷 `ollama_models` 中。

> 不要随意执行 `docker compose down -v`，`-v` 会删除 Ollama 模型卷。

### 6. Docker 更新

更新源码后：

```powershell
docker compose up -d --build
```

不要因为更新程序而删除：

```text
database\
models\
ollama_models
```

---

# 基本使用流程

两种部署方式使用同一套 Web 界面和核心业务逻辑。

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

首次正式使用前，建议先用完全虚构、无真实身份信息的模拟病历图片测试整个流程。

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

如果目标电脑已经有同一病案号，不要直接覆盖，应按照软件提供的冲突处理流程决定保留、替换或合并审核。

建议至少备份：

```text
database\
local_knowledge\
models\llm\
```

Docker 用户同时保留本机 `.env`。

备份 SQLite 前最好先停止程序，避免复制正在写入的数据库。

未经安全评估，不要把患者数据库或脱敏图片自动同步到普通网盘。

---

# 隐私设计

本项目最重要的边界是：

> **未经脱敏的原始图片不作为患者长期数据保存，也不发送给后端 OCR / LLM。**

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

原始文件名不自动写入患者数据库，避免姓名或住院号从文件名泄露。

实心遮盖会真实修改输出像素，不是单纯的网页视觉覆盖。

医院环境仍建议配合受控账户、磁盘加密、终端安全策略和断网使用。

当前代码不依赖 CDN、第三方字体、遥测或外部错误上报。

---

# AI、OCR 与人工审核

```text
OCR 负责认字
↓
LLM 负责理解和结构化
↓
规则系统负责检查
↓
人工负责最终确认
```

AI 处理后的字段可以人工修改，修改前后的值分别保留。

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

模型不是固定依赖。

用户可以：

- 使用 Ollama 已安装模型；
- 在 `models/llm/` 中自行维护 GGUF；
- 在 Web 模型管理页面导入、测试和切换模型；
- 后续升级为其他 Ollama 兼容模型。

模型升级和程序升级互不绑定。

---

# 知识库

公开知识库：

```text
knowledge\
```

本地授权、机构内部或不适合公开提交的资料：

```text
local_knowledge\
```

字段定义及需要根据医院实际口径补充的内容：

```text
knowledge/manual/知识库手册.md
```

机器可读来源登记：

```text
knowledge/references/sources.yaml
```

主要参考乳腺癌相关的中国临床指南、AJCC、WHO/IARC、CAP、ASCO，以及 NCIt / LOINC / RxNorm 等标准术语体系。

原则：

- 病历明确记录优先于模型推断；
- 标准用于结构化、校验和辅助推断，不覆盖原始病历；
- 受版权或许可限制的全文内容不直接提交到公开仓库；
- 本地授权资料与公开知识库分离。

---

# 医院完全离线版

当前仓库具备本地运行基础，但尚未正式发布可直接交付医院的完整离线安装包。

医院离线发行还需要准备和验证：

- 所需 Windows / Docker 运行环境（Docker 版）；
- Ollama runtime；
- OCR 模型；
- LLM 模型权重；
- 离线安装说明；
- 真正无缓存、无互联网电脑上的完整验收。

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

提交前建议检查：

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
