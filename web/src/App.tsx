import React, { useState, useRef } from 'react';
import { api, QueryResponse, Thought, Action, Observation } from './api';
import { ReActTimeline } from './components/ReActTimeline';
import ReactMarkdown from 'react-markdown';

function App() {
  const [query, setQuery] = useState('');
  const [userId] = useState('default_user');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'raw'>('timeline');
  const [useStreaming, setUseStreaming] = useState(true); // 默认启用流式
  const eventSourceRef = useRef<EventSource | null>(null);

  // 实时流式数据
  const [streamThoughts, setStreamThoughts] = useState<Thought[]>([]);
  const [streamActions, setStreamActions] = useState<Action[]>([]);
  const [streamObservations, setStreamObservations] = useState<Observation[]>([]);

  // 渲染答案内容，支持 <think> 标签和 Markdown
  const renderAnswer = (answer: string) => {
    // 提取 <think> 标签内容
    const thinkRegex = /<think>([\s\S]*?)<\/think>/g;
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    while ((match = thinkRegex.exec(answer)) !== null) {
      // 添加 <think> 之前的内容
      if (match.index > lastIndex) {
        const beforeThink = answer.substring(lastIndex, match.index);
        parts.push(
          <ReactMarkdown key={`md-${lastIndex}`} className="prose prose-invert max-w-none">
            {beforeThink}
          </ReactMarkdown>
        );
      }

      // 添加 <think> 内容
      parts.push(
        <div key={`think-${match.index}`} className="my-4 bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-4">
          <div className="flex items-center space-x-2 mb-2">
            <svg className="w-4 h-4 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span className="text-sm font-semibold text-yellow-600">思考过程</span>
          </div>
          <ReactMarkdown className="prose prose-invert prose-sm max-w-none text-yellow-200/90">
            {match[1]}
          </ReactMarkdown>
        </div>
      );

      lastIndex = match.index + match[0].length;
    }

    // 添加剩余内容
    if (lastIndex < answer.length) {
      const remaining = answer.substring(lastIndex);
      parts.push(
        <ReactMarkdown key={`md-${lastIndex}`} className="prose prose-invert max-w-none">
          {remaining}
        </ReactMarkdown>
      );
    }

    return parts.length > 0 ? <div>{parts}</div> : (
      <ReactMarkdown className="prose prose-invert max-w-none">
        {answer}
      </ReactMarkdown>
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!query.trim()) {
      return;
    }

    // 关闭之前的连接
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setLoading(true);
    setResponse(null);
    setStreamThoughts([]);
    setStreamActions([]);
    setStreamObservations([]);

    try {
      let currentSessionId = sessionId;
      if (!currentSessionId) {
        const session = await api.createSession(userId);
        currentSessionId = session.session_id;
        setSessionId(currentSessionId);
      }

      const request = {
        query,
        user_id: userId,
        session_id: currentSessionId || undefined,
      };

      if (useStreaming) {
        // 使用流式查询
        eventSourceRef.current = api.queryStream(
          request,
          (thought) => {
            setStreamThoughts(prev => [...prev, thought]);
          },
          (action) => {
            setStreamActions(prev => [...prev, action]);
          },
          (observation) => {
            setStreamObservations(prev => [...prev, observation]);
          },
          (finalResponse) => {
            setResponse(finalResponse);
            setLoading(false);
          },
          (error) => {
            console.error('流式查询失败:', error);
            setLoading(false);
          }
        );
      } else {
        // 使用传统查询
        const result = await api.query(request);
        setResponse(result);
        setLoading(false);
      }
    } catch (error: any) {
      console.error('查询失败:', error);
      setLoading(false);
    }
  };

  const handleNewSession = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    setSessionId(null);
    setResponse(null);
    setQuery('');
    setStreamThoughts([]);
    setStreamActions([]);
    setStreamObservations([]);
  };

  return (
    <div className="min-h-screen bg-black">
      {/* Header */}
      <header className="border-b border-gray-800 bg-black/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-br from-gray-700 to-gray-900 rounded-lg flex items-center justify-center border border-gray-700">
                <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">RailMind-Agent</h1>
                <p className="text-xs text-gray-500">AI旅行向导：更智能的行程规划，更自在的体验。</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-full">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
                <span className="text-xs text-gray-400 font-medium">Online</span>
              </div>
              <button
                onClick={() => setUseStreaming(!useStreaming)}
                className={`px-3 py-1.5 text-xs font-medium rounded-full transition-all ${
                  useStreaming
                    ? 'bg-green-900/30 text-green-400 border border-green-800'
                    : 'bg-gray-800 text-gray-500 border border-gray-700'
                }`}
                title="切换查询模式"
              >
                {useStreaming ? '✨ 流式模式' : '⏱️ 普通模式'}
              </button>
              {sessionId && (
                <div className="text-xs text-gray-500">
                  Session: <span className="text-gray-400 font-mono">{sessionId.substring(0, 8)}...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left Panel - Input & Answer */}
          <div className="lg:col-span-2 space-y-6">
            {/* Query Input Card */}
            <div className="bg-zinc-900 border border-gray-800 rounded-xl p-6 shadow-2xl">
              <div className="flex items-center space-x-2 mb-4">
                <div className="w-1 h-6 bg-gray-600 rounded-full"></div>
                <h2 className="text-lg font-semibold text-white">输入查询</h2>
              </div>
              
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="例如：从北京到上海有哪些列车？"
                    className="w-full px-4 py-3 bg-black border border-gray-800 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-gray-600 focus:ring-1 focus:ring-gray-600 resize-none transition-all"
                    rows={4}
                    disabled={loading}
                  />
                </div>

                <div className="flex space-x-3">
                  <button
                    type="submit"
                    disabled={loading || !query.trim()}
                    className="flex-1 bg-white hover:bg-gray-100 text-black font-semibold py-3 px-6 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
                  >
                    {loading ? (
                      <span className="flex items-center justify-center">
                        <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        处理中...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center">
                        <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        发送查询
                      </span>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={handleNewSession}
                    className="bg-zinc-800 hover:bg-zinc-700 text-gray-300 font-semibold py-3 px-6 rounded-xl transition-all border border-gray-700"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                </div>
              </form>
            </div>

            {/* Answer Display Card */}
            {response && (
              <div className="bg-zinc-900 border border-gray-800 rounded-xl p-6 shadow-2xl">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-2">
                    <div className="w-1 h-6 bg-gray-600 rounded-full"></div>
                    <h2 className="text-lg font-semibold text-white">智能答案</h2>
                  </div>
                  <div className="flex items-center space-x-3 text-xs">
                    <span className="px-2 py-1 bg-zinc-800 text-gray-400 rounded-lg border border-gray-700">
                      {response.metadata.iterations} 次迭代
                    </span>
                    <span className="px-2 py-1 bg-zinc-800 text-gray-400 rounded-lg border border-gray-700">
                      {response.metadata.functions_used} 个函数
                    </span>
                  </div>
                </div>
                
                <div className="bg-zinc-800 border border-gray-700 rounded-xl p-5">
                  <div className="text-gray-200 leading-relaxed">
                    {renderAnswer(response.answer)}
                  </div>
                </div>

                {response.metadata.error && (
                  <div className="mt-4 bg-red-900/20 border border-red-800/50 rounded-xl p-4">
                    <div className="flex items-start space-x-2">
                      <svg className="w-5 h-5 text-red-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <div>
                        <p className="text-sm font-semibold text-red-400">错误</p>
                        <p className="text-sm text-red-400 mt-1">{response.metadata.error}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Panel - ReAct Process */}
          <div className="lg:col-span-3 bg-zinc-900 border border-gray-800 rounded-xl shadow-2xl">
            <div className="p-6 border-b border-gray-800">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="w-1 h-6 bg-gray-600 rounded-full"></div>
                  <h2 className="text-lg font-semibold text-white">ReAct 推理流程</h2>
                </div>
                
                <div className="flex space-x-2">
                  <button
                    onClick={() => setActiveTab('timeline')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      activeTab === 'timeline'
                        ? 'bg-white text-black'
                        : 'text-gray-500 hover:text-gray-300 hover:bg-zinc-800'
                    }`}
                  >
                    时间线
                  </button>
                  <button
                    onClick={() => setActiveTab('raw')}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      activeTab === 'raw'
                        ? 'bg-white text-black'
                        : 'text-gray-500 hover:text-gray-300 hover:bg-zinc-800'
                    }`}
                  >
                    原始数据
                  </button>
                </div>
              </div>
            </div>
            
            <div className="p-6 h-[calc(100vh-250px)] overflow-y-auto custom-scrollbar">
              {(response || streamThoughts.length > 0) ? (
                <>
                  {activeTab === 'timeline' ? (
                    <ReActTimeline
                      thoughts={useStreaming && !response ? streamThoughts : (response?.thoughts || [])}
                      actions={useStreaming && !response ? streamActions : (response?.actions || [])}
                      observations={useStreaming && !response ? streamObservations : (response?.observations || [])}
                    />
                  ) : (
                    <pre className="text-xs text-gray-400 bg-black p-4 rounded-xl overflow-auto border border-gray-800">
                      {JSON.stringify(response?.full_state || {
                        thoughts: streamThoughts,
                        actions: streamActions,
                        observations: streamObservations
                      }, null, 2)}
                    </pre>
                  )}
                </>
              ) : (
                <div className="text-center py-16">
                  <div className="w-20 h-20 mx-auto mb-4 bg-zinc-800 rounded-2xl flex items-center justify-center border border-gray-700">
                    <svg className="w-10 h-10 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-gray-500 mb-2">
                    等待查询...
                  </h3>
                  <p className="text-sm text-gray-600">
                    输入问题后，这里将展示 ReAct 推理过程
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-900 bg-black/80 backdrop-blur-sm mt-12">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between text-sm">
            <p className="text-gray-600">
              Powered by <span className="text-gray-400 font-semibold">LangGraph</span> + 
              <span className="text-gray-400 font-semibold"> FastAPI</span> + 
              <span className="text-gray-400 font-semibold"> Neo4j</span>
            </p>
            <div className="flex items-center space-x-4 text-gray-600">
              <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="hover:text-gray-400 transition-colors">
                API Docs
              </a>
              <span>·</span>
              <a href="http://localhost:7474" target="_blank" rel="noopener noreferrer" className="hover:text-gray-400 transition-colors">
                Neo4j Browser
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
