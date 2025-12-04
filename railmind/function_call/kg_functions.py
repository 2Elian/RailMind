# kg_functions.py
import json
from typing import Dict, List, Optional, Any
from langchain.tools import tool
from neo4j import GraphDatabase
import pandas as pd

class TrainKGQuerySystem:
    """列车知识图谱查询系统"""
    
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="123456"):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._ensure_constraints()
    
    def _ensure_constraints(self):
        """确保数据库约束"""
        with self.driver.session() as session:
            # 创建唯一性约束
            session.run("CREATE CONSTRAINT train_id_unique IF NOT EXISTS FOR (t:Train) REQUIRE t.train_id IS UNIQUE")
            session.run("CREATE CONSTRAINT station_id_unique IF NOT EXISTS FOR (s:Station) REQUIRE s.station_id IS UNIQUE")
            session.run("CREATE CONSTRAINT hall_id_unique IF NOT EXISTS FOR (h:WaitingHall) REQUIRE h.hall_id IS UNIQUE")
            session.run("CREATE CONSTRAINT gate_id_unique IF NOT EXISTS FOR (g:TicketGate) REQUIRE g.gate_id IS UNIQUE")
            session.run("CREATE CONSTRAINT platform_id_unique IF NOT EXISTS FOR (p:Platform) REQUIRE p.platform_id IS UNIQUE")
    
    def close(self):
        """关闭数据库连接"""
        self.driver.close()
    
    def run_query(self, cypher_query: str, parameters: Dict = None):
        """执行Cypher查询"""
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters or {})
            return [dict(record) for record in result]