// ============================================================
//  AiPreview.jsx —— AI 解析结果的"预览卡片"
//
//  ⭐ 它的职责只有一个：把草稿显示出来，让用户决定"哪些真的要创建"。
//
//  它【不负责】：
//    · 调接口（那是 useAiParse 和 useTodos 的事）
//    · 决定创建哪些（那是用户点按钮决定的）
//  它只负责"把数据画出来 + 把用户的意图转成回调"。
// ============================================================

// ⚠️ 为什么要 _id，而不是直接用 map 的下标当 key？
//
//   错误写法：{tasks.map((t, i) => <li key={i}>…)}
//
//   假设有三条 [A, B, C]，用户删掉 A。
//   重新渲染后数组是 [B, C]：
//        下标 0 原来是 A，现在是 B   → React 认为"0 号元素只是文字变了"
//        下标 1 原来是 B，现在是 C   → 同上
//   于是 React 会【复用】原来 A 的那个 DOM 节点来显示 B。
//   现在内容都是纯文字，看不出问题；
//   可一旦这一行里有 <input>（用户能编辑草稿）、有动画、或者有焦点状态，
//   就会出现"我删了 A，光标却跳到了 B 的输入框里"这种怪事。
//
//   用稳定的 _id，React 才能正确地知道"是哪一个被删了"。
function AiPreview({ tasks, note, busy, onRemove, onConfirm, onCancel }) {
    // ---------- 空结果：解析成功，但这句里没有任务 ----------
    if (tasks.length === 0) {
        return (
            <div className="ai-preview">
                <p>没有从这句话里找到任何任务。</p>
                {note && <p className="ai-note">{note}</p>}
                <button onClick={onCancel}>知道了</button>
            </div>
        );
    }

    // ---------- 正常情况：列出草稿，等用户确认 ----------
    return (
        <div className="ai-preview">
            <p className="ai-preview-hint">
                解析出 {tasks.length} 条，<strong>确认后才会写入</strong>：
            </p>
            {note && <p className="ai-note">{note}</p>}

            <ul>
                {tasks.map(t => (
                    // key 用稳定的 _id，不用下标 —— 理由见文件开头
                    <li key={t._id}>
                        <span className={`pri pri-${t.priority}`}>
                            {t.priority}
                        </span>
                        <span className="title">{t.title}</span>
                        {t.due && <span className="due">截止 {t.due}</span>}
                        <button onClick={() => onRemove(t._id)}>不要</button>
                    </li>
                ))}
            </ul>

            <div className="ai-preview-actions">
                <button onClick={onConfirm} disabled={busy}>
                    确认创建这 {tasks.length} 条
                </button>
                <button onClick={onCancel} disabled={busy}>
                    取消
                </button>
            </div>
        </div>
    );
}

export default AiPreview;
