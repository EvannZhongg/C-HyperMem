# C-HyperMem 当前实现状态

本文档记录当前代码实现进展，并说明它与 `development_architecture.md` 的差异。`development_architecture.md` 仍是长期架构蓝图，但本文也记录已经通过实现验证、应反向固化到后续开发中的修正点。后续写代码时不要机械遵守设计文档；若本文标记为“当前实现更优 / 应保持”的地方，应优先以本文为准。

## 1. 对外入口

- `c_hypermem.Memory` 是当前唯一推荐入口。
- 已支持 `from_config/reset/add/add_memory/search/stats/close`。
- `add_memory(...)` 会规范化为 `AgentInteraction`；`add(...)` 会规范化为 `MemoryImportBatch`。
- 如果配置中存在 `llm` 且未显式传入 extractor，`Memory` 会创建默认 `LLMMemoryExtractor`。

## 2. 配置与环境

- 默认配置入口为 `configs/default.yaml`。
- 模型配置拆在 `configs/models.yaml`，节点标签配置拆在 `configs/node_labels.yaml`。
- 仅读取 C-HyperMem 项目根目录下的 `.env`，当前可以直接使用`.env`调用模型进行测试。
- `.env` 已加入 `.gitignore`，仓库提供 `.env.example`。
- `embedding.batch_size` 已加入配置，默认值为 `10`。
- 当前默认节点标签包括：`turn/event/fact/entity/state/preference/task/instruction/tool`。
- `default_policy` 是系统内部 fallback 策略；传入 prompt 时不会以 `default_policy` 名称暴露给 LLM。

## 3. 当前 Schema

核心 schema 位于 `c_hypermem/schema.py`：

- `MemoryNode`：统一节点结构，使用 `node_labels` 表达语义类型。
- `HyperEdge`：具体高阶关系实例，成员通过 `hyper_edge_members` 表保存。
- `EdgeCluster`：相关 HyperEdge 的聚合工作集，不强制合并边。
- `LocalNodeGraph`：所有节点共享的局部图结构，包含 triples、attributes、roles。
- `MemoryExtraction`：LLM 一次抽取输出，只包含 `entities/events/assertions/sources`。

系统 ID 由 `utils/ids.py` 生成，LLM 不生成 `node_id/edge_id/triple_id`。

## 4. 写入 Pipeline

当前写入链路：

```text
Memory.add_memory/add
  -> IngestionPipeline
  -> LLMMemoryExtractor 或显式 extractor
  -> GraphAssembler
  -> SQLiteStore
```

已实现内容：

- 一次抽取：`LLMMemoryExtractor` 渲染 `prompts/extraction/memory_extraction.md`。
- `node_labels.yaml` 的启用标签描述会注入抽取 prompt 的 `{{NODE_LABELS}}`。
- 抽取输出归一化为 `MemoryExtraction`。
- `assertions` 是当前构建事实节点的主输入：每条 assertion 会转为 `fact` 节点、LocalNodeGraph triple、property index 和基础超边成员。
- `GraphAssembler` 负责系统组装：
  - 编排 `EntityResolver` 做轻量 entity alias resolution。
  - 编排 `NodeBuilder` 构建或复用 `entity/event/fact` 节点。
  - 编排 `LocalGraphBuilder` 为 event/entity/fact 构建统一 LocalNodeGraph。
  - 对 preference 谓词追加 `preference` 标签。
  - 编排 `BasicHyperEdgeBuilder` 构建基础 `evidence/state/correction` HyperEdge。
  - 编排 `BasicEdgeClusterBuilder` 创建基础 EdgeCluster 与 cluster members。
  - 写入 entity alias index 和 fact property index。
- 简单冲突事实处理已移入 `GraphMaintenance.retire_conflicting_facts(...)`：
  - 同一 subject node + predicate 下新旧 object 不同时，旧 fact 标记为 `retired`。
  - 创建 `correction` HyperEdge。
  - 同步退役旧 fact property index 行。

## 5. 维护 Prompt

`c_hypermem/prompts/maintenance` 已按当前维护编排拆分：

- `fact_merge.md`：property_key 重合后判断 merge/update/keep separate/需要冲突检查。
- `contradiction_check.md`：处理基础 SPO 冲突。
- `edge_merge.md`：构建新边时判断复用边、追加成员、新版本或新建边。
- `edge_conflict_check.md`：边挂载进 Cluster 后更新簇健康/冲突状态。
- `edge_cluster_merge.md`：后台宏观 Cluster 整理。

`configs/default.yaml` 已配置这些 prompt 路径，并预留：

```yaml
edge_clusters:
  background_maintenance:
    enabled: false
    trigger_every_k_writes: 100
```

