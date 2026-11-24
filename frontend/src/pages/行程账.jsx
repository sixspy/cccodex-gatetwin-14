import React, { useEffect, useState } from "react";
import { 取 } from "../api.js";

export default function 行程账() {
  const [行, 设] = useState([]);
  const 刷 = () => 取("/行程账").then(设);
  useEffect(() => { 刷(); }, []);
  return (
    <div>
      <h1 className="题">行程账</h1>
      <p className="述">
        进站+出站成对后的正式行程。主读按<strong>当前版本</strong>解析：成对后若经封印写闸修正出站，
        基行保留、新版本行标当前，此处显示主读值。贯验与封印链同票。
      </p>
      <div className="行"><button className="次" onClick={刷}>刷新</button></div>
      {!行.length ? <div className="空态">暂无行程。先灌成对样例。</div> : (
        <table>
          <thead>
            <tr>
              <th>行程键</th><th>卡号</th><th>进→出(主读)</th><th>进站时</th><th>出站时(主读)</th>
              <th>历时秒</th><th>主读版本</th><th>基行出站</th><th>封印态</th>
            </tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.行程键}>
                <td>{r.行程键}</td><td>{r.卡号}</td>
                <td>{r.进站站点键}→{r.出站站点键}</td>
                <td>{r.进站事件时}</td><td>{r.出站事件时}</td>
                <td>{r.历时秒}</td>
                <td>
                  {r.版本}
                  {!r.是否基行 && <span className="徽章 通" style={{ marginLeft: 4 }}>追加</span>}
                </td>
                <td style={{ color: r.是否基行 ? undefined : "var(--淡)" }}>
                  {r.基行出站站点键}{!r.是否基行 && "（保留）"}
                </td>
                <td>{r.封印态}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
