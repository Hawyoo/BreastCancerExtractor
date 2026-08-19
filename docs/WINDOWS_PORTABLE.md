# BreastCancerExtractor Windows Portable

## 默认使用：只需要 OCR

1. 解压整个 `BreastCancerExtractor` 文件夹，不要只复制 exe。
2. 双击 `BreastCancerExtractor.exe`。
3. PaddleOCR 会由 Portable 自动启动。
4. 浏览器会打开 `http://127.0.0.1:8765`。

**Ollama 不是 Windows 版必需组件。** 没有安装 Ollama 时，图片导入、脱敏、ROI、OCR、人工录入和审核均可正常使用，只是不运行本地 AI 抽取。

关闭启动窗口或按 `Ctrl+C` 会停止本次 Portable 主程序及由它启动的辅助服务。

## 需要本地 AI 时

任选一种方式即可：

### 方式 A：单独安装系统 Ollama（推荐）

安装 Ollama 后启动它，BreastCancerExtractor 会自动连接本机 `127.0.0.1:11434`。

例如：

```powershell
ollama pull qwen3:8b
```

已经由用户自己启动的系统 Ollama 不会在 BreastCancerExtractor 退出时被关闭。

### 方式 B：构建自带 Ollama 的 Portable

默认：

```text
build-portable.bat
```

生成精简版，不携带 Ollama。

如果明确需要离线自带 Ollama，并且构建电脑已安装 Ollama：

```text
build-portable-with-ollama.bat
```

此时才会把 Ollama runtime 复制到：

```text
runtime/ollama/
```

## 数据目录

Portable 明确分为患者数据、本机配置和可重建运行文件：

```text
database/        只保存患者数据；可整体复制、备份和跨电脑拼接
  patients/
    <7位病案号>/
      patient.sqlite
      manifest.json
      sanitized/
config/          本机配置，例如 runtime_config.json、instance.json
runtime/         可重建索引和缓存，例如 catalog.sqlite、PaddleOCR缓存
models/llm/      用户自行放入的 GGUF
local_knowledge/ 本地知识库扩展
logs/            本地日志
```

### `database/` 可以直接搬走

`database/` 是患者数据的唯一便携目录。每名患者都是一个自包含数据包：

- `patient.sqlite`：该患者完整结构化数据、OCR、审核和审计记录；
- `manifest.json`：患者包版本、校验信息和文件清单；
- `sanitized/`：脱敏图片。

把另一台电脑的 `database/patients/` 中不同病案号目录直接复制进本机 `database/patients/` 即可。程序启动时会自动发现尚未进入本机索引的新患者并导入，不要求逐个手工登记。

相同病案号若存在不同内容，不会静默覆盖；应保留两个患者包目录后使用“扫描患者目录”进入冲突处理。

### `catalog.sqlite` 不需要备份

`runtime/catalog.sqlite` 只是本机运行时总索引，不再属于患者数据。删除它不会删除患者资料：下次启动会根据 `database/patients/*/patient.sqlite` 自动重建。

旧版本升级时，程序会自动把：

```text
database/catalog.sqlite      -> runtime/catalog.sqlite
database/runtime_config.json -> config/runtime_config.json
database/instance.json       -> config/instance.json
```

迁移完成后，`database/` 根目录只保留 `patients/` 患者数据。

## TNM 与影像尺寸的确认后整理

完整 `cTNM/ycTNM`、`pTNM/ypTNM` 和完整影像尺寸字符串仍是唯一可编辑主字段。

人工确认后，程序会自动生成只读字段：

- TNM：分别拆出 T、N、M；
- 影像尺寸：按原文顺序拆出径线1、径线2、径线3，并统一显示为 mm；
- 原文只有两个径线时，第3径留空，不补造。

只读字段可在患者回顾、数据总览和 CSV 中使用，但不能单独修改；需要修改时必须修改完整主字段并重新确认，派生字段随后自动重算。

## 备份

患者资料只需备份：

```text
database/
```

如果还希望保留本机模型选择等偏好，可额外备份：

```text
config/
models/
local_knowledge/
```

`runtime/` 不需要备份。
