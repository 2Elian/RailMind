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

def find_trains_between_stations(departure_station: str, arrival_station: str) -> str:
    """
    查询两个车站之间的直达列车
    
    Args:
        departure_station: 出发站名称
        arrival_station: 到达站名称
    
    Returns:
        JSON格式的列车信息
    """
    query = """
    MATCH (t:Train)-[:DEPARTS_FROM]->(dep:Station {station_name: $departure_station})
    MATCH (t)-[:ARRIVES_AT]->(arr:Station {station_name: $arrival_station})
    RETURN t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间,
           dep.station_name as 始发站,
           arr.station_name as 终到站
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {
        "departure_station": departure_station,
        "arrival_station": arrival_station
    })
    return json.dumps(results, ensure_ascii=False, indent=2)
res = find_trains_between_stations(
    departure_station = "北京西",
    arrival_station = "西安"
)
print(res)