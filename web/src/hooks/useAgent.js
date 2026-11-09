// ============================================================
//  hooks/useAgent.js —— 自定义 Hook：把一句话交给【会动手】的助手
//
//  ⭐ 它和 useAiParse 的根本区别：**它会产生副作用**。
//
//     useAiParse  → 只问"这句话里有哪些任务"，一个字节都不写
//     useAgent    → 后端会真的建任务、真的改状态
//
//     所以这个 hook 返回的东西，不是"草稿"，而是"已经发生的事"：
//       actions  —— 它做了什么（回执，只读，不能撤销也不能编辑）
//       proposals —— 它想删什么（还没发生，等你点头）
//
//  ⭐ 为什么 proposals 要和 actions 分开？
//
//     actions 里的每一条都已经发生了，前端唯一能做的是【显示】。
//     proposals 里的每一条都还没发生，前端要做的是【问】。
//
//     如果把两者塞进同一个数组，界面就会长成
//       ✓ 请求删除 #30《买牛奶》
//     用户扫一眼“✓”，以为删完了，然后刷新发现还在 —— 这比不显示更糟。
//
//  ⚠️ 还有一点和 useTodos 不同：这个请求可能要跑很久。
//     后端最多 5 轮 × 60 秒，用户在界面上会真的干等。
//     所以 running 这个状态必须被用起来（禁用按钮 + 显示"处理中"），
//     否则用户会以为没反应，连续点三次 —— 三次都真的执行，三次都收费。
// ============================================================

import { useState } from "react";
import { STATUS_MESSAGE, friendlyError } from "./aiMessages";

const API = "http://127.0.0.1:8000";

export function useAgent() {
    const [running, setRunning] = useState(false);   // 助手正在干活（可能几十秒）
    const [result, setResult] = useState(null);     // 后端的 AgentResult
    const [error, setError] = useState(null);

    async function run(text) {
        setRunning(true);
        setError(null);
        setResult(null);   // ⚠️ 先清空上一次的结果，否则新旧回执会叠在一起

        try {
            const res = await fetch(`${API}/ai/agent`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });

            if (!res.ok) {
                throw new Error(
                    STATUS_MESSAGE[res.status] ?? `服务器返回 ${res.status}`
                );
            }

            setResult(await res.json());
        } catch (err) {
            setError(friendlyError(err));
        } finally {
            setRunning(false);
        }
    }

    // ---------- 用户说"这条不要删" ----------
    //
    // ⭐ 纯前端：从 proposals 里去掉一条，不发任何请求。
    //    和 useAiParse.removeDraftTask 是同一个道理 ——
    //    "不做这件事"不需要通知任何人，因为这件事本来就没发生。
    function dismissProposal(id) {
        setResult(prev =>
            prev
                ? { ...prev, proposals: prev.proposals.filter(p => p.id !== id) }
                : prev
        );
    }

    // ---------- 清场 ----------
    function reset() {
        setResult(null);
        setError(null);
    }

    return { running, result, error, run, dismissProposal, reset };
}
