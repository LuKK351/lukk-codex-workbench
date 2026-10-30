'use strict';
let data;
const viewPositions=new Map();
const viewDisclosures=new Map();
let renderedView=null;
function viewKey(hash){const p=new URLSearchParams(hash.slice(1));if(!p.size)p.set('tab','all');if(p.get('tab')==='time')p.delete('day');p.sort();return p.toString();}
function disclosureKey(el){
 const owner=el.closest('article'),day=el.closest('.day-group');
 const ownerKey=owner?.id||owner?.querySelector('[data-task-id]')?.dataset.taskId||owner?.querySelector('h3 a')?.getAttribute('href')||'';
 const label=el.querySelector('summary')?.textContent.replace(/\d+/g,'#').trim()||'';
 // Stable card identity avoids restoring an expanded panel onto a different card after moves.
 return [day?.id||'',ownerKey,el.className,label].join('|');
}
function rememberView(){if(renderedView===null)return;const panels=new Map();for(const el of app.querySelectorAll?.('details:not(.month-picker)')||[])panels.set(disclosureKey(el),el.open);const input=app.querySelector?.('input[name="q"]');viewDisclosures.set(renderedView,{panels,draft:input?.value});if(viewDisclosures.size>100)viewDisclosures.delete(viewDisclosures.keys().next().value);}
function restoreView(preserve=false){const saved=viewDisclosures.get(renderedView);if(!saved)return;for(const el of app.querySelectorAll?.('details:not(.month-picker)')||[]){const key=disclosureKey(el);if(saved.panels.has(key))el.open=saved.panels.get(key);}const input=app.querySelector?.('input[name="q"]');if(input&&saved.draft!==undefined&&(preserve||!state().q))input.value=saved.draft;}