注意：这些维护 prompt 当前主要是接口和策略预留，除基础冲突退役外，完整 LLM 维护调用链尚未接入。

## 6. 存储

当前存储实现为 `SQLiteStore`：

- `nodes`
- `triples`
- `hyper_edges`
- `hyper_edge_members`
- `edge_clusters`
- `edge_cluster_members`
- `entity_alias_index`
- `fact_property_index`
- `ingestion_cache`

其中 `ingestion_cache` 表已预留，但增量缓存逻辑尚未正式启用。

## 7. 检索现状

检索代码暂时保持轻量实现：

- `Retriever` 使用 `LexicalScorer` 做 BM25-like 召回。
- 支持基于 HyperEdge 的简单扩展。
- 可根据 `preference/task/entity/time` 等信号做少量结构化加分。

检索侧尚未按设计文档完整重构，后续需要补充向量召回、EdgeCluster 扩展、query analysis LLM、冲突感知排序等。

## 8. 与开发架构文档的实现关系

当前实现已经对齐 `development_architecture.md` 的核心方向：

- C-HyperMem 保持独立包边界，不依赖 `agent_memory_eval`。
- 对外入口收敛到 `Memory.from_config/reset/add/add_memory/search/stats/close`。
- LLM 只做一次紧凑语义抽取，输出 `entities/events/assertions/sources`，不生成系统 ID、权重或外层图结构。
- 系统统一生成 `MemoryNode/HyperEdge/EdgeCluster/LocalTriple` ID。
- `MemoryNode` 使用统一 schema，语义类型通过可累积 `node_labels` 表达。
- 实体 alias resolution 先于 entity 节点 ID 生成。
- `HyperEdge` 与成员表分离，`EdgeCluster` 聚合相关边但不强制合并边。
- `LocalNodeGraph` 采用统一结构，基础 triple 已持久化到 `triples` 表。
- 基础 `evidence/state/correction` HyperEdge 已打通，基础冲突事实退役已接入写入流程。

当前实现仍低于设计文档的部分：

- 增量构建缓存只实现了 `ingestion_cache` 表结构，尚未实现 cache cursor、prefix hash、append-only/rebuild 判断。
- 维护 prompt 已存在，但 `fact_merge/contradiction_check/edge_merge/edge_conflict_check/edge_cluster_merge` 的 LLM 调用链尚未接入主流程。
- `turn/state/task/instruction/tool` 已作为标签配置存在，但尚未都有专门构建策略；当前主要依靠 LLM 输出 labels 和统一节点结构承载。
- 向量索引配置和 embedding client 已有，但检索主流程仍以 lexical recall 为主，尚未启用完整向量召回链路。
- EdgeCluster 当前由边描述轻量生成，尚未实现相似 cluster 召回、LLM cluster merge、后台宏观整理和复杂冲突状态维护。
- LocalNodeGraph 当前只覆盖 event participants、entity attributes 和 assertion SPO；还没有从事件内部关系、工具调用、任务状态中构建更丰富的局部图。

## 9. 设计仍不明确时的轻量替代方案

以下点在设计文档中有方向，但工程边界、触发条件或评测收益还不明确。当前实现先采用轻量方案，避免过早引入不可控复杂度：

- **实体消歧**  
  设计方向：后续可引入更复杂的 entity resolution。  
  当前方案：只用 normalized alias 和可选 `entity_type` 精确匹配。  
  原因：LLM 合并实体的误合并成本很高，尤其是不同样本、同名人物、宠物/项目重名场景。后续若引入 LLM，只能作为候选确认，不应直接覆盖 alias 精确匹配结果。

- **事实 merge / update / contradiction**  
  设计方向：通过 `fact_merge.md` 和 `contradiction_check.md` 判断 merge、update、keep separate、conflict。  
  当前方案：同一 `subject_node_id + predicate` 下 object 不同则保守退役旧 fact，并创建 correction edge；多值谓词暂不退役。  
  原因：哪些谓词是单值、哪些 object 兼容、如何处理时间有效期仍需要评测反馈。当前 deterministic 规则更可解释，也保留历史事实。

- **HyperEdge 复用与合并**  
  设计方向：根据成员重叠、relation、roles、polarity、source/time 召回候选并判断复用、追加成员、新版本或新建。  
  当前方案：基础边保守新建，只按确定性 fingerprint 去重；成员重叠不触发合并。  
  原因：成员相近的边可能表达支持、修正或冲突关系，直接合并会污染语义。后续 edge merge 必须先完成冲突感知和角色兼容规则。

