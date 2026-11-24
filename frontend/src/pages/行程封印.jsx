import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 行程封印() {
  const [账, 设账] = useState([]);
  const [键, 设键] = useState("");
  const [状, 设状] = useState(null);
  const [版, 设版] = useState([]);
  const [审, 设审] = useState([]);
  const [讯, 设讯] = useState("");
  const [改站, 设改站] = useState("站A");
  const [改时, 设改时] = useState("2026-11-22T08:42:00Z");

  const 刷账 = () => 取("/行程账").then((r) => {
    设账(r);
    if (!键 && r.length) 设键(r[0].行程键);
  });
  useEffect(() => { 刷账(); }, []);

  const 刷详情 = async (k = 键) => {
    if (!k) return;
    设讯("");
    try {
      const [s, v, a] = await Promise.all([
        取(`/行程封印?行程键=${encodeURIComponent(k)}`),
        取(`/行程封印/版本?行程键=${encodeURIComponent(k)}`),
        取(`/行程封印/审计?行程键=${encodeURIComponent(k)}`),
      ]);
      设状(s); 设版(v); 设审(a);
    } catch (e) { 设讯(String(e.message || e)); }
  };
  useEffect(() => { if (键) 刷详情(键); }, [键]);

  const 做封印 = async () => {
    const r = await 递("/行程封印", { 行程键: 键, 备注: "页面手封" });
    设讯(r.ok ? `已封印，封印版本 ${r.封印版本}` : `封印失败：${r.原因}`);
    await 刷账(); await 刷详情();
  };
  const 做改 = async () => {
    const r = await 递("/行程封印/改出站", { 行程键: 键, 出站站点键: 改站, 出站事件时: 改时, 依据: "页面修正" });
    设讯(r.ok ? (r.命中 ? "与当前版本一致，未追加" : `已追加版本 ${r.当前版本}，主读出站=${r.主读出站站}`) : `失败：${r.原因}`);
    await 刷账(); await 刷详情();
  };
  const 做重放 = async () => {
    const r = await 递("/行程封印/重放", { 行程键: 键, 出站站点键: 改站, 出站事件时: 改时, 依据: "页面重放" });
    设讯(r.接受 ? "重放命中（封印只读，未改动）" : `重放拒绝：${r.拒绝}（已落旁路）`);
    await 刷账(); await 刷详情();
  };

  return (
    <div>
      <h1 className="题">行程封印</h1>
      <p className="述">
        口径：<strong>版本追加</strong>。已成对行程基行不可原地改；出站/历时修正追加版本行并标当前，
        主读取当前版本，贯验同票。装载重放对封印行程只读，冲突拒绝入旁路匣。
      </p>

      <div className="行">
        <select value={键} onChange={(e) => 设键(e.target.value)}>
          {!账.length && <option value="">（无行程）</option>}
          {账.map((r) => (
            <option key={r.行程键} value={r.行程键}>
              {r.行程键} · {r.卡号} · {r.进站站点键}→{r.出站站点键} · v{r.版本}
            </option>
          ))}
        </select>
        <button className="次" onClick={刷账}>刷新行程</button>
        <button className="次" onClick={() => 刷详情()}>刷新详情</button>
      </div>

      {讯 && <p className="讯">{讯}</p>}

      {状 && (
        <div className="阶条" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          <div className="阶"><div className="序">封印态</div><b style={{ fontSize: "1rem" }}>{状.封印态}</b><span>valid: {String(状.valid)}</span></div>
          <div className="阶"><div className="序">主读出站站</div><b style={{ fontSize: "1rem" }}>{状.主读出站站}</b><span>版本 {状.主读版本}</span></div>
          <div className="阶"><div className="序">当前版本</div><b>{状.当前版本 ?? "—"}</b><span>{状.口径}</span></div>
          <div className="阶"><div className="序">拒绝</div><b style={{ fontSize: "0.9rem" }}>{状.拒绝 ? 状.拒绝.动作 : "无"}</b><span>{状.问题?.length ? 状.问题.join("；") : "链一致"}</span></div>
        </div>
      )}

      <div className="行">
        <button onClick={做封印}>封印</button>
        <label>改出站
          <select value={改站} onChange={(e) => 设改站(e.target.value)} style={{ marginLeft: 6 }}>
            <option>站A</option><option>站B</option><option>站C</option>
          </select>
        </label>
        <input value={改时} onChange={(e) => 设改时(e.target.value)} style={{ width: 210 }} />
        <button className="水" onClick={做改}>提交修正（追加版本）</button>
        <button className="次" onClick={做重放}>模拟装载重放</button>
      </div>

      <h2 className="段题">版本链</h2>
      {!版.length ? <div className="空态">选一行程查看版本链。</div> : (
        <table>
          <thead><tr><th>版本</th><th>出站站</th><th>出站时</th><th>历时秒</th><th>依据</th><th>当前</th><th>处理时</th></tr></thead>
          <tbody>
            {版.map((v) => (
              <tr key={v.版本}>
                <td>{v.版本}{v.基行 && "（基行）"}</td>
                <td>{v.出站站点键}</td><td>{v.出站事件时}</td><td>{v.历时秒}</td><td>{v.依据}</td>
                <td>{v.是否当前 ? <span className="徽章 通">当前</span> : "—"}</td>
                <td>{v.处理时}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 className="段题">封印审计</h2>
      {!审.length ? <div className="空态">无审计记录。</div> : (
        <table>
          <thead><tr><th>#</th><th>动作</th><th>版本</th><th>载荷</th><th>时刻</th></tr></thead>
          <tbody>
            {审.map((a) => (
              <tr key={a.编号}>
                <td>{a.编号}</td><td>{a.动作}</td><td>{a.版本}</td>
                <td style={{ maxWidth: 460, wordBreak: "break-all" }}>{a.载荷}</td><td>{a.时刻}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
