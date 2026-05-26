# C-HyperMem Retrieval Design

本文档记录 C-HyperMem 检索算法的设计概念和 pipeline 边界。具体代码模块、真实配置、测试覆盖和当前实现进度放在 `current_implementation.md` 中维护；本文只保留检索设计应遵守的结构。

当前约束：

- `retrieval.query_analysis: false` 是唯一当前开发目标。
- 当前 false 链路不使用 `c_hypermem/prompts/retrieval/query_analysis.md`。
- 当前 false 链路不加载 spaCy。
- `nlp` / `llm` query analysis 只保留为未来扩展入口；当前不参与默认开发链路。
- 不做规则化 query 抽取，尤其不从 query 中用规则抽取 entity candidates。
- 不做兜底召回策略。
- 当前仍是开发环境，不考虑旧数据迁移或兼容。

## 参数边界

检索参数应围绕以下边界组织，具体字段名和默认值以 `current_implementation.md` 与配置文件为准：

- query analysis 模式。
- lexical recall 候选数。
- node content / node local graph 向量召回候选数。`node_content` 向量文本由 `MemoryNode.content` 与 `MemoryNode.summary` 拼接生成，不再拆分独立 `node_summary` 向量通道。
- HyperEdge description 向量召回候选数。
- RRF 常数 `rrf_k`。
- RRF 后进入图谱涟漪扩散的 seed 数。
- HyperEdge coherence 的 `alpha` / `beta` 权重。
- 最终返回的 HyperEdge 数量。

## 检索 Pipeline

```text
Memory.search(query, namespace)
  -> query analysis
  -> parallel rank channels
     -> lexical node recall
     -> node_content vector recall
     -> node_local_graph vector recall
     -> hyper_edge_description vector recall
        -> each ranked HyperEdge projects its rank contribution to all active member nodes
  -> node-level fusion
     -> Reciprocal Rank Fusion across all four channels
  -> graph ripple expansion
     -> seed node -> incident HyperEdge -> all edge member nodes
     -> incident HyperEdge -> EdgeCluster -> sibling edges and description variants
     -> HyperEdge coherence scoring
  -> edge-level ranking
  -> final top-k HyperEdges, each carrying member nodes
```

## 向量召回

用户 query 会先被向量化，然后分别查询两个 node 向量索引和一个 HyperEdge 向量索引：

- `node_content`
- `node_local_graph`
- `hyper_edge_description`

node 向量命中必须通过 payload 中的 `node_id` 回到 SQLite canonical store 读取 `MemoryNode`。HyperEdge description 向量命中必须通过 payload 中的 `edge_id` 回到 SQLite canonical store 读取 `HyperEdge`，并读取其 active 成员 `MemoryNode`，把该 edge 的向量排名投影为这些节点的同量纲 RRF 贡献。向量索引只作为可重建旁路索引，不作为权威数据源。

`node_content` 索引文本为 node content 与 node summary 的拼接；当 summary 拼接或压缩维护导致 `MemoryNode.summary` 更新时，写入闭环必须用同一个 node content vector point id 覆盖更新。

## Lexical 召回

用户 query 同时进入词法召回通道。第一阶段可使用 SQLite FTS；后续也可以替换为 BM25 或其他开发者自定义算法。

词法召回应作为独立算法模块，不应把 FTS / BM25 细节写死在检索编排器里。

## 融合策略

当前使用 Reciprocal Rank Fusion。

RRF 常数通过 `retrieval.rrf_k` 显式配置；实现上仍应封装在融合模块中，方便后续替换融合策略。

```text
score(node) =
  1 / (rrf_k + rank_lexical)
  + 1 / (rrf_k + rank_node_content_vector)
  + 1 / (rrf_k + rank_node_local_graph_vector)
  + max(1 / (rrf_k + rank_hyper_edge_description_vector(edge))
        for each recalled edge containing node)
```

其中：

- `rank_lexical` 来自 SQLite FTS 结果排序。
- `rank_node_content_vector` 来自 node content + summary 向量召回排序。
- `rank_node_local_graph_vector` 来自 node local graph 向量召回排序。
- `rank_hyper_edge_description_vector(edge)` 来自 HyperEdge description 向量召回排序；命中的 edge 将排名证据投影到其全部 active 成员节点，而节点只采用所属命中 edge 中的最佳排名贡献。
- 若节点不属于任何被 HED 通道召回的 active HyperEdge，则该通道对节点的贡献为 `0`。
- 如果某个节点只出现在一路召回中，只计算该路的 RRF 分数。

