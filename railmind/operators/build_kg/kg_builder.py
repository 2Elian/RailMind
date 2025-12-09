import pandas as pd
from py2neo import Graph, Node, Relationship, NodeMatcher
import re
from datetime import datetime

NEO4J_URI = "bolt://172.16.107.15:7687"
NEO4J_USER = "neo4j" 
NEO4J_PASSWORD = "MyStrongPassword123"

class TrainKnowledgeGraph:
    def __init__(self):
        try:
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.matcher = NodeMatcher(self.graph)
        except Exception as e:
            print(f"连接Neo4j数据库失败: {e}")
            raise
    
    def clear_database(self):
        try:
            self.graph.delete_all()
            print("已清空数据库")
        except Exception as e:
            print(f"清空数据库失败: {e}")
    
    def read_excel_data(self, file_path):
        try:
            df = pd.read_excel(file_path)
            print(f"成功读取数据，共{len(df)}条记录")
            return df
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return None
    
    def create_nodes_and_relationships(self, df):
        created_nodes = {}
        
        for idx, row in df.iterrows():
            try:
                train_number = str(row['车次']).strip()
                # 作为唯一性约束的key
                train_key = f"train_{train_number.replace('/', '_')}_{str(row['开点'])}"
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
                    print(f"创建列车节点: {train_number} ({row['开点']})")
                else:
                    train_node = created_nodes[train_key]
                
                departure_station = str(row['始发站']).strip()
                departure_key = f"station_{departure_station}_{str(row['开点'])}_{str(row['到点'])}_{str(row['检票口'])}_{str(row['站台'])}"
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
                
                arrival_station = str(row['终到站']).strip()
                arrival_key = f"station_{arrival_station}_{str(row['开点'])}_{str(row['到点'])}_{str(row['检票口'])}_{str(row['站台'])}"
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

                waiting_halls = str(row['候车厅']).split('，')
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
                        waits_at = Relationship(train_node, "WAITS_AT", hall_node)
                        self.graph.create(waits_at)
                
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

                departs_from = Relationship(train_node, "DEPARTS_FROM", departure_node,
                                        departure_time=str(row['开点']))
                self.graph.create(departs_from)
                
                arrives_at = Relationship(train_node, "ARRIVES_AT", arrival_node,
                                        arrival_time=str(row['到点']))
                self.graph.create(arrives_at)
                
                checks_at = Relationship(train_node, "CHECKS_AT", gate_node)
                self.graph.create(checks_at)
                
                stops_at = Relationship(train_node, "STOPS_AT", platform_node)
                self.graph.create(stops_at)
                
            except Exception as e:
                print(f"处理第{idx+1}行数据时出错: {e}")
                raise


def main():
    kg = TrainKnowledgeGraph()
    
    kg.clear_database()
    excel_path = "/data/lzm/AgentDev/RailMind/data/raw_data.xlsx" 
    df = kg.read_excel_data(excel_path)
    kg.create_nodes_and_relationships(df)

if __name__ == "__main__":
    main()