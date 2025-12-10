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
__all__ = ["kg_system"] # 对外部导出使用

@tool
def search_trains_by_station(station_name: str) -> str:
    """
    根据车站名称查询经过该车站的列车
    
    Args:
        station_name: 车站名称（如：乌鲁木齐、郑州）
    
    Returns:
        JSON格式的列车信息列表
    """
    query = """
    MATCH (t:Train)-[:DEPARTS_FROM|ARRIVES_AT]->(s:Station)
    WHERE s.station_name CONTAINS $station_name
    RETURN DISTINCT t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间,
           s.station_name as 关联车站,
           s.station_type as 车站类型
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {"station_name": station_name})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
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

@tool
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

@tool
def search_trains_by_time_range(start_time: str, end_time: str) -> str:
    """
    查询指定时间范围内的列车
    
    Args:
        start_time: 开始时间（格式：HH:MM，如：00:00）
        end_time: 结束时间（格式：HH:MM，如：01:00）
    
    Returns:
        JSON格式的列车信息
    """
    query = """
    MATCH (t:Train)
    WHERE t.departure_time >= $start_time AND t.departure_time <= $end_time
    RETURN t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {
        "start_time": start_time,
        "end_time": end_time
    })
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def search_trains_by_train_type(train_type: str) -> str:
    """
    根据列车类型查询列车
    
    Args:
        train_type: 列车类型（如：K、Z、T、D）
    
    Returns:
        JSON格式的列车信息
    """
    query = """
    MATCH (t:Train)
    WHERE t.train_number STARTS WITH $train_type
    RETURN t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {"train_type": train_type})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_station_info(station_name: str) -> str:
    """
    获取车站的详细信息
    
    Args:
        station_name: 车站名称
    
    Returns:
        JSON格式的车站信息
    """
    query = """
    MATCH (s:Station {station_name: $station_name})
    OPTIONAL MATCH (t:Train)-[:DEPARTS_FROM]->(s)
    WITH s, collect(DISTINCT t.train_number) as departures
    OPTIONAL MATCH (t2:Train)-[:ARRIVES_AT]->(s)
    WITH s, departures, collect(DISTINCT t2.train_number) as arrivals
    RETURN s.station_name as 车站名称,
           s.station_type as 车站类型,
           departures as 始发列车,
           arrivals as 到达列车,
           size(departures) + size(arrivals) as 总车次
    """
    
    results = kg_system.run_query(query, {"station_name": station_name})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_waiting_hall_info(hall_name: str) -> str:
    """
    获取候车厅的详细信息
    
    Args:
        hall_name: 候车厅名称
    
    Returns:
        JSON格式的候车厅信息
    """
    query = """
    MATCH (h:WaitingHall {hall_name: $hall_name})
    MATCH (t:Train)-[:WAITS_AT]->(h)
    RETURN h.hall_name as 候车厅名称,
           collect(DISTINCT t.train_number) as 列车车次,
           count(DISTINCT t) as 列车数量
    """
    
    results = kg_system.run_query(query, {"hall_name": hall_name})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_platform_info(platform_number: str) -> str:
    """
    获取站台的详细信息
    
    Args:
        platform_number: 站台编号
    
    Returns:
        JSON格式的站台信息
    """
    query = """
    MATCH (p:Platform {platform_number: $platform_number})
    MATCH (t:Train)-[:STOPS_AT]->(p)
    RETURN p.platform_number as 站台编号,
           collect(DISTINCT t.train_number) as 列车车次,
           count(DISTINCT t) as 列车数量
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {"platform_number": platform_number})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_ticket_gate_info(gate_number: str) -> str:
    """
    获取检票口的详细信息
    
    Args:
        gate_number: 检票口编号
    
    Returns:
        JSON格式的检票口信息
    """
    query = """
    MATCH (g:TicketGate {gate_number: $gate_number})
    MATCH (t:Train)-[:CHECKS_AT]->(g)
    RETURN g.gate_number as 检票口编号,
           collect(DISTINCT t.train_number) as 列车车次,
           count(DISTINCT t) as 列车数量
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, {"gate_number": gate_number})
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_all_stations() -> str:
    """
    获取所有车站的列表
    
    Returns:
        JSON格式的车站列表
    """
    query = """
    MATCH (s:Station)
    RETURN s.station_name as 车站名称,
           s.station_type as 车站类型
    ORDER BY s.station_name
    """
    
    results = kg_system.run_query(query)
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_all_trains() -> str:
    """
    获取所有列车的列表
    
    Returns:
        JSON格式的列车列表
    """
    query = """
    MATCH (t:Train)
    RETURN t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query)
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def search_trains_by_multiple_conditions(
    departure_station: Optional[str] = None,
    arrival_station: Optional[str] = None,
    train_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> str:
    """
    根据多个条件组合查询列车
    
    Args:
        departure_station: 出发站
        arrival_station: 到达站
        train_type: 列车类型
        start_time: 开始时间
        end_time: 结束时间
    
    Returns:
        JSON格式的查询结果
    """
    # 构建动态查询
    query_parts = ["MATCH (t:Train)"]
    where_conditions = []
    parameters = {}
    
    if departure_station:
        query_parts.append("MATCH (t)-[:DEPARTS_FROM]->(dep:Station)")
        where_conditions.append("dep.station_name = $departure_station")
        parameters["departure_station"] = departure_station
    
    if arrival_station:
        query_parts.append("MATCH (t)-[:ARRIVES_AT]->(arr:Station)")
        where_conditions.append("arr.station_name = $arrival_station")
        parameters["arrival_station"] = arrival_station
    
    if train_type:
        where_conditions.append("t.train_number STARTS WITH $train_type")
        parameters["train_type"] = train_type
    
    if start_time:
        where_conditions.append("t.departure_time >= $start_time")
        parameters["start_time"] = start_time
    
    if end_time:
        where_conditions.append("t.departure_time <= $end_time")
        parameters["end_time"] = end_time
    
    # 构建完整查询
    query = " ".join(query_parts)
    if where_conditions:
        query += " WHERE " + " AND ".join(where_conditions)
    
    query += """
    RETURN DISTINCT t.train_number as 车次,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间
    ORDER BY t.departure_time
    """
    
    results = kg_system.run_query(query, parameters)
    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def get_current_date(format_type: str = "date") -> str:
    """获取当前日期和时间
    
    Args:
        format_type: 返回格式类型
            - "date": 返回日期 (YYYY-MM-DD)
            - "datetime": 返回日期时间 (YYYY-MM-DD HH:MM:SS)
            - "time": 返回时间 (HH:MM:SS)
            - "timestamp": 返回时间戳
            - "weekday": 返回星期几
            - "full": 返回完整信息
    
    Returns:
        JSON格式的日期时间信息
    """
    now = datetime.now()
    
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日"
    }
    
    result = {}
    
    if format_type == "date":
        result = {
            "date": now.strftime("%Y-%m-%d"),
            "year": now.year,
            "month": now.month,
            "day": now.day
        }
    elif format_type == "datetime":
        result = {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S")
        }
    elif format_type == "time":
        result = {
            "time": now.strftime("%H:%M:%S"),
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second
        }
    elif format_type == "timestamp":
        result = {
            "timestamp": int(now.timestamp()),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S")
        }
    elif format_type == "weekday":
        result = {
            "weekday": weekday_map[now.weekday()],
            "weekday_number": now.weekday(),
            "date": now.strftime("%Y-%m-%d")
        }
    elif format_type == "full":
        result = {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": weekday_map[now.weekday()],
            "weekday_number": now.weekday(),
            "timestamp": int(now.timestamp())
        }
    else:
        # 默认返回日期
        result = {
            "date": now.strftime("%Y-%m-%d"),
            "year": now.year,
            "month": now.month,
            "day": now.day
        }
    
    return json.dumps(result, ensure_ascii=False, indent=2)

@tool
def get_local_cite_information(user_id: str) -> str:
    """获取用户当前所在城市
    
    Args:
        user_id (str, optional): 用户唯一标识，用于个性化定位
        
    Returns:
        str: 城市名称
    """
    return "北京"

@tool
def get_local_city_station(city_name: str, station_type: Optional[str]) -> List[str]:
    """获取指定城市的所有火车站信息
    
    Args:
        city_name (str): 城市名称，如"北京"
        station_type (str, optional): 站点类型过滤，如"高铁站"、"火车站"
        
    Returns:
        Dict: 城市站点列表，包含车站名称
    """
    return ["北京", "北京西", "北京南"]

TOOLS = [
    search_trains_by_station,
    get_train_details,
    find_trains_between_stations,
    search_trains_by_time_range,
    search_trains_by_train_type,
    get_station_info,
    get_waiting_hall_info,
    get_platform_info,
    get_ticket_gate_info,
    get_all_stations,
    get_all_trains,
    search_trains_by_multiple_conditions,
    get_current_date
]