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
- PaddleOCR 独立本地服务，脱敏 PNG 可一键 OCR，文字与坐标结果保存到 SQLite；
- Ollama 已安装模型查询、本地 `models/llm/*.gguf` 扫描与导入，以及按字段字典的结构化 AI 抽取；
- 确认脱敏并保存后自动依次执行 OCR 和 AI 抽取；任一阶段失败时保留脱敏图片及此前已完成的结果；
- 支持一次选择多张图片或患者文件夹；确认一张后自动打开下一张，OCR 与 AI 在页面下方后台队列中顺序运行，不锁定裁剪和 ROI 编辑区；
- 夜间模式可手动切换，默认跟随 Windows 系统主题；
- 图片编辑区提供“原图 / 增强图”开关，选择在图片之间及页面刷新后保持；增强图仅在浏览器内存中通过非生成式重采样、屏纹抑制和对比度调整生成，保存时记录增强模式与版本；
- 裁剪框首次拖动建立后，可通过四条边和八个控制点继续微调；
- ROI首次框选后同样可选中并拖动四条边或八个控制点微调；ROI类型随文档类型切换为对应字段；
- 每张已保存脱敏图片可单独删除；同步删除其 ROI、OCR 和 AI 字段，保留删除审计记录；
- “已保存脱敏图片”支持一键OCR尚未识别的图片，以及一键对已完成OCR但尚未AI处理的图片进行结构化提取；批量任务进入后台队列且不重复覆盖已有结果；
- Docker Compose 本地部署，OCR 与 Ollama 均不向宿主机公开端口；
- 158 项队列字段的机器可读数据字典、乳腺癌病理 Schema、IHC 规则和 Prompt；
- TNM“病历记录优先、缺失时推断”的策略，区分 c/p/yc/yp 并要求推断结果人工复核；
- 公开知识库与 `local_knowledge/` 本地授权/内部资料分离。

尚未完成的模块包括完整 AJCC 确定性分期规则引擎、证据文字框精确回链、原生 XLSX 导出和离线版镜像打包。当前已支持患者级批量处理队列、全部患者宽表预览及 Excel 兼容 UTF-8 CSV 导出。AI 可抽取原文 TNM；原文没有 TNM 时可按事实推断，但推断结果强制进入人工复核。

## Windows Native / Portable

项目现在由同一套核心代码支持 Docker 与 Windows Native。Windows 发布形式为 **PyInstaller onedir**，最终用户不需要安装 Python、uv、Conda 或 Docker：

```text
下载完整的 BreastCancerExtractor 文件夹
↓
解压
↓
双击 BreastCancerExtractor.exe
```

Portable 会自动启动随包提供的 PaddleOCR；先连接 `127.0.0.1:11434` 上已有的 Ollama，未检测到服务时再尝试启动 `runtime/ollama/ollama.exe`。模型仍由 Web 模型管理页面选择，不在核心业务代码中写死。数据库、脱敏图片、模型和本地知识库均保存在 exe 同级子目录。

开发者可双击 `start-native.bat` 在 Windows Python 环境直接运行。生成 Portable 包时双击 `build-portable.bat`，输出位于 `dist/BreastCancerExtractor/`。必须复制整个目录，不能只复制 exe。详细说明见 [`docs/WINDOWS_PORTABLE.md`](docs/WINDOWS_PORTABLE.md)，迁移边界和验证记录见 [`docs/WINDOWS_NATIVE_MIGRATION.md`](docs/WINDOWS_NATIVE_MIGRATION.md)。

字段定义和仍需补充的医院口径详见 `knowledge/manual/知识库手册.md`。

## 隐私模型

```text
用户本地原图
  ↓ 仅浏览器内存
裁剪 + 实心遮盖 + ROI
  ↓ Canvas 重新编码 PNG（删除 EXIF）
本地 FastAPI
  ↓ 再次解码/编码
database/patients/<patient_code>/sanitized/<uuid>.png
```

注意：浏览器崩溃转储、操作系统交换文件、屏幕录制等属于操作系统层面的风险，无法仅靠 Web 应用绝对消除。医院部署仍应配合加密磁盘、受控账户和禁用外网策略。

