// ============================================================
//  AgentPanel.jsx —— 显示助手做了什么，以及它想做什么
//
//  ⭐ 这个组件有个硬规矩：**它自己不发请求**。
//
//     它只负责显示，所有动作都通过 props 回调出去
//     （onConfirmDelete / onDismiss）。
//     这样它才能被单独测、被复用，也才不会偷偷改数据。
//
//  ⭐ 版块的顺序是有讲究的，从上到下：
//       ① 它说的话       —— 人先读句子
//       ② 它做的事       —— 回执，灰的，只读
//       ③ 它想做的事     —— 带按钮的询问，红色边框，专门抢注意力
//
//     如果 ② 和 ③ 长得一样，用户就会把"想删"当成"删了"。
// ============================================================

export default function AgentPanel({ result, onConfirmDelete, onDismiss }) {
    if (!result) return null;

    const { reply, actions, turns, truncated, proposals } = result;

    return (
        <div className="agent-panel">
            {/* ① 它说的话 */}
            <p className="agent-reply">{reply}</p>

            {/* ② 它做的事：只读回执 */}
            {actions.length > 0 && (
                <ul className="agent-actions">
                    {actions.map((a, i) => (
                        <li key={`${a.tool}-${i}`} className={a.ok ? "ok" : "fail"}>
                            <span className="mark">{a.ok ? "✓" : "✗"}</span>
                            {a.detail}
                        </li>
                    ))}
                </ul>
            )}

            {/* ③ 它想做的事：等你点头 */}
            {proposals.map(p => (
                <div key={p.id} className="agent-proposal">
                    <p>
                        要删除 <strong>#{p.id}《{p.title}》</strong> 吗？
                        <span className="agent-proposal-hint">
                            点"删除"才会真的删，现在还在。
                        </span>
                    </p>
                    {/* ⚠️ 这里【不能】复用 .ai-preview-actions：
                        那个容器的样式是"第一个按钮绿色 = 确认创建"，
                        照搬过来会让"删除"变成绿色主按钮 —— 一个颜色就把语义反了。
                        长得像什么，用户就会以为是什么。 */}
                    <div className="agent-proposal-actions">
                        {/* ⭐ 这个按钮是整条链路上【唯一】能触发 DELETE 的地方。
                            模型的工具表里没有删除，后端 /ai/agent 里也没有 DELETE。 */}
                        <button className="danger" onClick={() => onConfirmDelete(p)}>
                            删除
                        </button>
                        <button onClick={() => onDismiss(p.id)}>保留</button>
                    </div>
                </div>
            ))}

            {/* 轮次用完 = 说完了但可能没做完，要明说 */}
            {truncated && (
                <p className="ai-note">
                    它做了一部分就停了（最多 {turns} 轮）。可以再发一次让它接着做。
                </p>
            )}

            <p className="agent-meta">
                用了 {turns} 轮 · {actions.length} 次工具调用
            </p>
        </div>
    );
}
