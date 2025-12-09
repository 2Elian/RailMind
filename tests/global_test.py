import json
from typing import Optional, Dict, Any, List
from py2neo import Graph
import sys

# 配置数据库连接
class Neo4jConnector:
    def __init__(self, uri="bolt://172.16.107.15:7687", 
                 user="neo4j", password="MyStrongPassword123"):
        """
        初始化Neo4j连接
        
        Args:
            uri: Neo4j数据库地址，默认为 bolt://localhost:7687
            user: 用户名，默认为 neo4j
            password: 密码
        """
        try:
            self.graph = Graph(uri, auth=(user, password))
            print(f"成功连接到Neo4j数据库: {uri}")
            
            # 测试连接
            test_query = "RETURN '连接成功' AS message"
            result = self.graph.run(test_query)
            print(f"连接测试: {result.data()[0]['message']}")
            
        except Exception as e:
            print(f"连接Neo4j数据库失败: {e}")
            print("请检查:")
            print("1. Neo4j服务是否启动")
            print("2. 数据库地址、用户名、密码是否正确")
            print("3. 防火墙设置是否允许连接")
            sys.exit(1)
    
    def run_query(self, query: str, parameters: Dict = None) -> List[Dict]:
        """
        执行Cypher查询
        
        Args:
            query: Cypher查询语句
            parameters: 查询参数
        
        Returns:
            查询结果列表
        """
        try:
            if parameters is None:
                parameters = {}
            
            print(f"执行查询: {query}")
            print(f"查询参数: {parameters}")
            
            result = self.graph.run(query, parameters)
            records = [dict(record) for record in result]
            
            print(f"查询成功，返回 {len(records)} 条记录")
            return records
            
        except Exception as e:
            print(f"执行查询时出错: {e}")
            return []

# 初始化全局连接
try:
    # 根据你的实际配置修改这些参数
    kg_system = Neo4jConnector(
        uri="bolt://172.16.107.15:7687",  # 你的Neo4j地址
        user="neo4j",                     # 你的用户名
        password="MyStrongPassword123"               # 你的密码
    )
