# RailMind

RailMind是一个基于LangChain构建的ReAct铁路运输场景下的问答系统

后续优化：Agent-RL训练、多智能体协作、更强大的记忆系统、与多数据库交互、抗并发等前沿Agent方法


# Framework

```mermaid
sequenceDiagram
    participant User
    participant Rewrite Query
    participant Intention Recognize
    participant async LLM
    participant Execute Action
    participant 知识图谱
    participant Result Eval

    User->>Rewrite Query: 发送原始Query
    
    Note over Rewrite Query: 步骤1: Query预处理
    Rewrite Query->>Rewrite Query: 1.1 纠错与标准化<br/>1.2 同义词扩展<br/>1.3 简化复杂表达
    Rewrite Query->>Intention Recognize: 发送改写后Query
    
    Note over Intention Recognize: 步骤2: 意图分析
    Intention Recognize->>Intention Recognize: 2.1 多意图检测<br/>2.2 实体提取<br/>2.3 召回相关Func
    Intention Recognize->>async LLM: 发送Query和Func列表<br/>(触发ReAct推理)
    
    Note over async LLM: 步骤3: ReAct推理
    async LLM->>async LLM: 3.1 Thought: 分析用户意图<br/>3.2 Action: 选择Func组合<br/>3.3 Plan: 制定执行顺序
    async LLM->>Execute Action: 返回执行计划<br/>(Func序列+参数)
    
    loop 循环执行Func直到解决问题
        Note over Execute Action: 步骤4: 函数执行
        Execute Action->>Execute Action: 4.1 解析Func调用<br/>4.2 参数验证与填充
        Execute Action->>知识图谱: 执行Cypher查询
        
        知识图谱->>Execute Action: 返回查询结果
        
        Execute Action->>Result Eval: 传递中间结果
        
        Note over Result Eval: 步骤5: 结果评估
        Result Eval->>Result Eval: 5.1 检查完整性<br/>5.2 评估相关性<br/>5.3 判断是否继续
        
        alt 结果不完整/需要更多信息
            Result Eval->>async LLM: 请求下一步决策<br/>(当前结果+问题状态)
            async LLM->>async LLM: Thought: 分析当前状态<br/>Action: 选择下一个Func
            async LLM->>Execute Action: 返回新Func调用
        else 结果完整/问题解决
            结果评估模块->>异步LLM: 发送最终结果
        end
    end
    
    Note over async LLM: 步骤6: 答案生成
    async LLM->>async LLM: 6.1 整合所有结果<br/>6.2 生成自然语言<br/>6.3 添加解释说明
    async LLM->>用户: 返回最终答案
    
    Note right of async LLM: ReAct循环示例:<br/>Thought→Action→Observation→...<br/>直到问题解决
```


---

## 1. 各模块拆解

### 1.3 各模块响应时间


```mermaid
gantt
    title 列车查询系统处理流程时间线
    dateFormat  HH:mm
    axisFormat %H:%M
    
    section 用户交互
    用户输入查询     :00:00, 10s
    显示结果        :00:20, 5s
    
    section 意图识别
    文本预处理      :00:02, 3s
    意图分类        :00:05, 5s
    参数提取        :00:10, 5s
    
    section 查询处理
    构建Cypher查询  :00:15, 8s
    执行数据库查询  :00:18, 7s
    
    section 结果处理
    数据格式化      :00:25, 5s
    计算处理        :00:27, 8s
    生成自然语言    :00:30, 10s
```

### 1.2 IF LOOP

```mermaid
graph TD
    A[_evaluate_result] --> B[iteration_count++]
    B --> C{达到最大迭代?}
    C -->|是| D[停止: 达到最大迭代次数，并进行结果总结]
    C -->|否| E{Func Call执行结果}
    E -->|无结果| F[返回ReThink重新执行]
    E -->|有结果| G{是否有子查询?}
    G -->|是| H[评估当前子查询]
    H --> I{当前子查询结果是否满意?}
    I -->|是| J[切换到下一子查询]
    J --> K{所有子查询是否满意?}
    K -->|是| L[停止: 标记所有子查询已完成]
    K -->|否| M[选中子查询重回ReThink模块]
    I -->|否| N[重回ReThink模块, 并标记当前子查询未完成]
    G -->|否| O[评估整体查询]
    O --> P[根据评估结果决定后续流程]
```

## 2. 遇到的挑战及解决方案

### 2.1 Query重写模块


### 2.2 意图识别模块


### 2.3 ReThink模块


### 2.4 Func Call 执行模块


### 2.5 完成度评估模块


### 2.6 Agent记忆问题


### 2.7 前端可视化