- **EdgeCluster 整理**  
  设计方向：相关 HyperEdge 进入同一 cluster，并支持后台 cluster merge。  
  当前方案：按 edge 类型和描述创建基础 cluster；后台整理只保留配置开关。  
  原因：cluster 相似度阈值、冲突 cluster 的状态机、description variants 的压缩策略都还没有稳定标准。

- **LocalNodeGraph 丰富度**  
  设计方向：节点内部保存属性、角色、三元组、qualifiers 和局部状态。  
  当前方案：从 assertions 和 event participants 构建基础 triple/roles；不要求 LLM 直接输出复杂 graph。  
  原因：让 LLM 同时抽取 facts、attributes、triples 容易重复写入同一事实。当前以 assertions 为主输入，能保持信息来源单一。

- **标签专门策略**  
  设计方向：`turn/state/task/instruction/tool` 可有各自的时间、索引、检索策略。  
  当前方案：这些标签先通过统一 `MemoryNode` 承载，暂不新增专用 schema 或强规则构建器。  
  原因：真实 agent 数据中的 tool/task/instruction 形态差异较大，过早固定策略会限制后续适配。

- **检索增强**  
  设计方向：lexical + vector + hyperedge + edge cluster + temporal + rerank。  
  当前方案：lexical recall + 简单 HyperEdge expansion + 少量结构化加分。  
  原因：写入结构还在稳定，先保留可解释检索链路，避免向量和 rerank 问题掩盖写入质量问题。

- **增量构建缓存**  
  设计方向：prefix hash、config hash、prompt hash、append-only/rebuild 判断。  
  当前方案：只预留表结构，不参与写入决策。  
  原因：缓存一旦误判会造成旧事实解释不更新。需要先稳定冲突维护和实体消歧后再启用。

这些轻量方案的原则是：先保证统一 schema、系统生成 ID、一次抽取和基础写入闭环稳定，再逐步补维护和检索增强。

## 10. 当前实现优于或修正原设计的地方

以下实现选择已经比原始设计文字更清晰，后续应优先保留，必要时把设计文档反向更新：

- **`GraphAssembler` 只保留编排职责**  
  原设计列出了多个 pipeline 模块，但没有明确 `GraphAssembler` 是否继续承载实现细节。当前拆分为 `EntityResolver`、`NodeBuilder`、`LocalGraphBuilder`、`BasicHyperEdgeBuilder`、`BasicEdgeClusterBuilder`、`GraphMaintenance` 后，边界更清楚。后续不要把实体解析、节点构建、局部图构建或冲突维护重新塞回 `GraphAssembler`。

- **基础构建器与外部扩展 builder 并存**  
  当前 `BasicHyperEdgeBuilder` / `BasicEdgeClusterBuilder` 承担内置 M1 规则，`IngestionPipeline` 仍保留可注入的 `hyperedge_builder` / `edge_cluster_builder` 扩展点。这个形态比“只有 protocol 占位”更可运行，也比直接把规则写死在 assembler 更容易替换。

- **维护 prompt 不默认进入主链路**  
  原设计容易让后续实现把多个 maintenance prompt 串到每次写入中。当前保持“确定性规则先行，LLM 维护按需触发”的方向更稳。后续接入 prompt 时，应有明确召回候选、触发条件、成本控制和失败降级，不应每次写入无条件多轮调用 LLM。

- **`assertions` 作为事实、property index 和基础 triple 的唯一主输入**  
  这比让 LLM 同时输出 facts、attributes、triples 更稳定。后续即使扩展 extraction schema，也应避免同一事实在多个字段重复入库。

- **保守冲突退役优先于物理覆盖**  
  当前保留旧 fact，并用 `retired/superseded_by/invalidated_by/correction edge` 表达修正。这一点应保持，不应为了“更新事实”直接覆盖旧节点。

- **EdgeCluster 不是 HyperEdge merge 的前置条件**  
  当前实现允许先创建具体 HyperEdge，再用 cluster 轻量聚合。后续相似边召回、cluster merge 都应维持“不强制合并具体边”的原则。

- **`default_policy` 只作为内部 fallback，不暴露为 prompt label**  
  这避免 LLM 抽取出 `default_policy` 这种实现名标签。后续扩展 node label prompt 时应保持该行为。

## 11. 验证

当前测试覆盖：

- 默认配置和 split config 加载。
- `.env` 模型变量解析。
- embedding `batch_size` 配置和分批调用。
- 统一节点 schema 和 SQLite 表结构。
- 显式 extractor 到系统组装链路。
- 默认节点标签集合。
- `default_policy` 不作为 prompt label 渲染。
- 抽取 prompt 注入 `node_labels.yaml`。
- 维护 prompt registry 加载。
- 冲突 fact 退役与 correction edge。

常用验证命令：

```powershell
python -m compileall -q c_hypermem
python -m pytest -q
```
