import pandas as pd
from py2neo import Graph, Node, Relationship, NodeMatcher
import re
from datetime import datetime

# Neo4j数据库连接配置
NEO4J_URI = "bolt://172.16.107.15:7687"  # 默认URI
NEO4J_USER = "neo4j"  # 默认用户名
NEO4J_PASSWORD = "MyStrongPassword123"  # 请替换为您的密码

class TrainKnowledgeGraph:
    def __init__(self):
        """初始化Neo4j连接"""
        try:
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.matcher = NodeMatcher(self.graph)
            print("成功连接到Neo4j数据库")
        except Exception as e:
            print(f"连接Neo4j数据库失败: {e}")
            raise
    
    def clear_database(self):
        """清空现有数据"""
        try:
            self.graph.delete_all()
            print("已清空数据库")
        except Exception as e:
            print(f"清空数据库失败: {e}")
    
    def read_excel_data(self, file_path):
        """读取Excel数据"""
        try:
            df = pd.read_excel(file_path)
            print(f"成功读取数据，共{len(df)}条记录")
            return df
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return None
    
    def create_nodes_and_relationships(self, df):
        """
        创建节点和关系
        """
        created_nodes = {}  # 记录已创建的节点，避免重复
        
        for idx, row in df.iterrows():
            try:
                # 清理车次名称
                train_number = str(row['车次']).strip()
                train_key = f"train_{train_number.replace('/', '_')}"
                
                # 1. 创建或获取列车节点
                if train_key not in created_nodes:
                    train_node = Node(
                        "Train",
                        train_id=train_key,
                        train_number=train_number,
                        departure_time=str(row['开点']),
                        arrival_time=str(row['到点'])
                    )
                    self.graph.create(train_node)
                    created_nodes[train_key] = train_node
                    print(f"创建列车节点: {train_number}")
                else:
                    train_node = created_nodes[train_key]
                
                # 2. 创建或获取始发站节点
                departure_station = str(row['始发站']).strip()
                departure_key = f"station_{departure_station}"
                
                if departure_key not in created_nodes:
                    departure_node = Node(
                        "Station",
                        station_id=departure_key,
                        station_name=departure_station,
                        station_type="Departure"
                    )
                    self.graph.create(departure_node)
                    created_nodes[departure_key] = departure_node
                else:
                    departure_node = created_nodes[departure_key]
                
                # 3. 创建或获取终到站节点
                arrival_station = str(row['终到站']).strip()
                arrival_key = f"station_{arrival_station}"
                
                if arrival_key not in created_nodes:
                    arrival_node = Node(
                        "Station",
                        station_id=arrival_key,
                        station_name=arrival_station,
                        station_type="Arrival"
                    )
                    self.graph.create(arrival_node)
                    created_nodes[arrival_key] = arrival_node
                else:
                    arrival_node = created_nodes[arrival_key]
                
                # 4. 创建列车与车站的关系
                # 始发关系
                departs_from = Relationship(
                    train_node, "DEPARTS_FROM", departure_node,
                    departure_time=str(row['开点'])
                )
                self.graph.create(departs_from)
                
                # 终到关系
                arrives_at = Relationship(
                    train_node, "ARRIVES_AT", arrival_node,
                    arrival_time=str(row['到点'])
                )
                self.graph.create(arrives_at)
                
                # 5. 处理候车厅（可能有多个）
                waiting_halls = str(row['候车厅']).split('，')  # 使用中文逗号分割
                for hall_name in waiting_halls:
                    hall_name = hall_name.strip()
                    if hall_name:
                        hall_key = f"hall_{hall_name}"
                        
                        if hall_key not in created_nodes:
                            hall_node = Node(
                                "WaitingHall",
                                hall_id=hall_key,
                                hall_name=hall_name
                            )
                            self.graph.create(hall_node)
                            created_nodes[hall_key] = hall_node
                        else:
                            hall_node = created_nodes[hall_key]
                        
                        # 列车-候车厅关系
                        waits_at = Relationship(
                            train_node, "WAITS_AT", hall_node
                        )
                        self.graph.create(waits_at)
                
                # 6. 创建检票口节点
                ticket_gate = str(row['检票口']).strip()
                gate_key = f"gate_{ticket_gate}"
                
                if gate_key not in created_nodes:
                    gate_node = Node(
                        "TicketGate",
                        gate_id=gate_key,
                        gate_number=ticket_gate
                    )
                    self.graph.create(gate_node)
                    created_nodes[gate_key] = gate_node
                else:
                    gate_node = created_nodes[gate_key]
                
                # 列车-检票口关系
                checks_at = Relationship(
                    train_node, "CHECKS_AT", gate_node
                )
                self.graph.create(checks_at)
                
                # 7. 创建站台节点
                platform = str(row['站台']).strip()
                platform_key = f"platform_{platform}"
                
                if platform_key not in created_nodes:
                    platform_node = Node(
                        "Platform",
                        platform_id=platform_key,
                        platform_number=platform
                    )
                    self.graph.create(platform_node)
                    created_nodes[platform_key] = platform_node
                else:
                    platform_node = created_nodes[platform_key]
                
                # 列车-站台关系
                stops_at = Relationship(
                    train_node, "STOPS_AT", platform_node
                )
                self.graph.create(stops_at)
                
                print(f"已处理列车: {train_number}")
                
            except Exception as e:
                print(f"处理第{idx+1}行数据时出错: {e}")
                continue
    
    def run_query(self, cypher_query):
        """执行Cypher查询"""
        try:
            result = self.graph.run(cypher_query).data()
            return result
        except Exception as e:
            print(f"查询执行失败: {e}")
            return None
    
    def display_statistics(self):
        """显示数据库统计信息"""
        queries = [
            "MATCH (n) RETURN labels(n) as node_type, count(*) as count",
            "MATCH ()-[r]->() RETURN type(r) as relationship_type, count(*) as count",
            "MATCH (t:Train) RETURN t.train_number as train, count(*) as train_count",
            "MATCH (s:Station) RETURN s.station_name as station, count(*) as station_count"
        ]
        
        print("\n=== 知识图谱统计信息 ===")
        for i, query in enumerate(queries, 1):
            print(f"\n查询 {i}:")
            results = self.run_query(query)
            if results:
                for row in results:
                    print(f"  {row}")
    
    def search_trains_by_station(self, station_name):
        """查询经过指定车站的列车"""
        query = f"""
        MATCH (t:Train)-[:DEPARTS_FROM|ARRIVES_AT]->(s:Station)
        WHERE s.station_name CONTAINS '{station_name}'
        RETURN DISTINCT t.train_number as train_number,
               t.departure_time as departure,
               t.arrival_time as arrival
        ORDER BY t.departure_time
        """
        return self.run_query(query)
    
    def search_trains_by_time_range(self, start_time, end_time):
        """查询指定时间范围内的列车"""
        query = f"""
        MATCH (t:Train)
        WHERE t.departure_time >= '{start_time}' AND t.departure_time <= '{end_time}'
        RETURN t.train_number as train_number,
               t.departure_time as departure,
               t.arrival_time as arrival
        ORDER BY t.departure_time
        """
        return self.run_query(query)
    
    def visualize_simple_graph(self):
        """生成简单的Cypher查询用于可视化"""
        print("\n=== 可视化查询 ===")
        print("在Neo4j Browser中运行以下查询进行可视化：")
        
        # 查询1：显示所有节点和关系
        print("\n1. 显示所有节点和关系:")
        print("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50")
        
        # 查询2：显示列车和车站
        print("\n2. 显示列车和车站:")
        print("MATCH (t:Train)-[r:DEPARTS_FROM|ARRIVES_AT]->(s:Station) RETURN t, r, s")
        
        # 查询3：显示列车完整路径
        print("\n3. 显示列车完整路径:")
        print("""
        MATCH (t:Train)-[:DEPARTS_FROM]->(s1:Station)
        MATCH (t)-[:ARRIVES_AT]->(s2:Station)
        MATCH (t)-[:WAITS_AT]->(h:WaitingHall)
        MATCH (t)-[:CHECKS_AT]->(g:TicketGate)
        MATCH (t)-[:STOPS_AT]->(p:Platform)
        RETURN t.train_number, s1.station_name, s2.station_name,
               h.hall_name, g.gate_number, p.platform_number
        """)


