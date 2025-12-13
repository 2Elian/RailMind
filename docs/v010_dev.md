# V0.1.0-第一代版本bug解决文档


## 2. 遇到的挑战及解决方案

### 2.1 Query重写模块


### 2.2 意图识别模块


### 2.3 ReThink模块


1. 参数名称规范与模糊查询问题

    比如：车站名称、城市名称、列车车次等必须使用中文 --> 北京西=北京西站，但是北京西站 在数据库是搜不出来的！ --> 比如用户输入的是北京，那么北京站、北京西站、北京南站应该都返回结果

    解决逻辑：先获取用户当前所在城市 --> 搜索当前城市的所有车站(火车、高铁、飞机、公交大巴)

2. 当任务完成的时候 返回的 func call 名称不在tools里面
    
    这种情况，我们在提示词里面做限制

    ```bash
    ### 4. 任务完成信号
        当满足以下任一条件时，请设置 `function_name` 为 `"end_of_turn"`：
        - 已经获取了回答问题所需的所有信息
        - 已经执行了必要的函数且有结果
        - 无法通过现有函数获取更多信息
        - **不要**在还没有任何数据时就结束
    ```


### 2.4 Func Call 执行模块


### 2.5 完成度评估模块


### 2.6 Agent记忆问题


### 2.7 前端可视化


### 2.8 其他零碎问题

1. 简单查询 过度循环问题

    query明明很简单，只需要调用一个func call就能解决的问题，系统会不断的循环，增加了无用的多轮循环的时间。

    1.1 评估时 --> 模型过度检查真实性
    ```bash
    example:
    问题: K4547/6次列车的始发站是哪里？
    系统调用了get_train_details工具，参数为K4547/6
    返回值是：
        [
        {
            "车次": "K4547/6",
            "始发站": "成都西",
            "终到站": "佳木斯",
            "发车时间": "00:12:00",
            "到达时间": "23:40:00",
            "候车厅": [
            "高架候车区西区",
            "综合候乘中心"
            ],
            "检票口": "1B",
            "站台": "2"
        }
        ]
    但是在评估的时候：{'score': 0.95, 'reason': '结果直接对应用户查询的列车始发站需求'}, 'accuracy': {'score': 0.0, 'confidence': 0.0, 'potential_issues': ['未获取到有效数据记录']}, 'should_continue': True, 'next_action_suggestion': '重新执行get_train_details函数并验证参数有效性'}
    导致重回Rethink执行
    ```

    导致这个问题的PROMPT的2个版本如下：

    ```bash
    # 版本1
    SYSTEM_PROMPT : str = """你是一个专业的结果评估助手。评估函数执行结果是否满足用户需求。

    评估维度：
    1. 完整性：结果是否包含所有必要信息
    2. 相关性：结果与用户查询的相关程度
    3. 准确性：结果是否准确可靠
    4. 是否需要继续：判断是否需要执行更多函数来获取完整答案

    输出格式（JSON）：
    {{
        "completeness": {{
            "score": 0.8,
            "missing_info": ["缺失的信息1", "缺失的信息2"],
            "is_complete": true/false
        }},
        "relevance": {{
            "score": 0.9,
            "reason": "相关性说明"
        }},
        "accuracy": {{
            "score": 0.85,
            "confidence": 0.9,
            "potential_issues": ["潜在问题1"]
        }},
        "should_continue": true/false,
        "next_action_suggestion": "建议的下一步操作（如果需要继续）",
    }}"""


    # 版本2

    SYSTEM_PROMPT : str = """你是一个专业的结果评估助手。评估函数执行结果是否满足用户需求。

    评估维度：
    1. 完整性：结果是否包含所有必要信息
    2. 相关性：结果与用户查询的相关程度
    3. 准确性：结果是否准确可靠
    4. 是否需要继续：判断是否需要执行更多函数来获取完整答案

    输出格式（JSON）：
    {{
        "accuracy": float, # 对于当前结果，是否解决了query，给出一个0-1的分数
        "should_continue": true/false, # 是否需要继续，如果当前结果没有解决query，则需要继续，否则不需要继续
    }}"""

    USER_PROMPT : str = """原始查询：{query}

    已执行的函数：
    {executed_functions}

    当前结果：
    {current_results}

    请评估这些结果是否足以回答用户的查询。"""
    ```

    经分析，以上两个版本的prompt会使得模型喜欢怀疑结果是否真实，而不是判断“是否回答了 query”。

    解决方案：必须让模型把任务限制为：评估是否回答了 query，而不是质疑函数数据是否真实、是否最新、是否可信。

    1.2 多个子查询调度的时候 出现代码逻辑错误

    已在xxx修复，在ER模块中，强化了should_continue=True的逻辑，只要子查询完成，就立刻记录state里面的状态到子查询，然后清空state必要的部分，开始下一个子查询

    1.3 func call为end的时候 graph依旧向下执行节点为题

    已在xxx修复


## 3. bug解决记录

### 3.1 当分解2个子query的时候，如果子query1调用的func call 子query2也要调用会产生如下bug

```bash
'thoughts': [{'iteration': 0, 'timestamp': '2025-12-13T14:19:50.808242', 'sub_query_index': 1, 'sub_query': 'K4547/6次列车的候车厅位置是什么？', 'content': {'thought': '用户询问K4547/6次列车的候车厅位置，已调用get_train_details获取列车详情但返回空结果。当前没有其他可用函数，无法进一步获取候车厅信息。', 'reasoning': '根据系统工具限制，只有get_train_details函数可用，但该函数未返回候车厅位置信息。现有数据无法满足用户需求，且无法通过其他途径获取补充信息。', 'next_action': {'function_name': 'end_of_turn', 'parameters': {}, 'reason': '已尝试获取列车详细信息但未获得候车厅位置数据，系统无其他可用功能补充信息'}, 'expected_outcome': '向用户说明无法获取该列车的候车厅位置信息'}}],
```
这个bug是因为在_update_current_sub_query函数中，清理evaluation_result写成了清理exe_info，导致的错误。已在66d57fa处理。
