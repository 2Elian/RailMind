"""
从 JSON 文件批量测试查询脚本
支持从外部 JSON 文件加载测试数据
支持并发执行
"""
import requests
import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

API_BASE_URL = "http://172.16.107.15:8000"
USER_ID = "test_user"


def load_test_data(file_path: str) -> List[Dict]:
    """从 JSON 文件加载测试数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key in ['data', 'questions', 'test_data', 'items']:
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = [data]
        
        print(f"成功加载 {len(data)} 条测试数据")
        return data
    except FileNotFoundError:
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 格式错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        sys.exit(1)


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
        timeout=120
    )
    response.raise_for_status()
    return response.json()


def run_batch_test(test_data: List[Dict], use_same_session: bool = True, output_dir: str = ".", max_workers: int = 1):
    """
    批量运行测试
    
    Args:
        test_data: 测试数据列表
        use_same_session: 是否使用同一个会话
        output_dir: 输出目录
        max_workers: 最大并发数（1为串行，>1为并发）
    """
    results = []
    start_time = datetime.now()
    
    print("=" * 80)
    print(f"🚀 开始批量测试")
    print(f"📊 测试数量: {len(test_data)}")
    print(f"🕐 开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 会话模式: {'同一会话' if use_same_session else '独立会话'}")
    print(f"⚡ 并发数: {max_workers} {'(串行)' if max_workers == 1 else '(并发)'}")
    print("=" * 80)
    print()
    
    session_id = create_session() if use_same_session else None
    
    # 添加线程锁用于打印和结果收集
    print_lock = threading.Lock()
    results_lock = threading.Lock()
    
    def process_single_question(idx_item):
        """处理单个问题"""
        idx, item = idx_item
        question_id = item.get("id", f"question_{idx}")
        question = item.get("question", "")
        expected_answer = item.get("answer", "")
        question_type = item.get("question_type", "unknown")
        
        if not question:
            with print_lock:
                print(f"⚠️  [{idx}/{len(test_data)}] 跳过：问题为空")
            return None
        
        with print_lock:
            print(f"📝 [{idx}/{len(test_data)}] ID: {question_id}")
            print(f"   问题: {question}")
            if expected_answer:
                print(f"   预期: {expected_answer[:80]}{'...' if len(expected_answer) > 80 else ''}")
        
        try:
            # 如果每个问题需要独立会话
            current_session_id = session_id
            if not use_same_session:
                current_session_id = create_session()
            
            query_start = time.time()
            response = query_api(question, current_session_id)
            query_time = time.time() - query_start
            
            actual_answer = response.get("answer", "")
            success = response.get("success", False)
            metadata = response.get("metadata", {})
            iterations = metadata.get("iterations", 0)
            functions_used = metadata.get("functions_used", 0)
            error = metadata.get("error")
            
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
                "session_id": current_session_id,
                "timestamp": datetime.now().isoformat(),
                "full_response": response
            }
            
            with print_lock:
                if success and not error:
                    print(f"   ✅ 成功 | {query_time:.2f}s | 迭代:{iterations} | 函数:{functions_used}")
                    print(f"   💬 回答: {actual_answer[:100]}{'...' if len(actual_answer) > 100 else ''}")
                else:
                    print(f"   ❌ 失败 | 错误: {error}")
                print()
            
            return result
            
        except requests.exceptions.Timeout:
            with print_lock:
                print(f"   ⏰ 超时")
                print()
            return {
                "id": question_id,
                "question": question,
                "error": "请求超时",
                "success": False,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            with print_lock:
                print(f"   ❌ 异常: {str(e)}")
                print()
            return {
                "id": question_id,
                "question": question,
                "error": str(e),
                "success": False,
                "timestamp": datetime.now().isoformat()
            }
    
    # 执行测试
    if max_workers == 1:
        # 串行执行
        for idx, item in enumerate(test_data, 1):
            result = process_single_question((idx, item))
            if result:
                results.append(result)
            if idx < len(test_data):
                time.sleep(1)  # 串行时添加延迟
    else:
        # 并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_single_question, (idx, item)): idx 
                      for idx, item in enumerate(test_data, 1)}
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    with results_lock:
                        results.append(result)
    
    # 统计
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    success_count = sum(1 for r in results if r.get('success', False))
    
    print("=" * 80)
    print("📊 测试完成统计")
    print("=" * 80)
    print(f"🕐 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  总耗时: {total_time:.2f}秒")
    print(f"📈 成功: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    print(f"📉 失败: {len(results)-success_count}/{len(results)}")
    
    if results:
        query_times = [r.get('query_time', 0) for r in results if 'query_time' in r]
        iterations = [r.get('iterations', 0) for r in results if 'iterations' in r]
        
        if query_times:
            print(f"⏰ 平均响应: {sum(query_times)/len(query_times):.2f}s")
            print(f"   最快: {min(query_times):.2f}s | 最慢: {max(query_times):.2f}s")
        
        if iterations:
            print(f"🔄 平均迭代: {sum(iterations)/len(iterations):.1f}")
    
    # 保存结果
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_path / f"test_results_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "total": len(results),
                "success": success_count,
                "failed": len(results) - success_count,
                "total_time": round(total_time, 2),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            },
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 结果已保存: {output_file}")
    print("=" * 80)
    
    return results


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python test_batch_query_from_file.py <json_file> [选项]")
        print("")
        print("选项:")
        print("  --new-session    每个问题使用独立会话")
        print("  --workers N      并发数（默认1为串行）")
        print("")
        print("示例:")
        print("  python test_batch_query_from_file.py test_data.json")
        print("  python test_batch_query_from_file.py test_data.json --workers 5")
        print("  python test_batch_query_from_file.py test_data.json --new-session --workers 3")
        sys.exit(1)
    
    json_file = sys.argv[1]
    use_same_session = "--new-session" not in sys.argv
    
    # 解析并发数
    max_workers = 1
    if "--workers" in sys.argv:
        try:
            workers_idx = sys.argv.index("--workers")
            max_workers = int(sys.argv[workers_idx + 1])
            if max_workers < 1:
                print("❌ 并发数必须大于等于1")
                sys.exit(1)
        except (IndexError, ValueError):
            print("❌ --workers 参数格式错误，应为: --workers N")
            sys.exit(1)
    
    print(f"📂 加载测试数据: {json_file}")
    test_data = load_test_data(json_file)
    
    run_batch_test(test_data, use_same_session=use_same_session, max_workers=max_workers)


if __name__ == "__main__":
    main()
