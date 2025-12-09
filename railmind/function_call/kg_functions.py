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
    
    def close(self):
        """关闭数据库连接"""
        self.driver.close()
    
    def run_query(self, cypher_query: str, parameters: Dict = None):
        """执行Cypher查询"""
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters or {})
            return [dict(record) for record in result]