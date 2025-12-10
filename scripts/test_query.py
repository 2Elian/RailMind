"""
批量测试查询脚本
向普通模式接口发送测试数据并记录结果
"""
import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Any

API_BASE_URL = "http://localhost:8000"
USER_ID = "test_user"
SESSION_ID = None  # None会自动创建新会话

with open("/data/lzm/AgentDev/RailMind/data/qa.json", "r", encoding="utf-8") as f:
    TEST_DATA = json.load(f)

def create_session() -> str:
    """创建新会话"""
    print("创建新会话...")
    response = requests.post(
        f"{API_BASE_URL}/api/session",
        json={"user_id": USER_ID}
    )
    response.raise_for_status()
    session_id = response.json()["session_id"]
    print(f"会话创建成功: {session_id}\n")
    return session_id


def query_api(question: str, session_id: str) -> Dict[str, Any]:
    """发送查询请求"""
    response = requests.post(
        f"{API_BASE_URL}/api/query",
        json={
            "query": question,
            "user_id": USER_ID,
            "session_id": session_id
        },
        timeout=240  # 4分钟超时
    )
    response.raise_for_status()
    return response.json()


def run_batch_test(test_data: List[Dict], use_same_session: bool = True):
    """
    批量运行测试
    
    Args:
        test_data: 测试数据列表
        use_same_session: 是否使用同一个会话（默认True）
    """
    results = []
    start_time = datetime.now()
    
    print("=" * 80)
    print(f"🚀 开始批量测试")
    print(f"📊 测试数量: {len(test_data)}")
    print(f"🕐 开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    session_id = create_session() if use_same_session else None
    
    for idx, item in enumerate(test_data, 1):
        question_id = item["id"]
        question = item["question"]
        expected_answer = item["answer"]
        question_type = item["question_type"]
        
        print(f"📝 [{idx}/{len(test_data)}] 测试问题: {question_id}")
        print(f"   问题: {question}")
        print(f"   类型: {question_type}")
        print(f"   预期答案: {expected_answer}")
        
        try:
            if not use_same_session:
                session_id = create_session()
            
            # 发送请求
            query_start = time.time()
            response = query_api(question, session_id)
            query_time = time.time() - query_start
            
            # 提取结果
            actual_answer = response.get("answer", "")
            success = response.get("success", False)
            metadata = response.get("metadata", {})
            iterations = metadata.get("iterations", 0)
            functions_used = metadata.get("functions_used", 0)
            error = metadata.get("error")
            
            # 记录结果
            result = {
                "id": question_id,
                "question": question,
                "question_type": question_type,
                "expected_answer": expected_answer,
                "actual_answer": actual_answer,
                "success": success,
                "error": error,
                "iterations": iterations,
                "functions_used": functions_used,
                "query_time": round(query_time, 2),
                "timestamp": datetime.now().isoformat()
            }
            results.append(result)
            
            # 打印结果
            if success and not error:
                print(f"   ✅ 成功 | 耗时: {query_time:.2f}s | 迭代: {iterations} | 函数: {functions_used}")
                print(f"   💬 Agent答案: {actual_answer[:100]}{'...' if len(actual_answer) > 100 else ''}")
            else:
                print(f"   ❌ 失败 | 错误: {error}")
            
        except requests.exceptions.Timeout:
            print(f"   ⏰ 超时 | 请求超过120秒")
            results.append({
                "id": question_id,
                "question": question,
                "error": "请求超时",
                "success": False
            })
        except Exception as e:
            print(f"   ❌ 异常 | {str(e)}")
            results.append({
                "id": question_id,
                "question": question,
                "error": str(e),
                "success": False
            })
        
        print()
        
        # 间隔1秒，避免过快请求
        if idx < len(test_data):
            time.sleep(1)
    
    # 测试完成
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    print("=" * 80)
    print("📊 测试完成统计")
    print("=" * 80)
    print(f"🕐 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  总耗时: {total_time:.2f}秒")
    print(f"📈 成功数量: {sum(1 for r in results if r.get('success', False))}/{len(results)}")
    print(f"📉 失败数量: {sum(1 for r in results if not r.get('success', False))}/{len(results)}")
    
    if results:
        avg_time = sum(r.get('query_time', 0) for r in results if 'query_time' in r) / len(results)
        avg_iterations = sum(r.get('iterations', 0) for r in results if 'iterations' in r) / len(results)
        print(f"⏰ 平均响应时间: {avg_time:.2f}秒")
        print(f"🔄 平均迭代次数: {avg_iterations:.1f}")
    
    # 保存结果
    output_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 结果已保存到: {output_file}")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    use_same_session=False
    run_batch_test(TEST_DATA, use_same_session=use_same_session)