`OFFLINE_MODE=true` 时程序只允许连接 Compose 内的 `ollama`/`ocr`、Windows 宿主机桥接地址、`localhost` 或回环地址，同时前端 CSP 将网络请求限制到当前本地站点。当前代码没有遥测、CDN、第三方字体或外部错误上报。

## 在一台新 Windows 电脑上安装

本节是 Docker 方式的从零安装说明。若使用已经构建好的 Windows Portable 发行目录，只需完整解压并双击 `BreastCancerExtractor.exe`，不执行本节的 Docker/WSL 安装步骤。

### 最简单的安装方式：双击一个文件

1. 在 GitHub Desktop 克隆仓库，或下载 ZIP 后完整解压；
2. 双击项目根目录的 **`install.bat`**；
3. 安装器会自动检查 Windows、CPU 虚拟化、磁盘空间、WSL2、Docker Desktop、Docker Compose 和本机配置；WSL2 缺失时自动安装，但不会在每次启动时强制联网更新；
4. WSL 或 Docker Desktop 缺失时，安装器会在征得确认后执行安装；如果 Windows 要求重启，重启后再次双击 `install.bat`；
5. 容器启动并通过健康检查后，安装器会自动打开 <http://127.0.0.1:8765>；
6. 以后日常使用只需双击 **`start.bat`**，它会自动启动 Docker Desktop、等待 Docker Engine并打开软件；双击 `stop.bat` 只停止本项目，双击 `stop-all.bat` 可退出 Docker Desktop、关闭 WSL 并释放 `vmmem`。`install.bat` 和 `stop-all.bat` 显示结果后均等待5秒自动关闭，不要求按任意键。

`install.bat` 会在首次安装或需要更新程序时构建 Docker 镜像并安装依赖；构建结果会保存在 Docker Desktop 中。日常的 `start.bat` 只执行 `docker compose up -d`，直接复用已有镜像，不会重新安装 Python、PaddleOCR 或系统软件包。

自动安装器不会自行修改 BIOS/UEFI，不会绕过 Windows 管理员授权，不会替机构接受 Docker 许可，也不会擅自下载体积较大的 LLM 模型。遇到这些情况时，它会停在明确的提示处。下面的手动步骤主要用于排查自动安装失败。

### 1. 手动检查安装条件

建议准备：

