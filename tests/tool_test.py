# train_query_functions.py
from langchain.tools import tool
from railmind.function_call import TrainKGQuerySystem
from typing import List, Dict, Optional
import json
from datetime import datetime

from railmind.config import get_settings

# TODO 因为后端都是异步接口 所以工具的话 可能得换成继承BaseTool 然后写同步和异步_run函数

setting = get_settings()
kg_system = TrainKGQuerySystem(uri=setting.neo4j_uri, user=setting.neo4j_user, password=setting.neo4j_password)

def get_train_details(train_number: str) -> str:
    """
    获取特定列车的完整详细信息
    
    Args:
        train_number: 列车车次（如：K178、T308）
    
    Returns:
        JSON格式的列车详细信息
    """
    query = """
    MATCH (t:Train {train_number: $train_number})-[:DEPARTS_FROM]->(dep:Station)
    MATCH (t)-[:ARRIVES_AT]->(arr:Station)
    OPTIONAL MATCH (t)-[:WAITS_AT]->(h:WaitingHall)
    OPTIONAL MATCH (t)-[:CHECKS_AT]->(g:TicketGate)
    OPTIONAL MATCH (t)-[:STOPS_AT]->(p:Platform)
    RETURN t.train_number as 车次,
           dep.station_name as 始发站,
           arr.station_name as 终到站,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间,
           collect(DISTINCT h.hall_name) as 候车厅,
           g.gate_number as 检票口,
           p.platform_number as 站台
    """
    
    results = kg_system.run_query(query, {"train_number": train_number})
    return json.dumps(results, ensure_ascii=False, indent=2)

res = get_train_details(
    train_number="K4547/6"
)
print(res)