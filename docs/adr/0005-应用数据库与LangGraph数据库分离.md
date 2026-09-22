# 应用数据库与 LangGraph 数据库分离

应用使用当前用户目录下 `.pet-comic/app.db` 保存宠物档案、供应商配置、任务索引、节点结果和事件；使用 `.pet-comic/langgraph.db` 保存 LangGraph checkpoint。两者职责分离，应用不直接依赖 checkpoint 内部表；`task_items` 以执行批次、节点、item 和输入 hash 记录成功结果，使节点重跑只处理失败或输入已变化的项。
