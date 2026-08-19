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

所有可写数据均保存在 exe 同级目录：

```text
database/        患者数据库和脱敏图片
models/llm/      用户自行放入的 GGUF
local_knowledge/ 本地知识库扩展
logs/            本地日志
runtime/         OCR 缓存；带 Ollama 构建时还包含 runtime/ollama/
```

每名患者位于 `database/patients/<7位病案号>/`。跨设备复制患者目录后，在首页点击“扫描患者目录”完成登记或冲突处理。

升级或迁移前建议备份：

```text
database/
models/
local_knowledge/
```