const C=Workbench, app=document.querySelector('#app');
function savedSet(key){try{return new Set(JSON.parse(localStorage.getItem(key)||'[]'));}catch{return new Set();}}
const favorites=savedSet('lukk-favorites-v3');
const dismissedTasks=savedSet('lukk-dismissed-tasks-v1');
const confirmedTasks=savedSet('lukk-confirmed-tasks-v1');
function confirmTask(id,confirm){if(!data.tasks.some(t=>t.id===id&&t.level!=='有明确接续'))return;confirm?confirmedTasks.add(id):confirmedTasks.delete(id);persist('lukk-confirmed-tasks-v1',confirmedTasks);lastDismissedTask=null;}
let lastDismissedTask=null;
function changeTaskVisibility(id,hide){if(!data.tasks.some(t=>t.id===id))return;hide?dismissedTasks.add(id):dismissedTasks.delete(id);lastDismissedTask=hide?id:null;persist('lukk-dismissed-tasks-v1',dismissedTasks);}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state=()=>Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
const link=o=>'#'+new URLSearchParams(Object.entries(o).filter(([,v])=>v!==undefined&&v!=='')).toString();
const go=o=>{viewPositions.set(location.hash,window.scrollY);const h=link(o);if(location.hash===h)render();else location.hash=h;};
const href=(t,n,extra={})=>link({item:t.id,...(n?{node:n.id}:{}),...extra});
const allThings=()=>[...data.items,...(data.legacyItems||[])];
const getThing=id=>allThings().find(t=>t.id===id);
const stamp=d=>`<time title="${esc(C.date(d))}">${esc(C.relative(d))}<span> · ${esc(C.date(d))}</span></time>`;
function highlight(text,terms){const value=String(text||''),lower=value.toLowerCase(),ranges=[];for(const w of terms){let start=0,i;while((i=lower.indexOf(w,start))>=0){ranges.push([i,i+w.length]);start=i+w.length;}}ranges.sort((a,b)=>a[0]-b[0]);const merged=[];for(const r of ranges){const last=merged.at(-1);if(last&&r[0]<=last[1])last[1]=Math.max(last[1],r[1]);else merged.push(r);}let result='',at=0;for(const [a,b] of merged){result+=esc(value.slice(at,a))+'<mark>'+esc(value.slice(a,b))+'</mark>';at=b;}return result+esc(value.slice(at));}
function readable(text){
 const raw=String(text||'');let formatted=false;
 function inline(value){
  const tokens=[];
  const token=html=>{tokens.push(html);return '\u0000'+(tokens.length-1)+'\u0000';};
  let chunk=value.replace(/(`+)([^\n]*?)\1/g,(_,ticks,code)=>token('<code>'+esc(code)+'</code>'));
  chunk=chunk.replace(/(!?)\[([^\]\n]*)\]\((?:<([^>\n]+)>|([^\s)]+))\)/g,(_,image,label,angle,url)=>{
   formatted=true;const target=angle||url,caption=label||(image?'未命名图片':'链接');
   const safe=/^https?:\/\//i.test(target);
   return token(image?'<span class="attachment-note">图片 · '+esc(caption)+' <small>未载入附件</small></span>':safe?'<a class="message-link" href="'+esc(target)+'" target="_blank" rel="noopener noreferrer">'+esc(caption)+' ↗</a>':'<span class="attachment-note">文件 · '+esc(caption)+'</span>');
  });
  return esc(chunk).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/^#{1,6} (.+)$/gm,'<strong class="message-heading">$1</strong>').replace(/\u0000(\d+)\u0000/g,(_,n)=>tokens[Number(n)]||'');
 }
 function cells(line){
  const parts=[];let cell='',codeTicks=0,separators=0;
  const s=line.trim();
  for(let i=0;i<s.length;i++){
   if(s[i]==='\\'&&s[i+1]==='|'){cell+='|';i++;continue;}
   if(s[i]==='`'){let end=i+1;while(s[end]==='`')end++;const size=end-i;if(!codeTicks)codeTicks=size;else if(size===codeTicks)codeTicks=0;cell+=s.slice(i,end);i=end-1;continue;}
   if(s[i]==='|'&&!codeTicks){parts.push(cell.trim());cell='';separators++;}else cell+=s[i];
  }
  parts.push(cell.trim());
  if(!separators)return null;
  if(s.startsWith('|'))parts.shift();
  if(parts.at(-1)===''&&s.endsWith('|'))parts.pop();
  return parts;
 }
 function blocks(chunk){
  const lines=chunk.split('\n'),out=[];let plain=[];
  const flush=()=>{if(plain.length){let value=plain.join('\n');if(out.at(-1)?.startsWith('<div class="message-table-scroll"'))value=value.replace(/^\n+/,'');out.push(inline(value));plain=[];}};
  for(let i=0;i<lines.length;i++){
   const header=cells(lines[i]),rule=i+1<lines.length?cells(lines[i+1]):null;
   if(!header||!rule||header.length!==rule.length||!rule.every(c=>/^:?-{3,}:?$/.test(c))){plain.push(lines[i]);continue;}
   while(plain.at(-1)==='')plain.pop();flush();formatted=true;
   const align=rule.map(c=>c.startsWith(':')&&c.endsWith(':')?'center':c.endsWith(':')?'right':'left');
   const row=(values,tag)=>'<tr>'+header.map((_,j)=>`<${tag}${tag==='th'?' scope="col"':''} class="align-${align[j]}">${inline(values[j]||'')}</${tag}>`).join('')+'</tr>';
   const rows=[];i++;
   while(i+1<lines.length){const values=cells(lines[i+1]);if(!values)break;rows.push(row(values,'td'));i++;}
   out.push('<div class="message-table-scroll" tabindex="0" role="region" aria-label="原文表格，可横向滚动"><table class="message-table"><thead>'+row(header,'th')+'</thead><tbody>'+rows.join('')+'</tbody></table></div>');
  }
  flush();return out.join('');
 }
 const body=raw.split(/```[^\n]*\n([\s\S]*?)```/g).map((chunk,i)=>i%2?'<pre><code>'+esc(chunk)+'</code></pre>':blocks(chunk)).join('');
 return body+(formatted?'<details class="original-text"><summary>查看原始文本</summary><pre>'+esc(raw)+'</pre></details>':'');
}
function sourceLink(id,title,terms=[]){const label=terms.length?highlight(title,terms):esc(title);return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id||'')?`<a class="source-shortcut" href="codex://threads/${encodeURIComponent(id)}" title="在 Codex 打开：${esc(title)}" aria-label="在 Codex 打开：${esc(title)}">${label} <span class="ui-arrow external" aria-hidden="true">↗</span></a>`:label;}
function sourceNames(t,terms=[]){const sources=[...new Map(t.nodes.map(n=>[n.thread,n])).values()];return `<span class="source-links">${sources.map(n=>sourceLink(n.thread,n.sourceTitle,terms)).join('')}</span>`;}
function sourceCount(t){return new Set(t.nodes.map(n=>n.thread)).size;}

function typeBadge(t){const type=data.types.find(x=>x.id===t.type);return type?`<span class="type-badge">${esc(type.name)}</span>`:'';}
function typeFilters(s){return `<div class="filters type-filters" role="group" aria-label="事情类型筛选"><span>事情类型</span>${[{id:'',name:'全部类型'},...data.types.filter(x=>x.id!=='unclassified'||allThings().some(t=>t.type===x.id))].map(x=>`<a class="filter ${(s.type||'')===x.id?'selected':''}" ${(s.type||'')===x.id?'aria-current="true"':''} href="${link({...s,type:x.id})}">${esc(x.name)}</a>`).join('')}</div>`;}

function localBack(value,fallback){return typeof value==='string'&&(value==='#'||/^#[a-zA-Z]/.test(value))?value:fallback;}
function toast(s){const e=document.querySelector('#toast');e.textContent=s;e.style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>e.style.display='none',3000);}
function persist(key,set){try{localStorage.setItem(key,JSON.stringify([...set]));return true;}catch{toast('未能保存到浏览器，本次打开期间仍有效');return false;}}
function icon(name){const shapes={search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',back:'<path d="M20 12H4m6-6-6 6 6 6"/>'};return `<svg class="icon icon-${name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[name]||''}</svg>`;}
function fav(t,compact=false){const saved=favorites.has(t.id);return `<button class="favorite ${saved?'on':''}" data-favorite="${t.id}" aria-pressed="${saved}" title="${saved?'取消收藏':'收藏'}" aria-label="${saved?'取消收藏':'收藏'}：${esc(t.title)}">${icon('star')}${compact?'':saved?' 已收藏':' 收藏'}</button>`;}
function searchForm(q=''){return `<form class="search" id="search"><span class="search-icon">${icon('search')}</span><input name="q" aria-label="搜索聊过的内容" placeholder="搜索全部讨论，输入关键词或一句描述" value="${esc(q)}" maxlength="300"><button class="primary">搜索</button></form>`;}
function tabs(tab){return `<nav class="tabs" aria-label="主要导航">${[['all','事情总览'],['tasks','可以接着做'],['time','每日回顾'],['favorites','收藏']].map(([v,n])=>`<a class="tab ${v===tab?'active':''}" ${v===tab?'aria-current="page"':''} href="${link({tab:v})}">${n}${v==='favorites'&&favorites.size?` <small>${favorites.size}</small>`:''}</a>`).join('')}</nav>`;}
function filters(s){const isDiscussion=s.tab==='time'||!!s.q;const basis=isDiscussion?'按讨论发生日期筛选':'按最近一次讨论日期筛选';const bounds=C.rangeBounds(s.range);const rangeText=bounds?' · '+C.date(bounds.start)+(bounds.end!==bounds.start?'—'+C.date(bounds.end):''):'';const dates=isDiscussion?data.items.flatMap(t=>t.nodes.map(n=>n.date)):s.tab==='tasks'?data.tasks.map(t=>t.date):allThings().map(t=>t.date);const months=[...new Set(dates.map(d=>C.dayKey(d).slice(0,7)))].sort().reverse();const selected=/^\d{4}-\d{2}$/.test(s.range||'')?s.range:'';return `<section class="time-filter" aria-label="时间范围筛选"><div class="filter-heading"><strong>时间范围</strong><span>${basis}${esc(rangeText)}</span></div><div class="filters time-options" role="group" aria-label="时间范围选项">${[['any','全部时间'],['today','今天'],['yesterday','昨天'],['thisWeek','本周'],['lastWeek','上周'],...(bounds&&(['beforeYesterday','thisMonth','lastMonth','week','month'].includes(s.range)||s.range?.startsWith('days:')||/^\d{4}-\d{2}-\d{2}$/.test(s.range||''))?[[s.range,bounds.label]]:[]),...(s.range==='older'?[['older','30天前']]:[])].map(([v,n])=>`<a class="filter ${(s.range||'any')===v?'selected':''}" href="${link({...s,range:v,day:undefined})}" ${(s.range||'any')===v?'aria-current="true"':''}>${n}</a>`).join('')}<details class="month-picker" id="month-filter"><summary class="filter month-trigger ${selected?'selected':''}" aria-label="选择月份">${selected?selected.slice(0,4)+'年'+Number(selected.slice(5))+'月':'选择月份'}</summary><nav class="month-menu" aria-label="按月份筛选"><span class="month-menu-label">选择讨论月份</span>${months.map(m=>`<a class="month-option ${m===selected?'selected':''}" ${m===selected?'aria-current="true"':''} href="${link({...s,range:m,day:undefined})}"><span>${m.slice(0,4)}年${Number(m.slice(5))}月</span><span class="month-check" aria-hidden="true">${m===selected?'✓':''}</span></a>`).join('')}</nav></details></div></section>`;}

function backLabel(hash){const s=Object.fromEntries(new URLSearchParams((hash||'').slice(1)));if(s.item)return '返回：'+(getThing(s.item)?.title||'事情详情');if(s.q)return '返回搜索结果';if(s.sources)return '返回对话目录';return '返回'+({tasks:'可以接着做',all:'事情总览',time:'每日回顾',favorites:'收藏'}[s.tab||'all']||'事情总览');}
function sourceDirectoryLink(s=state()){return s.sources?link({sources:'1',back:localBack(s.back,'#tab=all')}):link({sources:'1',back:link(s)});}
function scopeNote(){return `<footer class="footnote"><span>已收录 ${data.threads.length} 个对话 · ${data.items.length} 件事</span><span>${data.threads.length?'最近整理 '+esc(C.dateTime(data.organizedAt||data.snapshot)):'尚未收录'} · 非实时同步</span><button class="textbtn" data-about>收录情况</button><a class="textlink" href="${sourceDirectoryLink()}">已收录的对话 <span class="ui-arrow" aria-hidden="true">→</span></a></footer>`;}
function decisions(t,extra={}){return (t.decisions||[]).length?`<details class="decision-history"><summary>决定与变化 · ${t.decisions.length} 条</summary><div class="decisions">${t.decisions.map(d=>`<a class="decision" href="${href(t,t.nodes.find(n=>n.id===d.node),{...extra,branch:undefined})}"><span class="badge">${esc(d.label)}</span><span>${esc(d.text)}</span><small>${esc(C.date(d.date))} →</small></a>`).join('')}</div></details>`:'';}
function empty(title,text,action={href:link({tab:'all'}),label:'浏览事情总览 →'}){return `<div class="empty"><h2>${title}</h2><p>${text}</p>${action?`<a class="anchor" href="${esc(action.href)}">${esc(action.label)}</a>`:''}</div>`;}
function background(t){
 const summary=(t.summary||t.recap||'').trim();
 const parts=[t.recap,t.openQuestion].filter(Boolean).map(x=>x.trim()).filter(x=>x!==summary&&!/^(记录的是当时讨论与完成回执|根据已收录对话整理；完成回执与用户采用分开记录)/.test(x));
 const unique=[...new Set(parts)];return unique.length?`<details class="background"><summary>背景与补充说明</summary>${unique.map(x=>`<p>${esc(x)}</p>`).join('')}</details>`:'';
}
function contextPanel(n){const messages=(n.context||[]).filter(m=>m.id!==n.messageId);return messages.length?`<details class="context-details"><summary>查看相邻消息 · ${messages.length} 条</summary>${messages.map(m=>`<div class="context-message"><label>${m.role==='user'?'你的原话':'Codex 当时回复'} · ${esc(C.date(m.date))}</label><div class="message-body">${readable(m.text)}</div></div>`).join('')}</details>`:'';}

function row(t,s){return `<article class="thing-row"><div class="row-top"><h3><a href="${href(t,null,{from:s.tab||'all',range:s.range,returnTo:link(s)})}">${esc(t.title)}</a></h3><div class="row-meta">${stamp(t.date)}${t.nodes.some(n=>n.timePrecision?.includes("消息时间缺失"))?'<small>消息日期未知</small>':''}${fav(t,true)}</div></div>${typeBadge(t)}<p class="recap">${esc(t.summary||t.recap)}</p><div class="row-bottom"><div class="source-line"><span>全部来源 · ${sourceCount(t)}</span>${sourceNames(t)}</div><a class="textlink" href="${href(t,null,{from:s.tab||'all',range:s.range,returnTo:link(s)})}">查看讨论 <span class="ui-arrow" aria-hidden="true">→</span></a></div></article>`;}
function taskCard(task,s,removed=false){const t=getThing(task.item),n=t.nodes.find(n=>n.id===task.node);return `<article class="task-card"><div class="row-top"><h3><a href="${href(t,n,{from:'tasks',range:s.range,returnTo:link(s)})}">${esc(task.title||t.title)}</a></h3>${fav(t,true)}</div><div class="row-time">最后相关讨论 ${stamp(task.date)}</div><p class="stop-summary">${esc(task.stop)}</p><div class="source-line"><span>来源对话</span><span>${sourceLink(task.thread,task.sourceTitle)}</span></div><div class="task-footer"><details class="task-reason"><summary>停点依据</summary><p>${esc(task.reason)}</p>${confirmedTasks.has(task.id)?'<p class="muted">已在当前浏览器确认接续。</p>':''}</details>${!removed&&task.level!=='有明确接续'?`<button class="textbtn" data-task-confirm="${confirmedTasks.has(task.id)?'undo':'confirm'}" data-task-id="${esc(task.id)}" aria-label="${confirmedTasks.has(task.id)?'退回待确认':'移到可以接着做'}：${esc(t.title)}">${confirmedTasks.has(task.id)?'退回待确认':'移到可以接着做'}</button>`:''}<button class="textbtn" data-task-visibility="${removed?'restore':'hide'}" data-task-id="${esc(task.id)}" aria-label="${removed?'恢复显示':'不再显示'}：${esc(t.title)}">${removed?'恢复显示':'不再显示'}</button><a class="textlink card-read" href="${href(t,n,{from:'tasks',range:s.range,returnTo:link(s)})}">查看讨论 <span class="ui-arrow" aria-hidden="true">→</span></a></div></article>`;}
function tasks(s){
 const available=data.tasks.filter(t=>!dismissedTasks.has(t.id)&&C.inRange(t.date,s.range));
 const live=available.filter(t=>t.level==='有明确接续'||confirmedTasks.has(t.id)),uncertain=available.filter(t=>t.level!=='有明确接续'&&!confirmedTasks.has(t.id));
 const removed=data.tasks.filter(t=>dismissedTasks.has(t.id));
 return `${lastDismissedTask&&dismissedTasks.has(lastDismissedTask)?`<p class="list-note" role="status">已从此栏目移出，仍可在事情总览和搜索中找到。<button class="textbtn" data-task-visibility="restore" data-task-id="${esc(lastDismissedTask)}">撤销</button></p>`:''}<div class="sectionhead"><h2>接续事项</h2><span class="muted">${live.length} 件</span></div><p class="view-description">依据已收录的讨论整理，可能尚未包含其他窗口或线下的后续进展。</p>${live.length?live.map(t=>taskCard(t,s)).join(''):empty('当前时间范围内，没有显示的接续事项',s.range&&s.range!=='any'?'可切换到全部时间查看其他接续事项。':uncertain.length?'可在下方“进展待确认”中处理候选事项。':'已收录的讨论仍保留在事情总览中。',s.range&&s.range!=='any'?{href:link({...s,range:'any'}),label:'查看全部接续事项 →'}:uncertain.length?null:undefined)}${uncertain.length?`<details class="uncertain-group" open><summary>进展待确认 <span>${uncertain.length}</span></summary><p class="muted">对话中尚未明确是否继续，可移入接续事项或不再显示。</p>${uncertain.map(t=>taskCard(t,s)).join('')}</details>`:''}${removed.length?`<details class="uncertain-group"><summary>已移出 · ${removed.length} 件</summary><p class="muted">移出记录保存在当前浏览器，清除本站数据后会丢失。此处显示所有时间范围内的已移出事项。</p>${removed.map(t=>taskCard(t,s,true)).join('')}</details>`:''}`;
}
function timeline(s){const days=C.dailyGroups(data.items,s.range);return days.length?days.map(({day,things})=>`<section class="day-group" id="day-${day}"><div class="day-heading"><h2>${esc(C.date(day))}</h2><span>${esc(C.relative(day))} · ${things.length} 件事</span></div><div class="day-events">${things.map(({thing:t,nodes})=>{const latest=nodes.at(-1);const summary=data.dailySummaries?.[day+'|'+t.id]||(nodes.length===1?C.eventSummary(latest)||latest.title:[...new Set(nodes.map(n=>n.title))].slice(0,2).join(' · ')+(nodes.length>2?' 等 '+nodes.length+' 段讨论':''));const extra={from:'time',range:s.range,returnTo:link({...s,day})};return `<article class="event"><div class="row-top"><h3><a href="${href(t,latest,extra)}">${esc(t.title)}</a></h3>${fav(t,true)}</div><p class="event-summary">${esc(summary)}</p><div class="source-line"><span>当天来源 · ${sourceCount({nodes})}</span>${sourceNames({nodes})}</div>${nodes.some(n=>n.timePrecision?.includes("消息时间缺失"))?'<p class="muted">消息日期未知，暂按窗口创建日归组。</p>':''}<details class="day-discussions"><summary>展开当天 ${nodes.length} 段讨论</summary>${nodes.map(n=>`<a class="day-discussion" href="${href(t,n,extra)}"><time>${n.timePrecision?.includes("消息时间缺失")?"时间未知":esc(C.clock(n.date))}</time><div><strong>${esc(n.title)}</strong>${C.eventSummary(n)?`<p>${esc(C.eventSummary(n))}</p>`:""}${new Set(nodes.map(x=>x.thread)).size>1?`<small>来源对话：${esc(n.sourceTitle)}</small>`:''}</div><span>→</span></a>`).join('')}</details></article>`;}).join('')}</div></section>`).join(''):empty('这个范围暂未收录讨论','没有记录不代表没有聊过，可以切换到全部时间。',{href:link({...s,range:'any',day:undefined}),label:'查看全部日期 →'});}
function home(s){if(!data.threads.length){app.innerHTML=`<section class="hero compact"><h1>Codex 对话整理工作台</h1><p class="muted">按事情找回讨论，按日期回看变化。</p></section>${empty('还没有收录对话','请在 Codex 中使用“对话整理工作台” Skill，选择时间范围并完成首次整理。',null)}${scopeNote()}`;return;}let tab=s.tab||'all';if(['recent','paused'].includes(tab))tab='all';s={...s,tab};const titles={tasks:['可以接着做','从已收录对话中整理可能尚未结束的事情、进行中的项目，以及可能继续推进或讨论的内容。'],all:['事情总览','一件事一张卡，汇总历次讨论、当前进展与全部来源。'],time:['每日回顾','按日期看当天聊了什么、有哪些变化。同一件事可在不同日期出现，只列当天涉及的来源。'],favorites:['收藏','临时收藏的事情，方便再次回看。']};const title=titles[tab]||titles.all;const rows=(tab==='favorites'?allThings():s.collection==='previous'?(data.legacyItems||[]):data.items).filter(t=>C.inRange(t.date,s.range)&&(!s.type||t.type===s.type)&&(tab!=='favorites'||favorites.has(t.id))).sort((a,b)=>b.date.localeCompare(a.date));const content=tab==='tasks'?tasks(s):tab==='time'?timeline(s):rows.length?`<div class="sectionhead"><h2>${tab==='favorites'?'我的收藏':s.collection==='previous'?'此前样本':'全部事情'}</h2><span class="muted">${rows.length} 件 · 按已收录的最近讨论排序</span></div>${rows.map(t=>row(t,s)).join('')}`:empty(tab==='favorites'?(favorites.size?'当前筛选下没有收藏的事情':'这里还没有收藏的事情'):'当前筛选下没有事情',tab==='favorites'?(favorites.size?'收藏仍然保留，可以清除筛选后查看。':'点击事情旁的 ☆ 即可收藏。'):'可清除类型与时间筛选，重新查看。',tab==='favorites'?(favorites.size?{href:link({tab:'favorites',range:'any'}),label:'查看全部收藏 →'}:undefined):{href:link({tab:'all',range:'any'}),label:'清除筛选 →'});app.innerHTML=`<section class="hero compact"><div><h1>${title[0]}</h1><p class="muted">${title[1]}</p></div></section>${searchForm()}${tabs(tab)}${s.collection==='previous'?`<p class="sample-notice">以下是旧版局部样本，未在本轮重整，状态可能已变化；保留供找回与收藏。<a href="#tab=all" class="textlink">返回本轮 ${data.items.length} 件事 <span class="ui-arrow" aria-hidden="true">→</span></a></p>`:""}${tab==='favorites'&&!favorites.size?'':filters(s)}${tab==='all'||(tab==='favorites'&&favorites.size)?typeFilters(s):''}${tab==='all'?'<p class="list-note">跨日期、跨窗口合并整理 · 来源对话保留原标题</p>':''}${tab==='favorites'?'<p class="storage-note">收藏保存在当前浏览器，关闭浏览器或重启电脑通常不会丢失。清除本站数据、删除浏览器用户配置或结束无痕会话后会丢失，换浏览器或访问地址不会同步。</p>':''}${content}${scopeNote()}`;}
function search(s){
 const q=s.q||'',found=C.searchData(data,q,undefined,s.range),terms=found.terms;
 const timeSelection=s.range||({今天:'today',昨天:'yesterday',前天:'beforeYesterday',这周:'thisWeek',本周:'thisWeek',本月:'thisMonth',这个月:'thisMonth',上周:'lastWeek',上个月:'lastMonth',上月:'lastMonth',最近一周:'week',最近一个月:'month'}[found.timeRange?.label])||(found.timeRange&&/^(?:近|最近)\d+天$/.test(found.timeRange.label)?'days:'+found.timeRange.label.match(/\d+/)[0]:'any');
 const excerpt=text=>highlight(C.excerpts(C.plainExcerpt(text),terms).replace(/(?:…\s*){2,}/g,'… '),terms);
 const cards=groups=>groups.map(g=>{
  const t=g.thing,extra={q,returnTo:link(s)},best=g.nodes[0];
  const field=g.fields.find(f=>!['事情名称','关键词'].includes(f.label))||g.fields[0];
  const text=field?(['事情名称','关键词'].includes(field.label)?t.summary||t.recap:field.text):best?.evidence||t.summary||t.recap;
  const target=field?.node?t.nodes.find(n=>n.id===field.node):best?.node;
  const nodes=g.nodes.map(({node:n,evidence})=>`<a class="match-node" href="${href(t,n,extra)}"><strong>${highlight(n.title,terms)}</strong><time>${esc(C.date(n.date))}</time><p>${excerpt(evidence)}</p><small>来源对话：${esc(n.sourceTitle)}</small></a>`).join('');
  return `<article class="result search-group"><div class="row-top"><h3><a href="${href(t,target,extra)}">${highlight(t.title,terms)}</a></h3>${fav(t,true)}</div>${t.collection==='previous'?'<span class="badge">旧样本 · 未重新核查</span>':''}${g.approx?`<span class="badge">${esc(g.approx)}</span>`:''}<p class="match-excerpt">${excerpt(text)}</p><div class="source-line"><span>来源对话</span><span>${sourceNames(t,terms)}</span></div>${nodes?`<details class="matched-nodes"><summary>查看 ${g.nodes.length} 段匹配讨论</summary>${nodes}</details>`:''}<a class="textlink card-read" href="${href(t,target,extra)}">查看讨论 <span class="ui-arrow" aria-hidden="true">→</span></a></article>`;
 }).join('');
 const current=found.groups.filter(g=>g.thing.collection!=='previous'&&g.tier===2),mentioned=found.groups.filter(g=>g.thing.collection!=='previous'&&g.tier===1),old=found.groups.filter(g=>g.thing.collection==='previous');
 const sources=found.sources.map(({thread:t,messages,titleMatch})=>{
  const hits=messages.slice(0,80).map(m=>`<a class="match-node" href="${link({thread:t.id,message:m.id,back:link(s)})}"><small>${m.role==='user'?'你的原话':'Codex 当时回复'} · ${esc(C.date(m.date))}${m.searchScore?' · 按整句线索匹配':''}</small><p>${excerpt(m.text)}</p><span class="textlink">阅读前后文 →</span></a>`).join('');
  return `<article class="result"><h3><a href="${link({thread:t.id,back:link(s)})}">${highlight(t.title,terms)}</a></h3><p class="muted">来源对话${titleMatch?' · 窗口名匹配':''}${messages.length?' · '+messages.length+' 条其他原文':''}</p>${messages.length?`<details class="matched-nodes" ${!found.groups.length?'open':''}><summary>查看原文匹配</summary>${hits}${messages.length>80?'<p>先显示最近 80 条，请增加关键词缩小范围。</p>':''}</details>`:''}</article>`;
 }).join('');
 const searchBack=localBack(s.back,"#tab=all");
 app.innerHTML=`<div class="breadcrumbs"><a href="${esc(searchBack)}">← ${esc(backLabel(searchBack))}</a><span>/ 搜索结果</span></div><h1>搜索结果</h1>${searchForm(q)}${filters({...s,range:timeSelection})}<p class="search-summary">${current.length} 件相关事情${found.suggestions.length?' · '+found.suggestions.length+' 件相近候选':''}${mentioned.length?' · '+mentioned.length+' 件仅原话提及':''}${old.length?' · '+old.length+' 件旧样本':''} · ${found.rawCount} 条全文匹配${found.approxRawCount?' · '+found.approxRawCount+' 条相近原文':''}</p><p class="muted search-explainer">搜索全部已收录讨论；相近候选保留原文供核对。</p>${cards(current)}${found.suggestions.length?`<details class="older-search" ${!current.length?'open':''}><summary>可能是你要找的 · ${found.suggestions.length} 件</summary><p class="muted">根据相近说法、少量错字或部分关键词匹配的候选事情。</p>${cards(found.suggestions)}</details>`:''}${mentioned.length?`<details class="older-search" ${!current.length?'open':''}><summary>仅在原话中提及 · ${mentioned.length} 件</summary><p class="muted">这些讨论出现了关键词，不一定以它为主题。</p>${cards(mentioned)}</details>`:''}${old.length?`<details class="older-search"><summary>旧样本中的匹配 · ${old.length} 件</summary>${cards(old)}</details>`:''}${sources?`<details class="raw-results" ${!found.groups.length?'open':''}><summary>来源对话与其他全文匹配 · ${found.sources.length} 个对话</summary><p class="muted">保留窗口名、全文和整句线索命中；相近原文单独标明，上方已展示的原话不重复列出。</p>${sources}</details>`:''}${!found.groups.length&&!found.suggestions.length&&!sources?empty('没有找到匹配的内容',found.timeRange?'可切换到“全部时间”，或换一个关键词再找。没有命中不代表从未聊过。':'可以换一个具体词，例如“表盘”“重连”。没有命中不代表从未聊过。'):''}`;
}
function detail(s){const t=getThing(s.item);if(!t){app.innerHTML=empty('这件事暂未收录','可以返回事情总览。');return;}const work=t.workBranches||[],branch=work.includes(s.branch)?s.branch:'全部';const nodes=t.nodes.filter(n=>branch==='全部'||n.branch===branch);const n=nodes.find(n=>n.id===s.node)||nodes.at(-1);const extra={from:s.from,range:s.range,q:s.q,returnTo:s.returnTo};const back=localBack(s.returnTo,s.q?link({q:s.q}):link({tab:s.from||'all',range:s.range}));const names={tasks:'可以接着做',all:'事情总览',time:'每日回顾',favorites:'收藏'};const related=(t.related||[]).map(getThing).filter(Boolean);app.innerHTML=`<div class="breadcrumbs"><a href="${esc(back)}"><span class="ui-arrow back" aria-hidden="true">←</span> ${esc(backLabel(back))}</a><span>/ 讨论详情</span></div><div class="detailtitle"><h1>${esc(t.title)}</h1>${fav(t)}</div><div class="detail-time"><span class="status-pill">${esc(t.status||'此前样本')}</span>最后讨论 ${stamp(t.date)}</div>${t.collection==='previous'?'<p class="sample-notice">旧版样本，未在本轮重新核查。</p>':''}<p class="detail-recap">${esc(t.summary||t.recap)}</p>${background(t)}${work.length?`<nav class="worklines" aria-label="相关窗口分工"><a class="workline ${branch==='全部'?'active':''}" href="${href(t,null,{...extra,branch:'全部'})}"><strong>全部讨论</strong></a>${work.map(b=>{const latest=t.nodes.filter(n=>n.branch===b).at(-1);return `<a class="workline ${branch===b?'active':''}" href="${href(t,latest,{...extra,branch:b})}"><strong>${esc(b)}</strong><small>来源对话：${esc(latest.sourceTitle)}</small></a>`;}).join('')}</nav>`:''}${decisions(t,extra)}<div class="detailgrid"><aside class="timeline"><div class="timelinehead">讨论经过 · ${nodes.length} 段</div>${[...nodes].reverse().map(x=>`<a class="node ${x.id===n.id?'active':''}" ${x.id===n.id?'aria-current="true"':''} href="${href(t,x,{...extra,branch})}"><span class="date">${esc(C.date(x.date))}${work.length?' · '+esc(x.branch):''}</span><strong>${esc(x.title)}</strong></a>`).join('')}${related.length?`<div class="related">相关事情${related.map(r=>`<a class="related-link" href="${href(r,null,{returnTo:link(s)})}">${esc(r.title)} <span class="ui-arrow" aria-hidden="true">→</span></a>`).join('')}</div>`:''}</aside><section class="reader" id="selected-discussion" aria-label="讨论原文" tabindex="-1"><div class="readhead"><h2>${esc(n.title)}</h2><span class="muted">${esc(C.date(n.date))} · ${n.timePrecision?.includes("消息时间缺失")?"时间未知":esc(C.clock(n.date))}</span></div>${n.timePrecision?.includes("消息时间缺失")?'<p class="sample-notice">消息时间缺失，上方日期是窗口创建日期。</p>':''}${C.eventSummary(n)?`<p class="event-note"><span class="ai-label">小结</span>${esc(C.eventSummary(n))}</p>`:""}<span class="badge">${n.quoteRole==='assistant'?'Codex · 当时回复':'你的原话'}</span><div class="message-body quote">${readable(n.quote)}</div><div class="source-line"><span>来源对话</span><span>${esc(n.sourceTitle)}</span></div>${contextPanel(n)}<div class="actions">${data.threads?.some(x=>x.id===n.thread)?`<a href="${link({thread:n.thread,message:n.messageId,back:link({...s,node:n.id,branch})})}">查看收录原文 <span class="ui-arrow" aria-hidden="true">→</span></a>`:''}<a href="${link({tab:'time',range:C.dayKey(n.date),day:C.dayKey(n.date)})}">回看这一天</a></div><p class="source-note">可从列表的来源对话名尝试打开 Codex；这里保留已收录原文。</p></section></div>${scopeNote()}`;}
function renderWithoutMotion(preserve=false){if(!data)return;rememberView();const s=state();if(s.thread)sourceReader(s);else if(s.sources)sourceIndex(s);else if(s.item)detail(s);else if(s.q)search(s);else home(s);renderedView=viewKey(location.hash);restoreView(preserve);document.title=(s.item?(getThing(s.item)?.title||'讨论详情')+' · ':s.thread?'对话原文 · ':s.sources?'已收录的对话 · ':s.q?'查找：'+s.q+' · ':'')+'Codex 对话整理工作台';if(preserve)return;if(viewPositions.has(location.hash)){window.scrollTo(0,viewPositions.get(location.hash));return;}if(s.message)document.getElementById('message-'+s.message)?.scrollIntoView({block:'center'});else if(s.node&&s.item)document.getElementById('selected-discussion')?.scrollIntoView({block:'start'});else if(s.day)document.getElementById('day-'+s.day)?.scrollIntoView({block:'start'});else window.scrollTo(0,0);}
function sourceIndex(s){const back=localBack(s.back,'#tab=all');app.innerHTML=`<div class="breadcrumbs"><a href="${esc(back)}"><span class="ui-arrow back" aria-hidden="true">←</span> ${esc(backLabel(back))}</a></div><h1>已收录的对话</h1><p class="muted">${data.threads.length} 个来源对话，按最近讨论排序，包含未被选入事情详情的消息。点击阅读已收录原文。</p>${[...data.threads].sort((a,b)=>b.date.localeCompare(a.date)).map(t=>`<a class="result source-index-card" href="${link({thread:t.id,back:link(s)})}"><h3>${esc(t.title)} <span class="ui-arrow" aria-hidden="true">→</span></h3><p>${t.messages.length} 条消息 · ${esc(C.date(t.messages[0].date))} 至 ${esc(C.date(t.messages.at(-1).date))}${t.messages.some(m=>m.timePrecision?.includes('消息时间缺失'))?' · 部分日期按窗口创建日归组':''}</p></a>`).join('')}`;}
function sourceReader(s){const t=data.threads.find(t=>t.id===s.thread);if(!t){app.innerHTML=empty('这个窗口尚未收录','请返回对话目录查看已收录的窗口。',{href:link({sources:'1'}),label:'返回对话目录 →'});return;}const fallback=s.backItem?link({item:s.backItem,node:s.backNode}):s.q?link({q:s.q}):'#sources=1';const back=localBack(s.back,fallback);app.innerHTML=`<div class="breadcrumbs"><a href="${esc(back)}"><span class="ui-arrow back" aria-hidden="true">←</span> ${esc(backLabel(back))}</a></div><div class="card-label">来源对话</div><h1>${esc(t.title)}</h1><p class="sample-notice">${t.messages.length} 条消息 · 采集于 ${t.checked||data.checked}，未实时同步。${t.messages.some(m=>m.timePrecision?.includes("消息时间缺失"))?"消息时间缺失，暂显示窗口创建日期。":"时间为每轮对话的开始时间。"}附件内容未读取。${t.inheritedPrefix?"前 "+t.inheritedPrefix.messages+" 条继承自原窗口，全文保留，搜索不重复计数。":""}</p><div class="transcript">${t.messages.map(m=>`<article id="message-${esc(m.id)}" class="transcript-message ${s.message===m.id?'target':''}"><label>${m.role==='user'?'你的原话':'Codex 当时回复'} · ${esc(C.date(m.date))} ${m.timePrecision?.includes("消息时间缺失")?"消息时间未知":esc(C.clock(m.date))}</label><div class="message-body">${readable(m.text)}</div></article>`).join('')}</div>`;}
function showAbout(){const total=data.threads.reduce((n,t)=>n+t.messages.length,0);document.querySelector('#scope-description').innerHTML=`<div class="coverage-stats"><div><strong>${data.threads.length}</strong><span>对话窗口</span></div><div><strong>${data.items.length}</strong><span>件事情</span></div></div><p class="coverage-updated">${data.threads.length?'最近整理：'+esc(C.dateTime(data.organizedAt||data.snapshot)):'尚未完成首次收录'}</p>${data.collectionCutoff?`<p>本轮读取截止：${esc(C.dateTime(data.collectionCutoff))}（${esc(C.timeZoneLabel())}）。此后的讨论需下次更新，实际覆盖见下方收录范围。</p>`:'<p>页面根据已保存的对话整理，尚未实时同步。</p>'}<section class="coverage-status"><h3>当前收录范围</h3><p>${esc(data.scopeDescription)}</p><p>当前不包含 ChatGPT 对话和附件内容。</p></section><details class="coverage-details"><summary>详细说明</summary><p>${total} 条消息 · ${data.items.reduce((v,t)=>v+t.nodes.length,0)} 段讨论 · ${data.items.reduce((v,t)=>v+t.decisions.length,0)} 条决定与变化。</p><p>分批采集于 ${esc(data.checked)}，每个来源对话标明采集日期。部分早期消息缺少时间，按窗口创建日归组并单独标明。</p><p>事情名称、小结和停点由 AI 根据对话整理，不代表源项目的实时进展。原话保留，可在详情中核对。</p></details><div class="dialog-actions"><a class="secondary" data-close-about href="${sourceDirectoryLink()}">查看已收录对话 <span class="ui-arrow" aria-hidden="true">→</span></a></div>`;document.querySelector('#about').showModal();}
document.querySelector('#scope').onclick=showAbout;document.querySelector('#close-about').onclick=()=>document.querySelector('#about').close();
app.addEventListener('submit',e=>{if(e.target.id==='search'){e.preventDefault();const q=new FormData(e.target).get('q').trim();if(!q){e.target.querySelector('input[name="q"]').focus();toast('请输入要查找的内容');return;}const current=state();go({q,range:current.range,back:current.q?current.back:link(current)});}});
app.addEventListener('click',e=>{if(e.target.closest('a[href^="#"]'))viewPositions.set(location.hash,window.scrollY);const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-about'))showAbout();if(b.dataset.taskConfirm){const confirmed=b.dataset.taskConfirm==='confirm';confirmTask(b.dataset.taskId,confirmed);render(true);toast(confirmed?'已移到上方接续事项':'已退回进展待确认');return;}if(b.dataset.taskVisibility){changeTaskVisibility(b.dataset.taskId,b.dataset.taskVisibility==='hide');render(true);return;}if(b.dataset.favorite){const id=b.dataset.favorite;favorites.has(id)?favorites.delete(id):favorites.add(id);persist('lukk-favorites-v3',favorites);const y=window.scrollY;render(true);window.scrollTo(0,y);toast(favorites.has(id)?'已收藏，可从收藏页找回':'已取消收藏');}});
// Keep the month disclosure usable with both pointer and keyboard.
window.addEventListener('click',e=>{const picker=document.querySelector('.month-picker[open]');if(picker&&(!picker.contains(e.target)||e.target.closest('.month-option')))picker.open=false;});
window.addEventListener('keydown',e=>{
 const picker=document.querySelector('.month-picker');if(!picker||!picker.contains(e.target))return;
 const trigger=picker.querySelector('summary'),options=[...picker.querySelectorAll('.month-option')];
 if(e.key==='Escape'){e.preventDefault();picker.open=false;trigger.focus();return;}
 if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
  e.preventDefault();picker.open=true;let i=options.indexOf(document.activeElement);
  if(e.key==='Home')i=0;else if(e.key==='End')i=options.length-1;else if(i<0)i=e.key==='ArrowUp'?options.length-1:Math.max(0,options.findIndex(x=>x.hasAttribute('aria-current')));else i=(i+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;
  options[i]?.focus();
 }
});
app.addEventListener('focusout',e=>{const picker=e.target.closest('.month-picker');if(picker&&e.relatedTarget&&!picker.contains(e.relatedTarget))picker.open=false;});
document.querySelector('#about').addEventListener('click',e=>{if(e.target.closest('[data-close-about]')){viewPositions.set(location.hash,window.scrollY);document.querySelector('#about').close();}});
window.addEventListener('hashchange',()=>render());
fetch('data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('data');return r.json();}).then(d=>{data=d;C.setTimeZone(d.timezone||'Asia/Shanghai');render();render.last=state().item;}).catch(error=>{console.error('Workbench load/render failed',error);app.innerHTML='<h1>页面暂时没有加载成功</h1><p>请通过本机服务打开，然后刷新重试。</p>';});

// Only animate actual navigation. Favorite/status updates retain their position.
const motionPreference=window.matchMedia('(prefers-reduced-motion: reduce)');
let motionTabsObserver;
function render(preserve=false){
  if(!data)return;
  const before=motionSnapshot();
  const favoriteFocus=preserve?document.activeElement?.dataset.favorite:null;
  renderWithoutMotion(preserve);
  motionAfter(before,preserve);
  if(favoriteFocus)app.querySelector(`[data-favorite="${CSS.escape(favoriteFocus)}"]`)?.focus({preventScroll:true});
}
function motionSnapshot(){
  const tab=app.querySelector('.tab.active');
  return {tab:tab?.getBoundingClientRect(),key:app.dataset.motionKey};
}
function motionAfter(before,preserve){
  const s=state();
  const key=s.item?'item:'+s.item:s.thread?'thread:'+s.thread:s.sources?'sources':s.q?'search':'home';
  app.dataset.motionKey=key;
  if(!s.q&&!s.item&&!s.thread&&!s.sources&&(s.tab||'all')==='tasks')app.querySelector('.empty')?.classList.add('empty-compact');
  const nav=app.querySelector('.tabs'),active=nav?.querySelector('.tab.active');
  motionTabsObserver?.disconnect();
  if(active){
    const bar=document.createElement('span');bar.className='tabs-indicator';bar.setAttribute('aria-hidden','true');
    bar.style.left=active.offsetLeft+'px';bar.style.width=active.offsetWidth+'px';nav.append(bar);nav.classList.add('has-indicator');
    motionTabsObserver=new ResizeObserver(()=>{bar.style.left=active.offsetLeft+'px';bar.style.width=active.offsetWidth+'px';});
    motionTabsObserver.observe(nav);
    if(before.tab&&!preserve&&!motionPreference.matches){
      const rect=active.getBoundingClientRect();
      bar.animate([{transform:`translateX(${before.tab.left-rect.left}px) scaleX(${before.tab.width/rect.width})`},{transform:'none'}],{duration:320,easing:'cubic-bezier(.22,1,.36,1)'});
      bar.style.transformOrigin='left';
    }
  }
  const hero=app.querySelector('.hero');
  if(hero?.querySelector(':scope>div')){
    hero.insertAdjacentHTML('beforeend',`<svg class="thread-art" viewBox="0 0 250 100" aria-hidden="true" focusable="false">
      <path class="thread" pathLength="100" d="M0 13C90 13 110 50 170 50H244"/>
      <path class="thread" pathLength="100" d="M0 50H244"/>
      <path class="thread" pathLength="100" d="M0 87C90 87 110 50 170 50H244"/>
      <path class="trace" pathLength="100" d="M0 13C90 13 110 50 170 50H244"/>
      <path class="trace" pathLength="100" d="M0 50H244"/>
      <path class="trace" pathLength="100" d="M0 87C90 87 110 50 170 50H244"/>
      <circle class="junction" cx="180" cy="50" r="4"/><circle class="junction" cx="240" cy="50" r="4"/>
    </svg>`);
    // The illustration runs once on arrival, never while filtering or saving.
    if(before.key||preserve)hero.querySelectorAll('.trace').forEach(el=>el.style.animation='none');
  }
  if(preserve||motionPreference.matches||document.hidden)return;
  // Do not fade the search form, focused controls, or previously restored reading position.
  const samePage=before.key===key;
  const candidates=[...app.children].filter(el=>!el.matches('form,nav,.footnote,.filters,.time-filter,.storage-note,.list-note,.sample-notice'));
  let i=0;
  for(const el of candidates){
    if(samePage&&!el.matches('.thing-row,.task-card,.day-group,.result,.empty,.detailgrid'))continue;
    const r=el.getBoundingClientRect();
    if(r.bottom<0||r.top>innerHeight||i>=5)continue;
    el.animate([{opacity:.45,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:240,delay:i++*20,fill:'backwards',easing:'cubic-bezier(.22,1,.36,1)'});
  }
}
motionPreference.addEventListener('change',()=>{
  if(motionPreference.matches)document.getAnimations().forEach(a=>a.cancel());
});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden)document.getAnimations().forEach(a=>a.cancel());
});