- 64 位 Windows 11，或仍受 Docker 支持的 64 位 Windows 10；
- BIOS/UEFI 已启用 CPU virtualization；可在“任务管理器 → 性能 → CPU”确认“虚拟化：已启用”；
- 内存最低 8 GB；本项目实际使用建议 32 GB 以上，计划运行本地视觉/语言模型建议 64 GB；
- 系统盘和项目盘预留足够空间。Docker 镜像、Ollama 运行模型及手工保留的 GGUF 可能重复占用空间，建议至少预留 50 GB，实际按模型数量增加；
- 新电脑第一次安装 WSL、Docker 镜像及模型时需要互联网；处理真实病历时可断网；
- 医院或大型机构使用 Docker Desktop 前，需要由信息部门核对 [Docker Desktop 许可条款与适用订阅](https://docs.docker.com/desktop/setup/install/windows-install/)。

Docker 当前要求 WSL 2.1.5 或更高版本，并列出了受支持的 Windows 版本和硬件要求；安装前以 [Docker Desktop for Windows 官方页面](https://docs.docker.com/desktop/setup/install/windows-install/) 的实时说明为准。

### 2. 手动安装或更新 WSL2

1. 在开始菜单搜索 `PowerShell`；
2. 右键选择“以管理员身份运行”；
3. 执行：

```powershell
wsl --install
```

4. 命令完成后重启电脑；
5. 重启后再次以管理员身份打开 PowerShell，执行：

```powershell
wsl --update
wsl --version
wsl --status
```

Microsoft 的标准流程是管理员 PowerShell 执行 `wsl --install` 后重启，详见 [Microsoft WSL 安装说明](https://learn.microsoft.com/windows/wsl/install)。如果电脑已经安装 WSL，重点执行 `wsl --update`；如果命令提示虚拟化未启用，需要先进入 BIOS/UEFI 开启 Intel VT-x/AMD-V，再回到本步骤。

### 3. 手动安装 Docker Desktop

1. 从 [Docker Desktop for Windows 官方页面](https://docs.docker.com/desktop/setup/install/windows-install/) 下载安装程序；
2. 运行安装程序，使用默认的 WSL 2 backend；
3. 安装结束后从开始菜单启动 Docker Desktop；
4. 等待左下角或主界面显示 Docker Engine 正在运行；
5. 在 Docker Desktop 的 `Settings → General` 中确认使用 WSL 2 based engine。新版在兼容电脑上通常默认开启；
6. 打开普通 PowerShell，验证：

```powershell
docker version
docker compose version
```

两个命令都应返回版本信息。若只显示客户端信息、提示无法连接 daemon，通常是 Docker Desktop 尚未启动。WSL2 后端的官方设置方法见 [Docker WSL2 backend](https://docs.docker.com/desktop/features/wsl/)。

> 本项目运行 Linux 容器，不需要切换到 Windows containers。Docker Desktop 不要求登录账号才能运行本地容器；但离线状态下依赖联网的 Docker 功能不可用，参见 [Docker Desktop offline FAQ](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/)。

### 4. 获取 GitHub 轻量版项目

可以任选一种方式。

方法 A——GitHub Desktop：

1. 在 GitHub Desktop 中选择 `File → Clone repository`；
2. 选择 `BreastCancerExtractor` 仓库；
3. 建议克隆到空间充足、权限正常的目录，例如 `D:\Documents\GitHub\BreastCancerExtractor`；
4. 点击 `Clone`。

方法 B——下载 ZIP：

1. 在 GitHub 仓库页面选择 `Code → Download ZIP`；
2. 下载后完整解压，不要直接在压缩包预览窗口运行；
3. 建议解压到 `D:\BreastCancerExtractor` 等固定目录。

不要把项目放在会自动上传云端的 OneDrive、网盘或公共共享目录中。代码目录可以迁移，但 `database/` 和 `workspace/` 建立后不可随意删除。

### 5. 创建本机配置

打开项目目录，在文件资源管理器地址栏输入 `powershell` 并回车，然后执行：

```powershell
Copy-Item .env.example .env
```

首次安装建议保持 `.env` 默认内容：

```dotenv
APP_PORT=8765
OFFLINE_MODE=true
OLLAMA_URL=http://ollama:11434
OCR_URL=http://ocr:8001
DEFAULT_LLM_MODEL=
MAX_SANITIZED_IMAGE_MB=25
```

含义：

- `APP_PORT`：浏览器访问端口；首次安装先不要修改；
- `OFFLINE_MODE=true`：应用只允许使用本地/容器内 Ollama；
- `OLLAMA_URL`：Compose 内部 Ollama 地址，不要改成互联网地址；
- `OCR_URL`：Compose 内部 OCR 地址，默认保持 `http://ocr:8001`；
- `DEFAULT_LLM_MODEL`：模型导入后再填写其 Ollama 名称；
- `MAX_SANITIZED_IMAGE_MB`：单张脱敏 PNG 的大小上限。

`.env`、患者数据和模型均已被 `.gitignore` 排除，不得手工提交到 GitHub。

### 6. 第一次启动

确保 Docker Desktop 正在运行，然后双击项目根目录的 `start.bat`。也可以在项目目录的 PowerShell 中执行：

```powershell
docker compose up -d --build
```

第一次启动会下载基础镜像并构建应用，所需时间取决于网络和电脑性能。命令完成后打开：

<http://127.0.0.1:8765>

检查容器：

```powershell
docker compose ps
```

应看到 `app`、`ocr` 和 `ollama` 三个服务处于运行状态。再访问健康检查：

<http://127.0.0.1:8765/api/health>

正常情况下会看到包含以下内容的 JSON：

```json
{
  "status": "ok",
  "offline_mode": true,
  "external_api": "disabled",
  "ollama": {"available": true, "models": 0},
  "ocr": {"available": true, "engine": "PaddleOCR"}
}
```

如果页面打不开，查看日志：

```powershell
docker compose logs --tail 200 app
docker compose logs --tail 200 ollama
docker compose logs --tail 200 ocr
```

### 7. 安装本地 LLM 模型

软件可以在没有模型时启动，但 LLM 抽取功能需要 Ollama 模型。模型不要放入 Git，也不要直接修改 Docker 的 `ollama_models` 卷。

> Windows 已安装 Ollama 不等于 Docker 内的 Ollama 已有模型。默认版使用 Compose 中的独立 Ollama 容器，Windows 用户目录下的模型与 Docker 命名卷相互隔离。这样离线版更容易复制和复现。软件顶部会分别显示 Ollama、模型数量和 OCR 的真实连接状态。

Web端“本地模型管理”现在可以在以下两个固定模式间切换：

- `Docker Ollama`：默认模式，模型保存在Docker命名卷；
- `Windows宿主机 Ollama（AMD GPU）`：应用通过 `http://host.docker.internal:11434` 连接Windows Ollama。

切换按钮会先测试目标服务，连接成功后才保存设置。选择结果保存在 `database/runtime_config.json`，容器升级后仍保留。为维持离线边界，Web端不接受任意URL。

使用宿主机模式前，需要先启动Windows Ollama，并使其允许Docker Desktop的WSL虚拟网络访问。可在Windows用户环境变量中设置 `OLLAMA_HOST=0.0.0.0:11434`，完全退出并重新启动Ollama；Windows防火墙应只允许受信任的本机/WSL虚拟网络访问11434，不要向公共网络开放。然后在Web端选择“Windows宿主机 Ollama（AMD GPU）”，点击“测试连接并使用”。顶部状态会显示当前运行位置以及模型运行后报告的 `CPU/GPU` 状态。

#### 方式 A：联网下载 Ollama 模型

在尚未导入真实病历、允许联网的准备阶段执行：

```powershell
docker compose exec ollama ollama pull <模型名称>
docker compose exec ollama ollama list
```

把 `<模型名称>` 替换为实际选择的 Ollama 模型标签。模型选择尚未在本 MVP 中锁定；正式使用前应以脱敏金标准样本比较准确率、JSON 合法率、漏提取和幻觉情况。

#### 方式 B：导入本地 GGUF，适合离线维护

1. 将合法获得的单文件 `.gguf` 复制到：

```text
models/llm/
```

2. 查看程序是否扫描到文件：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/models/local-files
```

3. 导入 Ollama；以下示例把文件名和模型名替换为自己的值：

```powershell
$body = @{
  filename = "your-model.gguf"
  model_name = "breast-extractor-model"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/api/models/import `
  -ContentType "application/json" `
  -Body $body
```

4. 检查已安装模型：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/models/installed
```

5. 在 `.env` 中设置：

```dotenv
DEFAULT_LLM_MODEL=breast-extractor-model
```

6. 重建并重启应用以读取新配置：

```powershell
docker compose up -d --build
```

Ollama 导入后的运行模型保存在 Docker 命名卷 `ollama_models`；`models/llm/` 是用户自行维护的原始 GGUF 仓库。二者可能同时占用磁盘。切换模型不会更改已经保存的 AI 结果或人工确认记录。

本地 GGUF 导入采用当前 Ollama API：程序先计算文件 SHA256，通过 `/api/blobs/:digest` 注册模型文件，再使用 `/api/create` 的 `files` 字段创建模型。重复导入同一文件时会复用已有 blob。参考：[Ollama 导入 GGUF](https://docs.ollama.com/import)、[Ollama Create API](https://docs.ollama.com/api/create)。

### 8. 首次功能验证

正式使用前按以下顺序验证：

1. 使用一张完全虚构、无真实身份信息的模拟病理报告图片；
2. 新建测试患者编号；
3. 在浏览器中裁剪；
4. 对模拟姓名和编号使用实心遮盖；
5. 框选一个或多个 ROI；
6. 点击“确认脱敏并保存”，该张原图被释放并自动打开下一张；
7. OCR 和 AI 自动进入页面下方后台队列，可继续处理后续图片，无需等待；
8. 检查项目目录，未经脱敏原图不应出现在 `workspace/`；
9. 确认上述流程无误后，再制定真实病历的受控测试方案。

保存脱敏图后，系统会自动顺序执行 OCR 和 AI 抽取。若某一步失败，已保存的脱敏图片以及此前已完成的 OCR 结果不会丢失。AI结果进入字段审核区，人工可修改并确认。首页“数据预览”可按问卷顺序查看全部患者宽表，并可切换“全部当前结果”或“仅人工已确认”，导出带 UTF-8 BOM 的 Excel 兼容 CSV；原生 XLSX 导出尚未完成。

### 9. 日常启动与停止

日常启动：

1. 启动 Docker Desktop；
2. 双击 `start.bat`；
3. 浏览器打开 <http://127.0.0.1:8765>。

日常停止可双击 `stop.bat`，或执行：

```powershell
docker compose stop
```

停止容器不会删除数据库、脱敏图片或模型。不要使用 `docker compose down -v`，因为 `-v` 会删除 Ollama 模型卷。

如果希望同时退出 Docker Desktop、关闭全部 WSL2 虚拟机并释放 `vmmem`，双击：

```text
stop-all.bat
```

脚本会先警告并要求输入 `Y`。它会停止本项目容器、正常停止 Docker Desktop，然后执行 `wsl --shutdown`。这不会删除镜像、数据库、脱敏图片或 Ollama 模型卷，但会同时中断该电脑上其他正在运行的 WSL 发行版；有其他 WSL 工作时只使用普通 `stop.bat`。

### 10. 更新 GitHub 轻量版

更新前先关闭系统并备份下述持久化内容。使用 GitHub Desktop 时先查看本地修改，确认没有把患者数据加入版本控制，然后执行 `Fetch origin/Pull origin`。更新代码后运行：

```powershell
docker compose up -d --build
```

程序升级、知识库升级和模型升级是三件独立的事情。不要因为更新代码而删除 `database/`、`models/` 或 Docker 的 `ollama_models` 卷。

### 11. 数据备份与迁移

至少备份：

```text
database/        可重建目录库，以及每名患者完整的 patient.sqlite、脱敏图片和审核记录
local_knowledge/ 本机授权资料和医院内部字典
models/llm/      用户保留的原始 GGUF（如需）
.env             本机配置
```

备份前先运行 `stop.bat`，避免复制正在写入的 SQLite 文件。未经安全评估，不要把备份放到普通网盘。Ollama 已导入模型位于 Docker 卷中；如果原始 GGUF 仍在 `models/llm/`，新电脑可重新导入，否则需要另行导出/备份 Docker 卷。

患者数据采用可移动目录：

```text
database/
├─ catalog.sqlite
├─ instance.json
└─ patients/
   └─ 1234567/
      ├─ patient.sqlite
      ├─ manifest.json
      └─ sanitized/
```

不同电脑处理不同患者时，停止软件后复制完整病案号目录到主电脑的 `database/patients/`，再在首页点击“扫描患者目录”。如果目标电脑已经有同一病案号，复制前将外来目录改名为 `病案号-来源电脑`（不要覆盖本机同名目录）；系统读取 `manifest.json` 中的真实病案号，并提供“保留本机”“使用外部”“合并并审核冲突”。处理后的外来目录会保留并标记为已处理，不会反复出现在扫描列表，也不会静默覆盖两边的人工确认值。旧版 `extractor.db` 和 `workspace/patients/` 首次启动时会复制迁移到新结构，旧文件保留用于回滚，确认新目录可用后再人工归档。

### 12. 离线版安装说明

**当前仓库尚未发布可直接交付医院的离线版安装包。** 在离线版正式发布前，不要只复制 GitHub ZIP 到断网电脑，因为 WSL、Docker Desktop、容器镜像和模型仍可能需要在线获取。

计划中的离线版将包含或配套提供：

```text
BreastCancerExtractor-Offline-<version>/
├─ docker-images/          已导出的 app 与 Ollama 镜像 tar
├─ models/llm/             许可允许分发的推荐模型，或独立模型介质
├─ knowledge/              公开知识库
├─ compose.yaml
├─ .env.example
├─ start-offline.bat
├─ stop.bat
└─ README-离线安装.md
```

离线电脑仍需预先安装兼容的 WSL2 和 Docker 运行环境。医院信息部门还需要核对 Docker Desktop 许可、终端安全策略、磁盘加密、账户权限和移动介质流程。正式离线包应在一台从未缓存过本项目镜像的断网电脑上完成验收后再发布。

### 13. 卸载或彻底移除

如果只是暂时停用，执行 `stop.bat` 即可，不需要卸载。

若要卸载应用但保留数据：

1. 执行 `stop.bat`；
2. 备份 `database/`、`local_knowledge/`、`.env` 和需要保留的 GGUF；
3. 执行 `docker compose down`；
4. 可以删除代码目录，但不要删除尚未备份的持久化数据。

若确认要永久删除应用及 Ollama 模型卷，可在项目目录执行：

```powershell
docker compose down -v
```

这是破坏性操作：`-v` 会删除本项目的 Ollama 模型卷，通常无法恢复；项目目录中的 `database/` 是 bind mount，仍需在确认备份和目标路径无误后由用户单独删除。本项目不会自动删除患者数据。

只有在该电脑不再运行任何其他容器应用时，才考虑通过 Windows“设置 → 应用”卸载 Docker Desktop；卸载 Docker Desktop 可能影响同机其他 Docker 项目。WSL 也可能被其他软件使用，不应为了卸载本项目而直接删除 WSL。

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
- 离线版：额外携带 `docker save` 导出的镜像 tar、已核对许可的 OCR/LLM 模型和离线安装说明。真实患者资料永远不属于发布物。

## 知识库来源与参考文献

以下来源已于 **2026-08-18** 核对。机器可读登记表位于 `knowledge/references/sources.yaml`；其中记录来源 ID、版本、用途、访问方式和许可边界。项目采用以下原则：

- 病历明确记载优先于模型推断；标准用于结构化、校验和缺失项推断，不用于覆盖原始记录；
- 中国临床口径优先参考国家卫生健康委员会和中国抗癌协会/中华医学会指南，国际病理与生物标志物口径参考 AJCC、WHO/IARC、CAP、ASCO 等原始规范；
- AJCC 分期表、WHO 分类全文、BI-RADS Atlas、SNOMED CT 等受版权或地区许可约束的内容只登记来源，不复制到公开仓库；获合法授权的本地资料放入 `local_knowledge/`；
- NCIt、LOINC、RxNorm、ATC/DDD 等动态术语库导入时必须记录版本、获取日期及文件 SHA256，不默认把整个术语库提交到 Git；
- 指南能提供定义，但不能替代本研究的汇总口径。解剖/预后分期、index lesion、治疗周期、复发事件等队列规则仍需在正式抽取前确定。

### 项目问卷与数据口径

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [WPS《信息收集表-2026.4.9最终版》](https://f.kdocs.cn/g/kD2Xj3eU/) | 2026-08-18 登录后核对127个展开问题的题型、选项、复合题及跳题关系；机器可读整理见 `knowledge/schema/wps_form_2026_04_09.yaml` | 用户提供、需登录；仅保存题型与编码规则，不保存填写记录或患者数据 |

### 中国临床基线

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [国家卫生健康委员会《乳腺癌诊疗指南（2022年版）》](https://www.nhc.gov.cn/yzygj/c100068/202204/0c1f7d3aca0545abbeb02030ce255930.shtml) | 中国诊疗流程、病理报告、TNM、FISH、分子分型、绝经定义及常用治疗方案的基线 | 公开网页；引用来源，不在仓库复制全文 |
| [《中国抗癌协会乳腺癌诊治指南与规范（2024年版）》](https://www.china-oncology.com/fileup/1007-3639/PDF/1703749976314-541179100.pdf) | 中国人群诊断、病理、手术、系统治疗和随访术语补充 | 公开期刊文章 |

### TNM、病理与报告结构

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [AJCC 当前分期版本状态](https://www.facs.org/quality-programs/cancer-programs/american-joint-committee-on-cancer/version-9/) | 判断各疾病部位当前适用版本；乳腺在尚未被 Version 9 替换时继续使用第 8 版 | 状态页公开；本项目据此作版本判断 |
| [AJCC Cancer Staging System Products](https://www.facs.org/quality-programs/cancer-programs/american-joint-committee-on-cancer/cancer-staging-systems/cancer-staging-system-products/) | 获取合法授权的 T/N/M、解剖分期及预后分期规则或 API/DLL | 完整规则受许可约束，不随仓库分发 |
| [NCI Breast Cancer Treatment (PDQ)—TNM 与新辅助后分期](https://www.cancer.gov/types/breast/hp/breast-treatment-pdq) | cTNM、ycTNM、pTNM、ypTNM 的时间语境；治疗前临床资料及新辅助后评估的公开说明 | 美国政府公开参考资料；用于流程和语境，不替代获授权 AJCC 规则 |
| [WHO Classification of Tumours Online](https://tumourclassification.iarc.who.int/index.html)（Breast Tumours，第 6 版） | 乳腺肿瘤组织学类型规范名称与分类层级 | 全文需订阅/授权；仅登记引用与本地映射 |
| [CAP Current Cancer Protocols—Breast](https://www.cap.org/protocols-and-guidelines/cancer-protocols/current-cancer-protocols/) | 穿刺、切除、分级、肿瘤范围、淋巴结、治疗反应、pTNM 和标志物报告字段 | 使用公开协议时保留版本与条款信息 |

### 生物标志物与替代分子分型

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [ASCO/CAP ER/PR Testing Guideline Update](https://www.cap.org/protocols-and-guidelines/cap-guidelines/current-cap-guidelines/guideline-recommendations-for-immunohistochemical-testing-of-estrogen-and-progesterone-receptors-in-breast-cancer) | ER/PR 阳性、低阳性、阴性、内对照及报告解释 | 公开指南摘要；规则标记指南版本 |
| [ASCO/CAP HER2 Testing Guideline Update 2023](https://www.cap.org/cap-guidelines/her2-testing-in-breast-cancer-2023-guideline-update/) | HER2 IHC、ISH/FISH 组合和边界情况 | 公开指南页面；规则标记指南版本 |
| [International Ki67 Working Group](https://pubmed.ncbi.nlm.nih.gov/33369635/) | Ki-67 分析有效性、评分方法和阈值使用边界 | PubMed 书目信息与摘要；不把单一阈值写死为普适标准 |
| [St Gallen 2013 surrogate definitions](https://pmc.ncbi.nlm.nih.gov/articles/PMC3755334/) | Luminal A-like、Luminal B-like、HER2-positive 和 triple-negative 替代分型的候选规则 | 开放获取文章；输出必须标记为“替代分型”及规则版本 |

### 新辅助疗效与影像

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [FDA pCR Guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/pathological-complete-response-neoadjuvant-treatment-high-risk-early-stage-breast-cancer-use) | pCR 可接受定义及报告边界 | 公开监管指南 |
| [Miller–Payne 原始分级论文](https://pubmed.ncbi.nlm.nih.gov/14659147/) | 五级病理反应分级 | 书目信息与摘要；正式规则应核对合法全文 |
| [Residual Cancer Burden 原始论文](https://ascopubs.org/doi/10.1200/JCO.2007.10.6823) | RCB 方法学及预后验证 | 出版商文章 |
| [MD Anderson RCB Calculator and Resources](https://www.mdanderson.org/for-physicians/clinical-tools-resources/clinical-calculators/residual-cancer-burden.html) | RCB 原始变量、计算器和病理评估说明 | 公开计算器；记录工具版本/访问日期，不自行改写算法 |
| [RECIST 1.1](https://recist.eortc.org/wp-content/uploads/sites/4/2015/03/RECISTGuidelines.pdf) | 影像靶病灶测量和 CR/PR/SD/PD 定义 | 仅在研究方案明确采用 RECIST 时启用 |
| [ACR BI-RADS](https://www.acr.org/Clinical-Resources/Reporting-and-Data-Systems/Bi-Rads)（第 5 版） | 钼靶、超声、MRI 术语和 BI-RADS 分级 | Atlas 受版权许可约束；公开仓库不复制词典全文 |

### 数据模型、肿瘤术语与药物标准化

| 来源 | 本项目用途 | 访问与许可 |
|---|---|---|
| [mCODE 4.0.0 STU4](https://hl7.org/fhir/us/mcode/) | 患者、疾病特征、TNM、治疗和结局的数据组织与互操作映射 | 开放规范；MVP 不要求部署 FHIR 服务器 |
| [NCI Thesaurus](https://www.cancer.gov/about-nci/organization/cbiit/vocabulary)（[下载入口](https://evs.nci.nih.gov/ftp1/NCI_Thesaurus)） | 肿瘤、解剖、病理、基因、标志物和药物标准概念 | 动态术语库；导入时固定版本与 SHA256 |
| [WHO ICD-O-3.2](https://www.who.int/standards/classifications/other-classifications/international-classification-of-diseases-for-oncology) | 肿瘤部位、形态学、行为和分级编码 | 使用官方发布文件并记录版本 |
| [LOINC 2.82](https://loinc.org/downloads/)（[License](https://loinc.org/license/)） | 检验和部分肿瘤标志物 observation 编码 | 免费但受许可及署名条件约束 |
| [RxNorm](https://www.nlm.nih.gov/research/umls/rxnorm/overview.html) | 药物通用名、商品名、成分、剂量和剂型归一化 | 以美国上市药物为主；下载/API 条款适用 |
| [WHO ATC/DDD](https://www.who.int/teams/health-product-and-policy-standards/inn/atc-ddd) | 药物利用研究和治疗药物分类 | 动态分类；不能替代乳腺癌方案词典 |
| [NCI Drug Dictionary](https://www.cancer.gov/publications/dictionaries/cancer-drug) | 抗肿瘤药物别名、机制及 NCIt 链接补充 | 公开网页词典 |
| [SNOMED CT Licensing Information](https://docs.snomed.org/snomed-ct-user-guides/mlds-user-guide/member-affiliate-licensing-information) | 疾病、临床发现、手术和治疗概念映射 | 按部署地区核对会员/附属许可，不随仓库分发术语包 |

### 主要论文引用

1. 中国抗癌协会乳腺癌专业委员会，中华医学会肿瘤学分会乳腺肿瘤学组. 中国抗癌协会乳腺癌诊治指南与规范（2024年版）. *中国癌症杂志*. 2023;33(12):1092–1187.
2. Quinn C, Tan PH, Allison KH, et al. The 2026 WHO Classification of Tumours of the Breast. *Histopathology*. 2026. doi:10.1111/his.70149.
3. Allison KH, Hammond MEH, Dowsett M, et al. Estrogen and Progesterone Receptor Testing in Breast Cancer: ASCO/CAP Guideline Update. *J Clin Oncol*. 2020;38(12):1346–1366. doi:10.1200/JCO.19.02309. PMID:31928404.
4. Wolff AC, Somerfield MR, Dowsett M, et al. Human Epidermal Growth Factor Receptor 2 Testing in Breast Cancer: ASCO/CAP Guideline Update. *J Clin Oncol*. 2023;41(22):3867–3872. doi:10.1200/JCO.22.02864. PMID:37284804.
5. Nielsen TO, Leung SCY, Rimm DL, et al. Assessment of Ki67 in Breast Cancer: Updated Recommendations From the International Ki67 in Breast Cancer Working Group. *J Natl Cancer Inst*. 2021;113(7):808–819. doi:10.1093/jnci/djaa201. PMID:33369635.
6. Goldhirsch A, Winer EP, Coates AS, et al. Personalizing the treatment of women with early breast cancer: highlights of the St Gallen International Expert Consensus 2013. *Ann Oncol*. 2013;24(9):2206–2223. doi:10.1093/annonc/mdt303.
7. Ogston KN, Miller ID, Payne S, et al. A new histological grading system to assess response of breast cancers to primary chemotherapy. *Breast*. 2003;12(5):320–327. doi:10.1016/S0960-9776(03)00106-1. PMID:14659147.
8. Symmans WF, Peintinger F, Hatzis C, et al. Measurement of residual breast cancer burden to predict survival after neoadjuvant chemotherapy. *J Clin Oncol*. 2007;25(28):4414–4422. doi:10.1200/JCO.2007.10.6823.
9. Eisenhauer EA, Therasse P, Bogaerts J, et al. New response evaluation criteria in solid tumours: revised RECIST guideline (version 1.1). *Eur J Cancer*. 2009;45(2):228–247. doi:10.1016/j.ejca.2008.10.026.

## Git 安全

`.gitignore` 已排除 `workspace/`、`database/`、`models/`、日志、数据库、GGUF 和离线镜像。提交前仍应运行：

```powershell
git status --short
```

确认不存在病历、患者标识、数据库或模型权重。
