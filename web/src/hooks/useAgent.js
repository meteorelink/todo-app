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
//
//  ============================================================
//  ⑨ 多轮记忆：这个 hook 现在还得记住 conversation_id
//  ============================================================
//
//  ⭐ 记忆的真相：**模型什么都没记住，是我们的代码把它上次说过的话又发了一遍。**
//
//     所以前端必须做一件很小但决定性的事：把后端给的 id 留着，
//     下一次请求原样带回去。不带，后端就只能当成一个全新的对话 ——
//     你上一句说"把买牛奶删掉"、这一句说"那另一条呢"，
//     没有 id 的时候模型完全不知道"另一条"是哪一条。
//
//  ⚠️ 这个 id 存在【浏览器内存】里，所以：
//       按 F5 刷新  → id 没了 → 下一句就是个新对话（模型失忆，但不报错）
//       后端重启/超时 24h → 后端读不到历史了，但 id 还能用，
//                          它只是从"空历史"开始，同样不报错
//
//     两处"静默失忆"都是【优雅降级】而不是崩溃 —— 这是有意的：
//     记忆是增强，不是前提。宁可它忘，也不能因为它忘了就整个用不了。
//
//     想让它跨刷新也活着？把 setConversationId 改成同时写 localStorage，
//     初始化时从 localStorage 读回来 —— 三行代码。我们故意没做，
//     因为"刷新一下开始新对话"对调试来说更好用。
// ============================================================

import { useState } from "react";
import { STATUS_MESSAGE, friendlyError } from "./aiMessages";

const API = "http://127.0.0.1:8000";

export function useAgent() {
    const [running, setRunning] = useState(false);   // 助手正在干活（可能几十秒）
    const [result, setResult] = useState(null);     // 后端的 AgentResult
    const [error, setError] = useState(null);

    // 当前这次对话的编号。null = 还没有对话（下一句话会开一个新的）
    const [conversationId, setConversationId] = useState(null);

    // 这一次请求有没有接上之前的话 —— 只用来在界面上告诉用户"它记得"
    const [continued, setContinued] = useState(false);

    async function run(text) {
        setRunning(true);
        setError(null);
        setResult(null);   // ⚠️ 先清空上一次的结果，否则新旧回执会叠在一起

        // 记下来这次是不是接着说的：null 说明这是新对话的第一句
        const previousId = conversationId;
        setContinued(previousId !== null);

        try {
            const res = await fetch(`${API}/ai/agent`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text,
                    // ⭐ 就是这一行让它"记得"。
                    //    第一次是 null（省略掉），之后每次都带上同一个 id。
                    conversation_id: previousId,
                }),
            });

            if (!res.ok) {
                throw new Error(
                    STATUS_MESSAGE[res.status] ?? `服务器返回 ${res.status}`
                );
            }

            const data = await res.json();
            setResult(data);

            // ⭐ 后端说"这次对话叫这个名字"，记下来给下一句用。
            //    只有在成功时才更新：失败了就保持原来的 id，
            //    用户重试时还是接着同一段对话，而不是莫名其妙开一个新的。
            if (data.conversation_id) {
                setConversationId(data.conversation_id);
            }

            // ⭐ 把结果【返回】给调用方，而不是在这里顺手把任务列表刷新一遍。
            //
            //    因为"要不要刷新列表"这个决定，这个 Hook 做不了：
            //    它根本不知道 useTodos 的存在（两个 Hook 互不相识，这是故意的）。
            //    知道"任务列表在哪"的是 App —— 它才是把两者放在一起的地方。
            //
            //    所以这里只交付事实，不负责善后。
            return data;
        } catch (err) {
            setError(friendlyError(err));
            return null;       // 失败 = 什么都没拿到，调用方据此跳过刷新
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

    // ---------- 清场：只清界面上的结果，对话还在 ----------
    function reset() {
        setResult(null);
        setError(null);
    }

    // ---------- 换个话题：对话也丢掉 ----------
    //
    // ⚠️ 这里【不发 DELETE 请求】。旧对话会在 24 小时后被后端自动清掉，
    //    现在就删只是徒增一次网络请求 —— 用户看不见的区别，不值得做。
    //    "前端忘了 id"和"后端删了记录"，效果是一样的：下一句话是新对话。
    function newConversation() {
        setConversationId(null);
        setContinued(false);
        setResult(null);
        setError(null);
    }

    return {
        running,
        result,
        error,
        continued,
        conversationId,
        run,
        dismissProposal,
        reset,
        newConversation,
    };
}
