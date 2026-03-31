interface Props {
  text: string;
}

export function ThinkingIndicator({ text }: Props) {
  if (!text) return null;

  return (
    <div className="thinking-block">
      <div className="thinking-header">
        <span className="thinking-icon">✦</span>
        <span className="thinking-label">thinking</span>
        <span className="thinking-dots"><span /><span /><span /></span>
      </div>
      <div className="thinking-body">{text}</div>
    </div>
  );
}
