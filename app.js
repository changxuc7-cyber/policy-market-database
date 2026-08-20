const D=window.APP_DATA;
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];

function setView(id){
  $$(".view").forEach(v=>v.classList.toggle("active",v.id===id));
  $$(".tab").forEach(t=>t.classList.toggle("active",t.dataset.view===id));
  window.scrollTo({top:0,behavior:"smooth"});
}
$$(".tab").forEach(t=>t.addEventListener("click",()=>setView(t.dataset.view)));
$$("[data-jump]").forEach(b=>b.addEventListener("click",()=>setView(b.dataset.jump)));

const badgeClass = cat => ({
  "全国碳市场":"blue",
  "CCER政策":"cyan",
  "地方碳市场":"purple",
  "绿电绿证":"gold",
  "生态环境综合政策":"indigo"
}[cat]||"indigo");

function renderLatest(){
  $("#latestPolicies").innerHTML=D.policies.slice(0,5).map(p=>`
    <tr><td>${p.date.slice(5)}</td><td class="title-cell">${p.title}</td><td>${p.publisher}</td>
    <td><span class="badge ${badgeClass(p.category)}">${p.category}</span></td></tr>`).join("");
}
function renderDeadlines(){
  $("#deadlineList").innerHTML=D.deadlines.map(x=>`
    <div class="deadline-item">
      <div><div class="deadline-name">${x.name}</div><div class="deadline-meta">${x.market} · 截止 ${x.date}</div></div>
      <div class="days ${x.risk}">${x.days}天</div>
    </div>`).join("");
}
function timelineHtml(items){
  return items.map(x=>`
    <div class="timeline-item">
      <div class="timeline-date">${x.date}</div><div class="timeline-axis"><span class="timeline-dot"></span></div>
      <div><div class="timeline-title">${x.title}</div><div class="timeline-desc">${x.type} · ${x.desc}</div></div>
    </div>`).join("");
}
function spark(points, positive=true){
  const w=180,h=34,min=Math.min(...points),max=Math.max(...points),span=max-min||1;
  const pts=points.map((v,i)=>`${i*(w/(points.length-1))},${h-3-(v-min)/(span)*(h-8)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline fill="none" stroke="${positive?"#0a9a63":"#d44848"}" stroke-width="2" points="${pts}"/></svg>`;
}
function renderMarketSnapshot(){
  $("#marketSnapshot").innerHTML=D.markets.map(m=>`
    <div class="market-mini"><div class="market-name">${m.name}</div>
    <div class="market-price">¥${m.price.toFixed(2)}</div>
    <div class="market-meta"><span class="${m.change>=0?"positive":"warning"}">${m.change>=0?"+":""}${m.change}%</span><span>${m.volume}</span></div>
    ${spark(m.points,m.change>=0)}</div>`).join("");
}
function renderPolicies(){
  const q=$("#globalSearch").value.trim().toLowerCase();
  const cat=$("#categoryFilter").value, pub=$("#publisherFilter").value;
  const from=$("#dateFrom").value,to=$("#dateTo").value;
  const rows=D.policies.filter(p=>{
    const text=[p.title,p.doc,p.publisher,p.category,p.market].join(" ").toLowerCase();
    return (!q||text.includes(q))&&(!cat||p.category===cat)&&(!pub||p.publisher===pub)&&(!from||p.date>=from)&&(!to||p.date<=to);
  });
  $("#policyResultCount").textContent=`共 ${rows.length} 条`;
  $("#policyTable").innerHTML=rows.map(p=>`
    <tr><td>${p.date}</td><td class="title-cell">${p.title}</td><td>${p.doc||'<span class="muted">—</span>'}</td>
    <td>${p.publisher}</td><td><span class="badge ${badgeClass(p.category)}">${p.category}</span></td>
    <td>${p.status==="有效"
      ?'<span class="badge status-valid">有效</span>'
      :(p.status==="征求意见"
        ?'<span class="badge status-review">征求意见</span>'
        :'<span class="badge status-invalid">'+p.status+'</span>')
    }</td>
    <td><button class="detail-btn" data-policy="${p.id}">详情</button></td></tr>`).join("");
  $$("[data-policy]").forEach(b=>b.addEventListener("click",()=>openPolicy(+b.dataset.policy)));
}
function openPolicy(id){
  const p=D.policies.find(x=>x.id===id); if(!p)return;
  $("#dialogTitle").textContent=p.title;
  $("#dialogBody").innerHTML=`
    <div class="detail-grid">
      <div class="detail-box"><label>文号</label><div>${p.doc||"未标注文号"}</div></div>
      <div class="detail-box"><label>发布日期</label><div>${p.date}</div></div>
      <div class="detail-box"><label>发布机构</label><div>${p.publisher}</div></div>
      <div class="detail-box"><label>适用市场</label><div>${p.market}</div></div>
      <div class="detail-box"><label>政策分类</label><div>${p.category}</div></div>
      <div class="detail-box"><label>有效状态</label><div>${p.status}</div></div>
    </div>
    <div class="summary-box"><b>政策摘要</b><br>${p.summary}</div>`;
  $("#policyDialog").showModal();
}
$("#closeDialog").addEventListener("click",()=>$("#policyDialog").close());

function renderMarket(){
  $("#marketCards").innerHTML=D.markets.map(m=>`
    <article class="market-card">
      <div class="market-card-top"><div><div class="market-name">${m.name}</div><div class="price">¥${m.price.toFixed(2)}</div></div>
      <span class="badge ${m.change>=0?"green":"red"}">${m.change>=0?"+":""}${m.change}%</span></div>
      ${spark(m.points,m.change>=0)}
      <div class="substats"><div class="substat"><b>${m.volume}</b><span>成交量</span></div>
      <div class="substat"><b>${m.updated}</b><span>更新时间</span></div><div class="substat"><b>演示</b><span>数据状态</span></div></div>
    </article>`).join("");
  const vals=[["T-5",83.2],["T-3",84.1],["T-1",85.9],["T",86.3],["T+1",86.8],["T+3",87.1],["T+5",87.45]];
  $("#windowGrid").innerHTML=vals.map(x=>`<div class="window-cell"><b>¥${x[1]}</b><span>${x[0]}</span></div>`).join("");
}
function renderCompliance(){
  const cols=[["urgent","7日内到期","red"],["upcoming","30日内到期","yellow"],["later","后续节点","blue"]];
  $("#complianceBoard").innerHTML=cols.map(([key,title,color])=>`
    <div class="kanban-col"><div class="kanban-head"><span>${title}</span><span class="badge ${color}">${D.compliance[key].length}</span></div>
    ${D.compliance[key].map(x=>`<article class="kanban-card"><h3>${x.name}</h3><p>${x.market}</p><div class="kanban-meta"><span>${x.owner}</span><b>${x.date}</b></div></article>`).join("")}
    </div>`).join("");
}
function renderParams(){
  $("#parameterTable").innerHTML=D.parameters.map(x=>`<tr><td>${x.type}</td><td class="title-cell">${x.name}</td><td><b>${x.value}</b></td><td>${x.unit}</td><td>${x.market}</td><td>${x.source}</td></tr>`).join("");
}
function renderSources(){
  $("#sourceGrid").innerHTML=D.sources.map(s=>`
    <article class="source-card"><div class="source-top"><div class="source-name">${s.name}</div><span class="badge ${s.status==="正常"?"green":"red"}">${s.status}</span></div>
    <div class="source-url">${s.url}</div><div class="source-meta"><span>最后同步：${s.last}</span><span>本次新增：${s.newCount} 条</span><span>响应：${s.latency}</span></div></article>`).join("");
}

const publishers=[...new Set(D.policies.map(p=>p.publisher))];
$("#publisherFilter").innerHTML+=[...publishers].map(p=>`<option>${p}</option>`).join("");

["input","change"].forEach(evt=>{
  $("#globalSearch").addEventListener(evt,()=>{renderPolicies(); if($("#globalSearch").value) setView("policies")});
  ["#categoryFilter","#publisherFilter","#dateFrom","#dateTo"].forEach(s=>$(s).addEventListener(evt,renderPolicies));
});
$("#resetFilters").addEventListener("click",()=>{["#categoryFilter","#publisherFilter","#dateFrom","#dateTo"].forEach(s=>$(s).value="");renderPolicies()});
$("#advancedBtn").addEventListener("click",()=>setView("policies"));

$("#syncBtn").addEventListener("click",()=>{
  const btn=$("#syncBtn"); btn.disabled=true; btn.textContent="⟳ 同步中…";
  setTimeout(()=>{
    const now=new Date();
    const pad=n=>String(n).padStart(2,"0");
    $("#lastUpdated").textContent=`${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
    btn.disabled=false;btn.textContent="⟳ 同步更新";
    showToast("同步完成：新增 3 条，更新 6 条，1 个数据源异常（演示）");
  },900);
});
function showToast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),3200)}

renderLatest();renderDeadlines();$("#eventTimeline").innerHTML=timelineHtml(D.events.slice(0,4));
$("#fullTimeline").innerHTML=timelineHtml(D.events);
renderMarketSnapshot();renderPolicies();renderMarket();renderCompliance();renderParams();renderSources();
