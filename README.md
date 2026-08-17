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
- 158 项队列字段的机器可读数据字典、乳腺癌病理 Schema、IHC 规则和 Prompt；
- TNM“病历记录优先、缺失时推断”的策略，区分 c/p/yc/yp 并要求推断结果人工复核；
- 公开知识库与 `local_knowledge/` 本地授权/内部资料分离。

尚未完成的模块包括 PaddleOCR/PP-Structure 实际推理、LLM 自动抽取任务队列、完整 AJCC 确定性分期规则、证据文字框精确回链、Excel 导出和离线版镜像打包。代码结构已为这些阶段保留边界，但 README 不把骨架描述成已完成功能。

字段定义和仍需补充的医院口径详见 `knowledge/manual/知识库手册.md`。

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
local_knowledge/ 授权或医院内部知识（禁止提交）
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
- 离线版：额外携带 `docker save` 导出的镜像 tar、已核对许可的 OCR/LLM 模型和离线安装说明。真实患者资料永远不属于发布物。

## 知识库来源与参考文献

以下来源已于 **2026-08-17** 核对。机器可读登记表位于 `knowledge/references/sources.yaml`；其中记录来源 ID、版本、用途、访问方式和许可边界。项目采用以下原则：

- 病历明确记载优先于模型推断；标准用于结构化、校验和缺失项推断，不用于覆盖原始记录；
- 中国临床口径优先参考国家卫生健康委员会和中国抗癌协会/中华医学会指南，国际病理与生物标志物口径参考 AJCC、WHO/IARC、CAP、ASCO 等原始规范；
- AJCC 分期表、WHO 分类全文、BI-RADS Atlas、SNOMED CT 等受版权或地区许可约束的内容只登记来源，不复制到公开仓库；获合法授权的本地资料放入 `local_knowledge/`；
- NCIt、LOINC、RxNorm、ATC/DDD 等动态术语库导入时必须记录版本、获取日期及文件 SHA256，不默认把整个术语库提交到 Git；
- 指南能提供定义，但不能替代本研究的汇总口径。解剖/预后分期、index lesion、治疗周期、复发事件等队列规则仍需在正式抽取前确定。

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
