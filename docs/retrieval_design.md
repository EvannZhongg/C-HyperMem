# C-HyperMem Retrieval Design

本文档记录当前开发阶段的检索流程。它替换旧的检索设计草案，只描述已经决定进入当前实现的路径。

当前约束：

- `retrieval.query_analysis: false` 是唯一当前开发目标。
- 不使用 `c_hypermem/prompts/retrieval/query_analysis.md`。
- 不加载 spaCy。
- 不做规则化 query 抽取。
- 不做兜底召回策略。
- 当前仍是开发环境，不考虑旧数据迁移或兼容。

## 配置

```yaml
retrieval:
  query_analysis: false
  lexical_top_k: 30
  node_content_vector_top_k: 20
  node_local_graph_vector_top_k: 20
  node_summary_vector_top_k: 10
  graph_seed_top_k: 80
  edge_coherence_alpha: 0.5
  edge_coherence_beta: 2.0
  final_top_k: 10
```

字段含义：

- `query_analysis`: 当前固定为 `false`，表示检索不做 LLM 或 spaCy query analysis。
- `lexical_top_k`: SQLite FTS 召回的 MemoryNode 数量。
- `node_content_vector_top_k`: `node_content` vector collection 召回数量。
- `node_local_graph_vector_top_k`: `node_local_graph` vector collection 召回数量。代码中对应现有 `triple` vector store。
- `node_summary_vector_top_k`: `node_summary` vector collection 召回数量。
- `graph_seed_top_k`: RRF 融合后进入图谱涟漪扩散的初始候选数量，当前为 80。
- `edge_coherence_alpha`: HyperEdge 相干性加分的基础权重。
- `edge_coherence_beta`: HyperEdge 相干性加分的非线性放大指数。
- `final_top_k`: 图谱涟漪扩散后的最终 HyperEdge 数量，当前为 10。每条返回的 edge 内包含其成员 nodes。

## 当前流程

```text
Memory.search(query, namespace)
  -> Retriever.search(...)
     -> QueryAnalyzer.analyze(query)
        - query_analysis=false 时返回原始 query metadata
     -> DenseVectorRecall.embed_query(query)
     -> DenseVectorRecall.recall(...)
        - node_content top 20
        - node_local_graph top 20
        - node_summary top 10
     -> SQLiteFTSRecall.recall(...)
        - SQLite FTS top 30
     -> reciprocal_rank_fusion(...)
     -> GraphRippleExpansion.expand(...)
        - take RRF top 80 as graph seeds
        - seed node -> incident HyperEdge -> all member nodes
        - incident edge -> EdgeCluster -> description_variants and sibling edge nodes
        - apply edge_coherence when one HyperEdge has 2+ seed hits
     -> final top 10 HyperEdge
     -> SearchResult per edge, with edge_nodes
```

## 向量召回

用户 query 会先被向量化，然后分别查询三个向量索引：

- `node_content`
- `node_summary`
- `node_local_graph`

现有代码中 `node_local_graph` 复用历史命名的 `triple` vector store，但 payload 的 `item_type` 为 `node_local_graph`。

每个向量命中必须通过 payload 中的 `node_id` 回到 SQLite canonical store 读取 `MemoryNode`。向量索引只作为可重建旁路索引，不作为权威数据源。

## SQLite FTS 召回

用户 query 同时送入 SQLite FTS：

- FTS 表：`nodes_fts`
- 索引字段：`content`、`summary`、`local_graph`
- namespace 与 node_id 作为非全文索引字段保存，用于过滤和回表。

词法召回通过 `SQLiteFTSRecall` 封装。后续如果开发者要替换成 BM25 或其他词法算法，应替换这个模块，而不是把算法写进 `Retriever`。

## 融合策略

当前使用 Reciprocal Rank Fusion。

常数 `k` 写死为 60，并封装在 `retrieval/fusion.py` 中，后续可替换该模块。

```text
score(node) =
  1 / (60 + rank_lexical)
  + 1 / (60 + rank_vector)
```

其中：

- `rank_lexical` 来自 SQLite FTS 结果排序。
- `rank_vector` 来自三路向量召回合并后的排序。
- 如果某个节点只出现在一路召回中，只计算该路的 RRF 分数。

三路向量召回内部先按每个节点的最佳向量分数形成一个 vector 排名，再与 lexical 排名做 RRF。

## 图谱涟漪扩散

RRF 之后，系统取 `graph_seed_top_k` 个高分 MemoryNode 作为图谱种子。

扩散步骤：

1. 对种子节点调用 `get_incident_edges(...)`，找到它们归属的 HyperEdge。
2. 将命中 HyperEdge 内的所有 active MemoryNode 加入候选池。
3. 如果命中 HyperEdge 属于某个 EdgeCluster，读取该 Cluster 的 `description_variants`。
4. 读取该 Cluster 内其他 HyperEdge，并将这些边内的 active MemoryNode 也加入候选池。

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
- 相干性加分会加到该 HyperEdge 内所有 active 成员节点上，包括由图谱扩散新带出的节点。
- EdgeCluster 带出的 sibling edge nodes 会进入候选池和 metadata；除非它们所属 HyperEdge 自身满足 2+ seed hits，否则不会凭空获得 `edge_coherence`。

## Final Edge Result

`final_top_k` 控制最终返回的 edge 数量，而不是 node 数量。

每个 `SearchResult` 表示一条 HyperEdge：

- `id`: `edge_id`
- `content`: edge description + edge 内 node 内容
- `score`: edge-level score
- `metadata.edge_nodes`: 该 edge 内包含的 MemoryNode 列表

Edge-level score 当前来自 edge 内成员 node 在图谱扩散后的最高分：

```text
S_edge = max(S_node for node in edge_nodes)
```

其中 `S_node` 已经包含 RRF 分数和可能存在的 `edge_coherence` 分数。这样 `final_top_k` 选择的是最相关的故事线/关系边，再把这些边内的节点整体返回。

## SearchResult Metadata

当前结果 metadata 包含：

- `channels`: `lexical`、`vector`、`graph`
- `score_parts`: edge-level score parts，包括 `edge_member_max`、`edge_member_avg`、`edge_coherence`
- `edge_nodes`: edge 内包含的 MemoryNode；每个 node 带自己的 `score_parts`、`channels`、`matched_vector_items`、`triples`
- `hyper_edge_ids`
- `edge_id`
- `edge_type`
- `edge_relation`
- `cluster_ids`
- `cluster_description_variants`
- `time`
- `edge_metadata`
- `query_analysis`

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
