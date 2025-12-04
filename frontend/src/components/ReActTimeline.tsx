import React from 'react';
import { Thought, Action, Observation } from '../api';

interface ReActTimelineProps {
  thoughts: Thought[];
  actions: Action[];
  observations: Observation[];
}

export const ReActTimeline: React.FC<ReActTimelineProps> = ({
  thoughts,
  actions,
  observations,
}) => {
  const [expandedStep, setExpandedStep] = React.useState<number | null>(null);

  // 合并 Thought、Action、Observation 按迭代组织
  const steps = React.useMemo(() => {
    const maxIteration = Math.max(
      thoughts.length,
      actions.length,
      observations.length
    );

    return Array.from({ length: maxIteration }, (_, i) => ({
      iteration: i,
      thought: thoughts.find((t) => t.iteration === i),
      action: actions.find((a) => a.iteration === i),
      observation: observations.find((o) => o.iteration === i),
    }));
  }, [thoughts, actions, observations]);

  const toggleStep = (iteration: number) => {
    setExpandedStep(expandedStep === iteration ? null : iteration);
  };

  return (
    <div className="space-y-3">
      {/* 时间线 */}
      <div className="relative">
        {/* 垂直线 */}
        <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gradient-to-b from-gray-700 via-gray-600 to-gray-700"></div>

        {steps.map((step, index) => (
          <div key={index} className="relative pb-6 last:pb-0">
            {/* 步骤节点 */}
            <div className="flex items-start">
              {/* 圆点 */}
              <div className="relative z-10">
                <div className="flex items-center justify-center w-12 h-12 bg-gradient-to-br from-gray-700 to-gray-900 rounded-xl text-white font-bold shadow-lg border border-gray-600">
                  {index + 1}
                </div>
              </div>

              {/* 内容 */}
              <div className="ml-4 flex-1">
                <button
                  onClick={() => toggleStep(step.iteration)}
                  className="w-full text-left bg-zinc-800 border border-gray-700 rounded-xl p-4 hover:border-gray-600 transition-all group"
                >
                  <div className="flex items-center justify-between">
                    <h4 className="text-base font-semibold text-white group-hover:text-gray-300 transition-colors">
                      步骤 {index + 1}
                    </h4>
                    <svg
                      className={`w-5 h-5 text-gray-400 transition-transform ${
                        expandedStep === step.iteration ? 'rotate-180' : ''
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </div>

                  {/* 摘要 */}
                  <div className="mt-2 flex items-center space-x-2">
                    {step.action && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-lg bg-zinc-700 text-gray-300 text-xs font-medium border border-gray-600">
                        {step.action.action.function_name}
                      </span>
                    )}
                    {step.observation && (
                      <span className="text-sm text-gray-400">
                        {step.observation.result_summary}
                      </span>
                    )}
                  </div>
                </button>

                {/* 展开详情 */}
                {expandedStep === step.iteration && (
                  <div className="mt-3 bg-black border border-gray-800 rounded-xl p-4 space-y-3">
                    {/* Thought */}
                    {step.thought && (
                      <div className="border-l-2 border-yellow-600/50 pl-3">
                        <div className="flex items-center space-x-2 mb-2">
                          <div className="w-2 h-2 bg-yellow-600 rounded-full"></div>
                          <h5 className="font-semibold text-yellow-600 text-sm">
                            💭 Thought（思考）
                          </h5>
                        </div>
                        <p className="text-sm text-gray-300 leading-relaxed">
                          {step.thought.content.thought}
                        </p>
                        {step.thought.content.reasoning && (
                          <p className="text-xs text-gray-400 mt-2">
                            <strong>推理:</strong> {step.thought.content.reasoning}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Action */}
                    {step.action && (
                      <div className="border-l-2 border-gray-600/50 pl-3">
                        <div className="flex items-center space-x-2 mb-2">
                          <div className="w-2 h-2 bg-gray-500 rounded-full"></div>
                          <h5 className="font-semibold text-gray-400 text-sm">
                            ⚡ Action（行动）
                          </h5>
                        </div>
                        <p className="text-sm text-gray-300">
                          <strong className="text-gray-400">函数:</strong> {step.action.action.function_name}
                        </p>
                        <div className="text-xs text-gray-400 mt-1 bg-zinc-900 border border-gray-800 rounded p-2 font-mono">
                          <strong>参数:</strong> {JSON.stringify(step.action.action.parameters, null, 2)}
                        </div>
                        <p className="text-xs text-gray-400 mt-1">
                          <strong>原因:</strong> {step.action.action.reason}
                        </p>
                      </div>
                    )}

                    {/* Observation */}
                    {step.observation && (
                      <div className="border-l-2 border-green-700/50 pl-3">
                        <div className="flex items-center space-x-2 mb-2">
                          <div className="w-2 h-2 bg-green-700 rounded-full"></div>
                          <h5 className="font-semibold text-green-700 text-sm">
                            👁️ Observation（观察）
                          </h5>
                        </div>
                        <p className="text-sm text-gray-300">
                          {step.observation.result_summary}
                        </p>
                        <details className="mt-2">
                          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300 transition-colors">
                            查看详细结果 ▼
                          </summary>
                          <pre className="mt-2 p-3 bg-zinc-900 border border-gray-800 rounded-lg text-xs overflow-auto max-h-48 custom-scrollbar text-gray-400">
                            {JSON.stringify(step.observation.result, null, 2)}
                          </pre>
                        </details>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {steps.length === 0 && (
        <div className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 bg-zinc-800 rounded-2xl flex items-center justify-center border border-gray-700">
            <svg className="w-8 h-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-gray-500 text-sm">暂无执行流程数据</p>
        </div>
      )}
    </div>
  );
};
