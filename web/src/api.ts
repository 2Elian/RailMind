import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface QueryRequest {
  query: string;
  user_id: string;
  session_id?: string;
}

export interface Thought {
  iteration: number;
  timestamp: string;
  content: {
    thought: string;
    reasoning: string;
    next_action: any;
    expected_outcome: string;
  };
}

export interface Action {
  iteration: number;
  timestamp: string;
  action: {
    function_name: string;
    parameters: any;
    reason: string;
  };
}

export interface Observation {
  iteration: number;
  timestamp: string;
  function: string;
  parameters: any;
  result: any;
  result_summary: string;
}

export interface QueryResponse {
  success: boolean;
  answer: string;
  metadata: {
    session_id: string;
    user_id: string;
    iterations: number;
    functions_used: number;
    timestamp: string;
    error?: string;
  };
  thoughts: Thought[];
  actions: Action[];
  observations: Observation[];
  full_state?: any;
}

export const api = {
  async createSession(userId: string) {
    const response = await axios.post(`${API_BASE_URL}/api/session`, {
      user_id: userId,
    });
    return response.data;
  },

  async query(request: QueryRequest): Promise<QueryResponse> {
    const response = await axios.post(`${API_BASE_URL}/api/query`, request);
    return response.data;
  },

  // 流式查询，实时返回 ReAct 流程
  queryStream(
    request: QueryRequest,
    onThought: (thought: Thought) => void,
    onAction: (action: Action) => void,
    onObservation: (observation: Observation) => void,
    onComplete: (response: QueryResponse) => void,
    onError: (error: Error) => void
  ) {
    const eventSource = new EventSource(
      `${API_BASE_URL}/api/query_stream?` + new URLSearchParams({
        query: request.query,
        user_id: request.user_id,
        session_id: request.session_id || '',
      })
    );

    eventSource.addEventListener('thought', (event) => {
      try {
        const thought = JSON.parse(event.data);
        onThought(thought);
      } catch (e) {
        console.error('解析 thought 失败:', e);
      }
    });

    eventSource.addEventListener('action', (event) => {
      try {
        const action = JSON.parse(event.data);
        onAction(action);
      } catch (e) {
        console.error('解析 action 失败:', e);
      }
    });

    eventSource.addEventListener('observation', (event) => {
      try {
        const observation = JSON.parse(event.data);
        onObservation(observation);
      } catch (e) {
        console.error('解析 observation 失败:', e);
      }
    });

    eventSource.addEventListener('complete', (event) => {
      try {
        const response = JSON.parse(event.data);
        onComplete(response);
        eventSource.close();
      } catch (e) {
        console.error('解析 complete 失败:', e);
      }
    });

    eventSource.addEventListener('error', (event) => {
      onError(new Error('流式查询失败'));
      eventSource.close();
    });

    return eventSource;
  },

  async getSessionHistory(sessionId: string) {
    const response = await axios.get(`${API_BASE_URL}/api/session/${sessionId}/history`);
    return response.data;
  },

  async deleteSession(sessionId: string) {
    const response = await axios.delete(`${API_BASE_URL}/api/session/${sessionId}`);
    return response.data;
  },

  async getFunctions() {
    const response = await axios.get(`${API_BASE_URL}/api/functions`);
    return response.data;
  },
};