except:
    # 如果上面的配置失败，使用默认配置
    print("使用默认配置尝试连接...")
    kg_system = Neo4jConnector()

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
        train_type: 列车类型（如'G'表示高铁，'D'表示动车，'C'表示城际）
        start_time: 开始时间（格式: 'HH:MM'）
        end_time: 结束时间（格式: 'HH:MM'）
    
    Returns:
        JSON格式的查询结果
    """
    # 构建动态查询
    query_parts = ["MATCH (t:Train)"]
    where_conditions = []
    parameters = {}
    
    # 处理出发站
    if departure_station:
        query_parts.append("MATCH (t)-[:DEPARTS_FROM]->(dep:Station)")
        where_conditions.append("dep.station_name = $departure_station")
        parameters["departure_station"] = departure_station
    
    # 处理到达站
    if arrival_station:
        query_parts.append("MATCH (t)-[:ARRIVES_AT]->(arr:Station)")
        where_conditions.append("arr.station_name = $arrival_station")
        parameters["arrival_station"] = arrival_station
    
    # 处理列车类型
    if train_type:
        # 支持多种格式：G、D、C等
        where_conditions.append("t.train_number STARTS WITH $train_type")
        parameters["train_type"] = train_type
    
    # 处理时间范围
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
    
    # 优化查询，避免重复MATCH
    query = query.replace("MATCH (t:Train) MATCH (t)-[:DEPARTS_FROM]->(dep:Station)", 
                          "MATCH (t:Train)-[:DEPARTS_FROM]->(dep:Station)")
    query = query.replace("MATCH (t:Train) MATCH (t)-[:ARRIVES_AT]->(arr:Station)", 
                          "MATCH (t:Train)-[:ARRIVES_AT]->(arr:Station)")
    
    # 添加返回字段
    query += """
    RETURN DISTINCT 
        t.train_number as 车次,
        t.departure_time as 发车时间,
        t.arrival_time as 到达时间
    ORDER BY t.departure_time
    """
    
    print("=" * 60)
    print("构建的查询语句:")
    print(query)
    print("查询参数:")
    print(json.dumps(parameters, ensure_ascii=False, indent=2))
    print("=" * 60)
    
    # 执行查询
    results = kg_system.run_query(query, parameters)
    
    # 格式化结果
    if results:
        formatted_results = {
            "status": "success",
            "count": len(results),
            "conditions": {
                "departure_station": departure_station,
                "arrival_station": arrival_station,
                "train_type": train_type,
                "start_time": start_time,
                "end_time": end_time
            },
            "trains": results
        }
    else:
        formatted_results = {
            "status": "success",
            "count": 0,
            "message": "未找到符合条件的列车",
            "conditions": {
                "departure_station": departure_station,
                "arrival_station": arrival_station,
                "train_type": train_type,
                "start_time": start_time,
                "end_time": end_time
            },
            "trains": []
        }
    
    return json.dumps(formatted_results, ensure_ascii=False, indent=2)

def search_trains_with_full_info(
    departure_station: Optional[str] = None,
    arrival_station: Optional[str] = None,
    train_number: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    查询列车完整信息（包括候车厅、检票口、站台等）
    
    Args:
        departure_station: 出发站
        arrival_station: 到达站
        train_number: 列车车次
        limit: 返回结果数量限制
    
    Returns:
        JSON格式的查询结果
    """
    query_parts = []
    where_conditions = []
    parameters = {"limit": limit}
    
    # 基础查询
    base_query = """
    MATCH (t:Train)-[:DEPARTS_FROM]->(dep:Station)
    MATCH (t:Train)-[:ARRIVES_AT]->(arr:Station)
    OPTIONAL MATCH (t:Train)-[:WAITS_AT]->(wh:WaitingHall)
    OPTIONAL MATCH (t:Train)-[:CHECKS_AT]->(tg:TicketGate)
    OPTIONAL MATCH (t:Train)-[:STOPS_AT]->(p:Platform)
    """
    
    if departure_station:
        where_conditions.append("dep.station_name = $departure_station")
        parameters["departure_station"] = departure_station
    
    if arrival_station:
        where_conditions.append("arr.station_name = $arrival_station")
        parameters["arrival_station"] = arrival_station
    
    if train_number:
        where_conditions.append("t.train_number = $train_number")
        parameters["train_number"] = train_number
    
    # 构建完整查询
    query = base_query
    if where_conditions:
        query += "WHERE " + " AND ".join(where_conditions) + "\n"
    
    query += """
    RETURN 
        t.train_number as 车次,
        dep.station_name as 始发站,
        arr.station_name as 终到站,
        COLLECT(DISTINCT wh.hall_name) as 候车厅,
        COLLECT(DISTINCT tg.gate_number) as 检票口,
        COLLECT(DISTINCT p.platform_number) as 站台,
        t.departure_time as 发车时间,
        t.arrival_time as 到达时间
    ORDER BY t.departure_time
    LIMIT $limit
    """
    
    results = kg_system.run_query(query, parameters)
    
    # 格式化结果
    formatted_results = {
        "status": "success",
        "count": len(results),
        "trains": results
    }
    
    return json.dumps(formatted_results, ensure_ascii=False, indent=2)

def get_database_stats() -> str:
    """
    获取数据库统计信息
    
    Returns:
        JSON格式的统计信息
    """
    stats_query = """
    // 统计列车数量
    MATCH (t:Train)
    WITH COUNT(t) AS train_count
    
    // 统计车站数量
    MATCH (s:Station)
    WITH train_count, COUNT(s) AS station_count
    
    // 统计候车厅数量
    MATCH (wh:WaitingHall)
    WITH train_count, station_count, COUNT(wh) AS waiting_hall_count
    
    // 统计检票口数量
    MATCH (tg:TicketGate)
    WITH train_count, station_count, waiting_hall_count, COUNT(tg) AS ticket_gate_count
    
    // 统计站台数量
    MATCH (p:Platform)
    RETURN 
        train_count AS 列车数量,
        station_count AS 车站数量,
        waiting_hall_count AS 候车厅数量,
        ticket_gate_count AS 检票口数量,
        COUNT(p) AS 站台数量
    """
    
    results = kg_system.run_query(stats_query)
    
    stats = {
        "status": "success",
        "database_stats": results[0] if results else {},
        "timestamp": datetime.now().isoformat()
    }
    
    return json.dumps(stats, ensure_ascii=False, indent=2)

