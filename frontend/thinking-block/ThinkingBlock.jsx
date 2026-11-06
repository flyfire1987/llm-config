import React, { useState, useEffect, useRef } from 'react';
import './ThinkingBlock.css';

/**
 * ThinkingBlock - 大模型思考过程折叠组件
 * 默认折叠,点击展开,带平滑过渡动画
 *
 * Props:
 *   - thinking: string      思考过程文本
 *   - duration: number     思考用时(秒),可选
 *   - model: string        模型名称,可选
 *   - isStreaming: boolean 是否正在生成思考过程
 *   - defaultOpen: boolean 是否默认展开,默认 false
 */
function ThinkingBlock({
  thinking = '',
  duration,
  model,
  isStreaming = false,
  defaultOpen = false,
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [displayedText, setDisplayedText] = useState(thinking);
  const contentRef = useRef(null);

  // 流式打字效果:isStreaming 时逐字显示
  useEffect(() => {
    if (!isStreaming) {
      setDisplayedText(thinking);
      return;
    }
    let i = 0;
    setDisplayedText('');
    const timer = setInterval(() => {
      i++;
      setDisplayedText(thinking.slice(0, i));
      if (i >= thinking.length) clearInterval(timer);
    }, 15);
    return () => clearInterval(timer);
  }, [thinking, isStreaming]);

  // 内容变化时滚动到底
  useEffect(() => {
    if (isOpen && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [displayedText, isOpen]);

  if (!thinking && !isStreaming) return null;

  return (
    <div className={`thinking-block ${isOpen ? 'open' : ''} ${isStreaming ? 'streaming' : ''}`}>
      <button
        className="thinking-header"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span className="thinking-icon">
          {isStreaming ? <span className="thinking-spinner" /> : '🤔'}
        </span>
        <span className="thinking-title">
          {isStreaming ? '正在思考...' : '思考过程'}
          {duration != null && !isStreaming && (
            <span className="thinking-duration">({duration}s)</span>
          )}
          {model && <span className="thinking-model">{model}</span>}
        </span>
        <span className={`thinking-arrow ${isOpen ? 'rotated' : ''}`}>▾</span>
      </button>

      <div
        className="thinking-content-wrapper"
        style={{ maxHeight: isOpen ? '400px' : '0' }}
      >
        <div className="thinking-content" ref={contentRef}>
          {displayedText}
          {isStreaming && <span className="thinking-cursor">▍</span>}
        </div>
      </div>
    </div>
  );
}

export default ThinkingBlock;