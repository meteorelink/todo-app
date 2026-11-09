// ============================================================
//  hooks/useAiParse.js —— 自定义 Hook：把一句话变成"待确认的草稿"
//
//  ⭐ 它和 useTodos 最大的区别：它【不写数据库】。
//
//     useTodos    → 和数据库打交道（增删改查，全都会真的改数据）
//     useAiParse  → 只问模型"这句话里有哪些任务"，一个字节都不写
//
//  这就是 8.3 里特意把 /ai/parse 和 /todos/batch 拆成两个接口的原因：
//  解析的结果是【草稿】，草稿不是数据。
//
//  ⭐ 由此推出一个反直觉的结论：
//     用户在预览里"删掉"一条，我们【什么都记】。
//     因为那条任务从来没存在过，谈不上"删除"——
//     他只是"不创建它"。不创建这件事，不需要记录，
//     做法就是"不把它放进要发送的数组里"。
// ============================================================

import { useState } from "react";
import { STATUS_MESSAGE, friendlyError } from "./aiMessages";

const API = "http://127.0.0.1:8000";

export function useAiParse() {
    // ---------- 状态 ----------
    const [parsing, setParsing] = useState(false);  // 正在等模型
    const [draft, setDraft] = useState(null);       // null = 没有预览；[] = 解析了但没任务
    const [note, setNote] = useState(null);         // 模型附带的说明（比如"只是闲聊"）
    const [error, setError] = useState(null);       // 错误信息

    // ---------- 请求解析（不写库！） ----------
    async function parse(text) {
        setParsing(true);
        setError(null);
        setNote(null);
        setDraft(null);

        try {
            const res = await fetch(`${API}/ai/parse`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });

            // ⚠️ fetch 不会因为 4xx/5xx 抛异常，必须自己判断
            if (!res.ok) {
                throw new Error(
                    STATUS_MESSAGE[res.status] ?? `服务器返回 ${res.status}`
                );
            }

            const data = await res.json();

            setNote(data.note ?? null);

            // ⭐ 给每条草稿加一个 _id。
            //    为什么不直接用数组下标当 key？见 AiPreview.jsx 里的说明。
            setDraft(
                data.tasks.map((t, i) => ({
                    ...t,
                    _id: `draft-${Date.now()}-${i}`,
                }))
            );
        } catch (err) {
            setError(friendlyError(err));
        } finally {
            setParsing(false);
        }
    }

    // ---------- 从草稿里划掉一条（纯前端，不发请求） ----------
    //
    // ⭐ 这一行就是"用户删掉买牛奶"的全部实现。
    //    没有 DELETE 请求，没有数据库操作，什么都没有。
    //    因为那条任务还没被创建过。
    function removeDraftTask(id) {
        setDraft(prev => prev.filter(t => t._id !== id));
    }

    // ---------- 放弃草稿 ----------
    function discardDraft() {
        setDraft(null);
        setNote(null);
        setError(null);
    }

    return {
        parsing,
        draft,
        note,
        error,
        parse,
        removeDraftTask,
        discardDraft,
    };
}
