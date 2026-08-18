# BreastCancerExtractor Windows Portable

## 使用

1. 解压整个 `BreastCancerExtractor` 文件夹，不要只复制 exe。
2. 双击 `BreastCancerExtractor.exe`。
3. 程序会检测本机 `127.0.0.1:11434` 上的 Ollama；没有服务时会尝试启动 `runtime/ollama/ollama.exe`。
4. OCR 由 Portable 内携带的本地 PaddleOCR 服务自动启动。
5. 浏览器会打开 `http://127.0.0.1:8765`。

关闭启动窗口或按 `Ctrl+C` 会停止本次 Portable 主程序及由它启动的辅助服务。

## 数据目录

所有可写数据均保存在 exe 同级目录：

```text
database/       SQLite 数据库
workspace/      脱敏图片和证据
models/llm/     用户放入的 GGUF 文件
models/ollama/  Portable Ollama 注册后的模型
local_knowledge/本地知识库扩展
logs/           本地运行日志
runtime/ollama/ Ollama standalone runtime
```

复制或升级程序前，请备份 `database/`、`workspace/`、`models/` 和 `local_knowledge/`。

推荐模型为 Qwen3 8B，但程序不会把模型名称写死；可在 Web 模型管理中选择或导入其他本地模型。