每个 node 向量通道内部先按每个节点的最佳向量分数形成该通道排名，再与 lexical 排名做 RRF。
HyperEdge description 通道按 node 聚合所属命中 edge：同一个节点若属于多条被召回的 HyperEdge，仅其排名最高的 edge 对该节点贡献一次 RRF 分数；所有匹配 edge payload 仍保留用于解释。由此第四通道与其他三个通道一样，对单个节点的基础分上限固定为 `1 / (rrf_k + 1)`。

## 图谱涟漪扩散

统一四通道 RRF 之后，系统取 `graph_seed_top_k` 个高分 MemoryNode 作为图谱种子。因此 HyperEdge description 命中也通过投影后的节点进入同一扩散路径，不形成独立 edge 打分体系。

扩散步骤：

1. 对种子节点调用 `get_incident_edges(...)`，找到它们归属的 HyperEdge。
2. 将命中 HyperEdge 内的所有 active MemoryNode 加入候选池。
3. 如果命中 HyperEdge 属于某个 EdgeCluster，读取该 Cluster 的成员 HyperEdges。
4. 读取该 Cluster 内其他 HyperEdge，并将这些边内的 active MemoryNode 和 description 作为动态检索上下文加入候选池。

涟漪扩散只依赖已有图结构，不分析 query，不做规则化抽取，不做兜底策略。

## Edge Coherence

如果同一条 HyperEdge 中有两个或更多节点同时出现在 RRF 初始候选池中，说明这条边对应的语境更可能是用户问题的故事线。此时对该 HyperEdge 内所有成员节点施加结构化相干性加分。

公式：

```text
S_coherence(E) =
  alpha * max(0, N_hit - 1) ^ beta * S_base_avg
```

其中：

- `E`: 被命中的 HyperEdge。
- `N_hit`: RRF 初始候选池中属于该边的节点数量。
- `alpha`: `retrieval.edge_coherence_alpha`。
- `beta`: `retrieval.edge_coherence_beta`。
- `S_base_avg`: 这些命中节点的 RRF 初始平均分。

实现约束：

- `N_hit <= 1` 时，相干性加分为 0。
- `N_hit >= 2` 时，相干性加分写入 `score_parts.edge_coherence`。
- `N_hit` 只统计由 lexical / node content vector / node local graph vector 独立命中的 seed nodes。HyperEdge description 命中向成员节点的投影已经构成该通道的基础分，不因一次 edge 命中投影出多个成员而额外触发 coherence。
- 相干性加分会加到该 HyperEdge 内所有 active 成员节点上，包括由图谱扩散新带出的节点。
- EdgeCluster 带出的 sibling edge nodes 会进入候选池和 metadata；除非它们所属 HyperEdge 自身满足 2+ seed hits，否则不会凭空获得 `edge_coherence`。

## Final Edge Result

`final_top_k` 控制最终返回的 edge 数量，而不是 node 数量。

每个 `SearchResult` 表示一条 HyperEdge：

- `id`: `edge_id`
- `content`: edge description + edge 内 node 内容
- `score`: edge-level score
- `metadata.edge_nodes`: 该 edge 内包含的 MemoryNode 列表
- `metadata.edge_metadata`: 系统写入的 edge metadata，例如 `source_turn_ids`

Edge-level score 当前来自 edge 内成员 node 在图谱扩散后的最高分：

```text
S_edge = max(S_node for node in edge_nodes)
```

其中 `S_node` 已经包含 RRF 分数和可能存在的 `edge_coherence` 分数。这样 `final_top_k` 选择的是最相关的故事线/关系边，再把这些边内的节点整体返回。

## 结果边界

最终返回单位是 HyperEdge，而不是单个 MemoryNode。每条结果应包含：

- edge identity、description、system metadata。
- edge-level score 与可解释 score parts。
- edge 内成员 nodes。
- 每个 node 的内容、分数来源和 triples；triple 的 HyperEdge 上下文使用 `scope_edge_ids`，同一个 triple 可以保留多个 edge scope。
- 每个 node 的系统来源字段，例如 `source_turn_ids`、`node_metadata`。
- 如果 edge 属于 EdgeCluster，附带 cluster id，以及从 cluster member HyperEdges 动态读取的 edge descriptions。

具体 JSON metadata 字段以 `current_implementation.md` 为准。

## 当前不做

当前检索流程不接入：

- entity alias recall
- turn dialogue recall
- recency decay
- access boost
- temporal filter
- LLM rerank
- spaCy query analysis
- LLM query analysis

这些能力如果后续需要加入，应等到对应开发阶段再设计和实现。