def main():
    """主函数"""
    # 创建知识图谱实例
    kg = TrainKnowledgeGraph()
    
    # 清空数据库（可选）
    kg.clear_database()
    
    # 读取Excel数据
    # 注意：请将以下路径替换为您的Excel文件路径
    excel_path = "./raw_data.xlsx"  # 或 "train_schedule.csv"
    
    # 如果没有Excel文件，可以使用提供的示例数据创建DataFrame
    # sample_data = {
    #     '车次': ['K4547/6', 'Z362', 'T308', 'D218', 'K178', 'T198'],
    #     '始发站': ['成都西', '乌鲁木齐', '乌鲁木齐', '兰州', '西宁', '乌鲁木齐'],
    #     '终到站': ['佳木斯', '南通', '南昌', '上海', '郑州', '郑州'],
    #     '到点': ['23:40', '0:10', '0:16', '0:42', '0:48', '0:55'],
    #     '开点': ['0:12', '0:21', '0:28', '0:53', '1:02', '1:10'],
    #     '候车厅': ['综合候乘中心，高架候车区西区', '综合候乘中心，高架候车区西区', 
    #              '综合候乘中心，高架候车区西区', '综合候乘中心，高架候车区西区',
    #              '综合候乘中心，高架候车区西区', '综合候乘中心，高架候车区西区'],
    #     '检票口': ['1B', '5B', '1A', '2A', '8B', '7A'],
    #     '站台': ['2', '5', '5', '1', '2', '5']
    # }
    
    df = kg.read_excel_data(excel_path)
    print("使用示例数据创建DataFrame")
    
    # 创建节点和关系
    kg.create_nodes_and_relationships(df)
    
    # 显示统计信息
    kg.display_statistics()
    
    # 示例查询
    print("\n=== 示例查询 ===")
    
    # 查询1：查找经过乌鲁木齐的列车
    print("\n1. 经过乌鲁木齐的列车:")
    result = kg.search_trains_by_station("乌鲁木齐")
    if result:
        for row in result:
            print(f"  车次: {row['train_number']}, 发车时间: {row['departure']}")
    
    # 查询2：查找时间范围内的列车
    print("\n2. 00:00到01:00之间的列车:")
    result = kg.search_trains_by_time_range("0:00", "1:00")
    if result:
        for row in result:
            print(f"  车次: {row['train_number']}, 发车时间: {row['departure']}")
    
    # 可视化查询
    kg.visualize_simple_graph()
    
    # 更多复杂查询示例
    print("\n=== 复杂查询示例 ===")
    
    # 查询所有从乌鲁木齐出发的列车
    query = """
    MATCH (t:Train)-[:DEPARTS_FROM]->(s:Station {station_name: '乌鲁木齐'})
    MATCH (t)-[:ARRIVES_AT]->(arr:Station)
    MATCH (t)-[:WAITS_AT]->(h:WaitingHall)
    MATCH (t)-[:CHECKS_AT]->(g:TicketGate)
    MATCH (t)-[:STOPS_AT]->(p:Platform)
    RETURN t.train_number as 车次,
           s.station_name as 始发站,
           arr.station_name as 终到站,
           t.departure_time as 发车时间,
           t.arrival_time as 到达时间,
           collect(DISTINCT h.hall_name) as 候车厅,
           g.gate_number as 检票口,
           p.platform_number as 站台
    ORDER BY t.departure_time
    """
    
    print("从乌鲁木齐出发的列车:")
    results = kg.run_query(query)
    if results:
        for row in results:
            print(f"  车次: {row['车次']}, 目的地: {row['终到站']}, 发车: {row['发车时间']}")
    
    print("\n知识图谱构建完成！")


if __name__ == "__main__":
    main()