# 测试函数
def test_search_functions():
    """测试查询功能"""
    print("=" * 60)
    print("测试列车查询功能")
    print("=" * 60)
    
    # 测试1: 查询所有列车（限制10条）
    print("\n1. 查询所有列车（前10条）:")
    all_trains = search_trains_with_full_info(limit=10)
    print(all_trains[:500] + "..." if len(all_trains) > 500 else all_trains)
    
    # 测试2: 根据条件查询
    print("\n2. 查询北京南站出发的列车:")
    result = search_trains_by_multiple_conditions(
        departure_station="北京南站"
    )
    print(result[:500] + "..." if len(result) > 500 else result)
    
    # 测试3: 查询特定时间段的列车
    print("\n3. 查询08:00-12:00之间的列车:")
    result = search_trains_by_multiple_conditions(
        start_time="08:00",
        end_time="12:00"
    )
    print(result[:500] + "..." if len(result) > 500 else result)
    
    # 测试4: 查询G字头列车
    print("\n4. 查询G字头列车:")
    result = search_trains_by_multiple_conditions(
        train_type="G"
    )
    print(result[:500] + "..." if len(result) > 500 else result)
    
    # 测试5: 组合条件查询
    print("\n5. 查询北京南站到上海虹桥的G字头列车:")
    result = search_trains_by_multiple_conditions(
        departure_station="北京南站",
        arrival_station="上海虹桥",
        train_type="G"
    )
    print(result[:500] + "..." if len(result) > 500 else result)
    
    # 测试6: 获取数据库统计
    print("\n6. 数据库统计信息:")
    stats = get_database_stats()
    print(stats)

# 交互式查询函数
def interactive_search():
    """交互式查询界面"""
    print("=" * 60)
    print("列车信息查询系统")
    print("=" * 60)
    
    while True:
        print("\n请选择查询方式:")
        print("1. 多条件组合查询")
        print("2. 查询列车完整信息")
        print("3. 查看数据库统计")
        print("4. 退出")
        
        choice = input("\n请输入选项 (1-4): ").strip()
        
        if choice == "1":
            print("\n请输入查询条件（不输入直接回车表示不限制）:")
            
            departure = input("出发站: ").strip() or None
            arrival = input("到达站: ").strip() or None
            train_type = input("列车类型（如G/D/C）: ").strip() or None
            start_time = input("开始时间（格式: HH:MM）: ").strip() or None
            end_time = input("结束时间（格式: HH:MM）: ").strip() or None
            
            result = search_trains_by_multiple_conditions(
                departure_station=departure,
                arrival_station=arrival,
                train_type=train_type,
                start_time=start_time,
                end_time=end_time
            )
            
            print("\n查询结果:")
            print(result)
            
        elif choice == "2":
            print("\n请输入查询条件:")
            
            departure = input("出发站: ").strip() or None
            arrival = input("到达站: ").strip() or None
            train_number = input("列车车次: ").strip() or None
            limit = input("返回数量限制（默认20）: ").strip()
            limit = int(limit) if limit.isdigit() else 20
            
            result = search_trains_with_full_info(
                departure_station=departure,
                arrival_station=arrival,
                train_number=train_number,
                limit=limit
            )
            
            print("\n查询结果:")
            print(result)
            
        elif choice == "3":
            result = get_database_stats()
            print("\n数据库统计:")
            print(result)
            
        elif choice == "4":
            print("感谢使用，再见！")
            break
            
        else:
            print("无效选项，请重新输入！")

# 主程序入口
if __name__ == "__main__":
    from datetime import datetime

    # 简单调用示例
    result = search_trains_by_multiple_conditions(
        departure_station="北京西",
        arrival_station="西安",
    )
    print(result)