import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 卡号换绑() {
  const [行, 设行] = useState([]);
  const [讯, 设讯] = useState("");
  const [旧卡, 设旧] = useState("");
  const [新卡, 设新] = useState("");
  const [事件时, 设时] = useState("");
  const 刷 = () => 取("/换绑").then(设行);
  useEffect(() => { 刷(); }, []);

  const 提交 = async () => {
    设讯("换绑写闸中…");
    try {
      const r = await 递("/换绑", { 旧卡: 旧卡.trim(), 新卡: 新卡.trim(), 事件时: 事件时.trim() });
      设讯(
        `换绑 ${r.换绑键} 生效：旧卡 ${r.旧卡}→新卡 ${r.新卡}，切断开腿 ${r.处置列表.length} 条`
      );
      设旧(""); 设新(""); 设时("");
      await 刷();
    } catch (e) {
      设讯(`换绑被闸门拒收：${e.message || e}`);
      await 刷();
    }
  };

  return (
    <div>
      <h1 className="题">卡号换绑隔离</h1>
      <p className="述">
        全局唯一口径：<strong>切断旧开腿旁路</strong>。换绑事务内旧卡全部在途开腿旁路（换绑切断），
        新卡从空开腿开始；<strong>开腿行卡号不改写</strong>，行程卡号与开腿卡号恒等。
        旧卡再出站按孤儿，新卡出站只配换绑后的新腿。
      </p>
      <div className="行">
        <input placeholder="旧卡" value={旧卡} onChange={(e) => 设旧(e.target.value)} />
        <input placeholder="新卡" value={新卡} onChange={(e) => 设新(e.target.value)} />
        <input placeholder="事件时(可空=此刻)" value={事件时} onChange={(e) => 设时(e.target.value)} />
        <button onClick={提交}>换绑写闸</button>
        <button className="次" onClick={刷}>刷新审计</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!行.length ? <div className="空态">尚无换绑记录。</div> : (
        <table>
          <thead>
            <tr><th>换绑键</th><th>旧卡</th><th>新卡</th><th>事件时</th><th>valid</th><th>开腿处置</th><th>审计</th></tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.换绑键}>
                <td>{r.换绑键}</td>
                <td>{r.旧卡}</td>
                <td>{r.新卡}</td>
                <td>{r.事件时}</td>
                <td>
                  <span className={`徽章 ${r.valid ? "通" : "败"}`}>{r.valid ? "生效" : "拒收"}</span>
                </td>
                <td style={{ maxWidth: 260, wordBreak: "break-all" }}>
                  {r.处置列表.length
                    ? r.处置列表.map((d) => `${d.开腿键}:${d.旁路原因}`).join("；")
                    : "—"}
                </td>
                <td style={{ maxWidth: 360, wordBreak: "break-all" }}>{JSON.stringify(r.审计)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
