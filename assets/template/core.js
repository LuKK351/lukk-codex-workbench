/* Calendar dates are interpreted in the user's timezone, not the server's. */
(function(root){
 let ZONE='Asia/Shanghai';
 function setTimeZone(zone){new Intl.DateTimeFormat('en-CA',{timeZone:zone}).format(new Date());ZONE=zone;}
 function asDate(v){return typeof v==='number'?new Date(v*1000):new Date(v.length===10?v+'T00:00:00Z':v);}
 function dayKey(v){if(typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v))return asDate(v).toISOString().slice(0,10);return new Intl.DateTimeFormat('en-CA',{timeZone:ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).format(asDate(v));}
 function age(v,now=new Date().toISOString()){return Math.max(0,Math.floor((Date.parse(dayKey(now))-Date.parse(dayKey(v)))/86400000));}
 function relative(v,now){const n=age(v,now);return n===0?'今天':n===1?'昨天':n<7?n+' 天前':n<30?Math.floor(n/7)+' 周前':n<365?Math.floor(n/30)+' 个月前':Math.floor(n/365)+' 年前';}
 const rangeQueries={today:'今天',yesterday:'昨天',beforeYesterday:'前天',thisWeek:'本周',thisMonth:'本月',lastWeek:'上周',lastMonth:'上个月',week:'最近一周',month:'最近一个月'};
 function rangeBounds(range,now=new Date().toISOString()){
  if(/^days:\d{1,2}$/.test(range||''))return parseQuery('近'+range.split(':')[1]+'天',now).range;
  if(/^\d{4}-\d{2}-\d{2}$/.test(range||'')&&Number.isFinite(Date.parse(range))&&dayKey(range)===range)return {start:range,end:range,label:date(range)};
  if(rangeQueries[range])return parseQuery(rangeQueries[range],now).range;
  if(/^\d{4}-(0[1-9]|1[0-2])$/.test(range||'')){const [y,m]=range.split('-').map(Number);return {start:range+'-01',end:new Date(Date.UTC(y,m,0)).toISOString().slice(0,10),label:y+'年'+m+'月'};}
  return null;
 }
 function inRange(v,range,now=new Date().toISOString()){const bounds=rangeBounds(range,now),day=dayKey(v);if(bounds)return day>=bounds.start&&day<=bounds.end;if(range==='older')return (Date.parse(dayKey(now))-Date.parse(day))/86400000>=30;return true;}

 function date(v){return asDate(v).toLocaleDateString('zh-CN',{timeZone:typeof v==='string'&&v.length===10?'UTC':ZONE,year:'numeric',month:'2-digit',day:'2-digit'});}
 function clock(v){return typeof v==='string'&&v.length===10?'时间未记录':asDate(v).toLocaleTimeString('zh-CN',{timeZone:ZONE,hour12:false,hour:'2-digit',minute:'2-digit'});}

 function dateTime(v){return date(v)+' '+clock(v);}

 function words(q){return [...new Set(String(q||'').normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean))];}
 function matches(text,terms){const body=String(text||'').toLowerCase();return terms.length>0&&terms.every(w=>body.includes(w));}
 function dailyGroups(items,range){
  const days=new Map();
  for(const t of items)for(const n of t.nodes){if(!inRange(n.date,range))continue;const day=dayKey(n.date);if(!days.has(day))days.set(day,new Map());const byThing=days.get(day);if(!byThing.has(t.id))byThing.set(t.id,{thing:t,nodes:[]});const list=byThing.get(t.id).nodes;if(!list.some(x=>x.id===n.id))list.push(n);}
  return [...days].sort((a,b)=>b[0].localeCompare(a[0])).map(([day,things])=>({day,things:[...things.values()].map(g=>({...g,nodes:g.nodes.sort((a,b)=>a.date.localeCompare(b.date))})).sort((a,b)=>b.nodes.at(-1).date.localeCompare(a.nodes.at(-1).date))}));
 }
 const searchIndexes=new WeakMap();
 const compact=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s\p{P}\p{S}]/gu,'');
 const synonymPairs=[['话筒','麦克风'],['麦克疯','麦克风'],['断线','重连'],['掉线','重连'],['蓝芽','蓝牙'],['截图','截屏']];
 function expandedQuery(q){let value=String(q).normalize('NFKC').toLowerCase();for(const [from,to] of synonymPairs)value=value.split(from).join(to);return value;}
 function edits(a,b){if(Math.abs(a.length-b.length)>2)return 99;let prev=Array.from({length:b.length+1},(_,i)=>i);for(let i=1;i<=a.length;i++){const row=[i];for(let j=1;j<=b.length;j++)row[j]=Math.min(row[j-1]+1,prev[j]+1,prev[j-1]+Number(a[i-1]!==b[j-1]));prev=row;}return prev[b.length];}
 function grams(text){const result=new Set();for(let i=0;i<text.length-1;i++)result.add(text.slice(i,i+2));return result;}
 function similarity(query,text){
  const remembered=String(query).replace(/我记得|记不清|之前|那个|好像|有关|关于/g,' ').trim();
  const a=compact(remembered),b=compact(text);if(a.length<2||!b)return 0;if(b.includes(a))return 1;
  if(b.length>=2&&a.includes(b)&&b.length/a.length>=.3)return .55+.2*b.length/a.length;
  if(a.length>=3&&a.length<=32&&b.length>=3&&b.length<=32&&edits(a,b)<=Math.min(2,Math.floor(a.length/3)))return .8;
  const parts=words(remembered).map(compact).filter(x=>x.length>=2);
  const partial=parts.length>1?parts.filter(w=>b.includes(w)).length/parts.length:0;
  const ag=grams(a),bg=grams(b);const overlap=[...ag].filter(x=>bg.has(x)).length;
  // Require two shared bigrams for longer recollections; a single short fragment is too ambiguous.
  const coverage=overlap>=(a.length<=3?1:2)?overlap/ag.size:0;
  return Math.max(partial>=.5?partial*.8:0,coverage>=.5?coverage*.75:0);
 }
 function searchIndex(data){
  if(searchIndexes.has(data))return searchIndexes.get(data);
  const items=[...data.items,...(data.legacyItems||[])],owners=new Map();
  for(const t of items)for(const n of t.nodes){const key=n.thread+':'+n.messageId;if(!owners.has(key))owners.set(key,new Set());owners.get(key).add(t.id);}
  const entries=items.map(t=>({thing:t,anchors:[t.title,...(t.terms||[])],body:[t.summary||t.recap,...(t.decisions||[]).map(d=>d.text),...t.nodes.flatMap(n=>[n.title,eventSummary(n)])].filter(Boolean)}));
  const index={items,owners,entries,cache:new Map()};searchIndexes.set(data,index);return index;
 }
 function suggestions(index,q,existing){
  const expanded=expandedQuery(q),changed=expanded!==String(q).normalize('NFKC').toLowerCase();
  return index.entries.filter(e=>!existing.has(e.thing.id)).map(e=>{
   let score=0,reason='',matched='';
   for(const text of e.anchors){const value=similarity(q,text),alias=changed?similarity(expanded,text):0;if(Math.max(value,alias)>score){score=Math.max(value,alias);reason=alias>value?'按相近说法匹配':'名称或关键词相近';matched=text;}}
   for(const text of e.body){const value=Math.max(similarity(q,text),similarity(expanded,text))*.8;if(value>score){score=value;reason='部分记忆词匹配';matched=text;}}
   if(score<.4)return null;
   const ranked=e.thing.nodes.map(node=>({node,score:Math.max(...[node.title,eventSummary(node),node.quote].map(text=>Math.max(similarity(q,text),similarity(expanded,text))))})).sort((a,b)=>b.score-a.score||b.node.date.localeCompare(a.node.date));
   const best=ranked[0],node=best?.score>=.4?best.node:null;
   return {thing:e.thing,tier:0,score,approx:reason,matched,fields:[{label:'小结',text:e.thing.summary||e.thing.recap,node:node?.id}],nodes:node?[{node,evidence:node.quote,score:best.score}]:[]};
  }).filter(Boolean).sort((a,b)=>b.score-a.score||b.thing.date.localeCompare(a.thing.date)).slice(0,6);
 }
 // All query terms must occur near one another in a quote; distant topics remain searchable in full text.
 function nearby(text,terms,maxSpan=180){
  if(!terms.length)return false;
  const lower=String(text||'').toLowerCase(),hits=[];
  for(let k=0;k<terms.length;k++){let i=-1;while((i=lower.indexOf(terms[k],i+1))>=0)hits.push({at:i,end:i+terms[k].length,k});}
  hits.sort((a,b)=>a.at-b.at);const counts=new Map();let left=0;
  for(let right=0;right<hits.length;right++){const h=hits[right];counts.set(h.k,(counts.get(h.k)||0)+1);while(counts.size===terms.length){if(Math.max(...hits.slice(left,right+1).map(x=>x.end))-hits[left].at<=maxSpan)return true;const first=hits[left++];counts.set(first.k,counts.get(first.k)-1);if(!counts.get(first.k))counts.delete(first.k);}}
  return false;
 }
 function exactSearch(data,q){
  const index=searchIndex(data),cacheKey=words(q).join(' ');if(index.cache.has(cacheKey))return index.cache.get(cacheKey);
  const terms=words(q),groups=new Map(),represented=new Set(),owners=index.owners;
  const ensure=t=>{if(!groups.has(t.id))groups.set(t.id,{thing:t,fields:[],nodes:[],score:0,tier:1});return groups.get(t.id);};
  const field=(t,label,text,score,node)=>{if(!matches(text,terms))return;const g=ensure(t);g.fields.push({label,text,node,score});g.score=Math.max(g.score,score);g.tier=2;};
  for(const t of index.items){
   field(t,'事情名称',t.title,100);
   field(t,'小结',t.summary||t.recap,75);
   for(const term of t.terms||[])field(t,'关键词',term,80);
   for(const d of t.decisions||[])field(t,'决定',d.text,85,d.node);
   // Combining terms is allowed only within this thing's own title and summary.
   if(!groups.has(t.id)&&matches([t.title,t.summary||t.recap].join(' '),terms)){
    const g=ensure(t);g.fields=[{label:'小结',text:t.summary||t.recap,score:65}];g.score=65;g.tier=2;
   }
   const seen=new Set();
   for(const n of t.nodes){
    const local=[['讨论标题',n.title,70],['讨论小结',eventSummary(n),60]];
    const anchor=local.find(([,text])=>matches(text,terms));
    const quoteMatch=nearby(n.quote,terms);
    if(!anchor&&!quoteMatch)continue;
    const key=n.thread+':'+n.messageId;
    // One shared multi-topic quote cannot independently promote several unrelated things.
    if(!anchor&&(owners.get(key)?.size||0)>1&&!groups.has(t.id))continue;
    if(seen.has(key))continue;seen.add(key);
    const [label,text,score]=anchor||['原话提及',n.quote,40];
    const g=ensure(t);g.nodes.push({node:n,evidence:label+'：'+text,score});g.score=Math.max(g.score,score);if(anchor)g.tier=2;
    // Context-only matches never lend relevance to their containing curated thing.
    if(quoteMatch)represented.add(key);
   }
  }
  for(const g of groups.values()){g.fields.sort((a,b)=>b.score-a.score);g.nodes.sort((a,b)=>b.score-a.score||b.node.date.localeCompare(a.node.date));}
  let rawCount=0;const sourceGroups=[];
  for(const t of data.threads||[]){
   const all=t.messages.filter((m,i)=>!(t.inheritedPrefix&&i<t.inheritedPrefix.messages)&&matches(m.text,terms));rawCount+=all.length;
   const messages=all.filter(m=>!represented.has(t.id+':'+m.id)).sort((a,b)=>Number(nearby(b.text,terms))-Number(nearby(a.text,terms))||b.date.localeCompare(a.date));
   const titleMatch=matches(t.title,terms);if(messages.length||titleMatch)sourceGroups.push({thread:t,messages,titleMatch});
  }
  sourceGroups.sort((a,b)=>Number(b.titleMatch)-Number(a.titleMatch)||a.thread.title.localeCompare(b.thread.title,'zh-CN'));
  const result={terms,groups:[...groups.values()].sort((a,b)=>b.tier-a.tier||b.score-a.score||b.thing.date.localeCompare(a.thing.date)),sources:sourceGroups,rawCount,represented};
  result.suggestions=terms.length&&result.groups.filter(g=>g.tier===2).length<3?suggestions(index,q,new Set(groups.keys())):[];
  if(index.cache.size>=40)index.cache.delete(index.cache.keys().next().value);index.cache.set(cacheKey,result);return result;
 }
 // Interpret dates only as a leading search constraint, never inside a remembered quote.
 function parseQuery(q,now=new Date().toISOString()){
  let text=String(q||'').normalize('NFKC').trim(),range=null;
  const prefix=/^(?:(?:帮我|请|我想|能不能)?(?:找一下|找找|查一下|搜索|找|查)(?:一下)?[，,\s]*)?/;
  const head=text.replace(/^(?:我记得|记得|好像是|好像)[，,\s]*/,'').replace(prefix,'');
  const m=head.match(/^(今天|昨天|前天|这周|本周|上周|这个月|本月|上个月|上月|最近(?:一周|一个月|\d{1,2}天)|近\d{1,2}天)/);
  if(m){
   const today=dayKey(now),utc=Date.parse(today),shift=n=>new Date(utc+n*86400000).toISOString().slice(0,10);
   let start=today,end=today;const label=m[0],weekday=(new Date(utc).getUTCDay()+6)%7;
   if(label==='昨天')start=end=shift(-1);else if(label==='前天')start=end=shift(-2);
   else if(/周/.test(label)&&!label.startsWith('最近')){start=shift(-weekday-(label==='上周'?7:0));end=label==='上周'?shift(-weekday-1):today;}
   else if(/本月|这个月|上月|上个月/.test(label)){const d=new Date(utc);d.setUTCDate(1);if(label.startsWith('上')){end=new Date(d.getTime()-86400000).toISOString().slice(0,10);d.setUTCMonth(d.getUTCMonth()-1);}start=d.toISOString().slice(0,10);}
   else if(/最近|^近/.test(label)){const n=label==='最近一周'?7:label==='最近一个月'?30:Number(label.match(/\d+/)?.[0]);start=shift(1-Math.max(1,n));}
   range={start,end,label};text=head.slice(label.length).replace(/^(?:我们)?(?:聊过的|讨论过的|聊的|讨论的|的)?[，,\s]*/,'').trim();
  }
  if(range&&/^(?:我们)?(?:都)?(?:聊了什么|聊过什么|说了什么|有哪些讨论|有什么讨论|讨论了什么)[？?]?$/.test(text))text='';
  return {text,range};
 }
 const segmenter=typeof Intl.Segmenter==='function'?new Intl.Segmenter('zh',{granularity:'word'}):null;
 const stopWords=new Set('我 你 他 她 我们 这个 那个 那些 这些 之前 以前 记得 记不清 好像 有关 关于 一下 找到 找找 查找 搜索 讨论 聊过 说过 什么 怎么 怎么样 为什么 是否 需要 可以 还是 已经 后来 当时 现在 最近 事情 内容 东西 问题 存在 不存在 检索 帮忙 帮我 觉得 有点 比较 好的 继续 之前的 接到 过去 变成'.split(' '));
 function canonical(s){return expandedQuery(plainExcerpt(s)).replace(/创建日期|日期/g,'时间').replace(/搬过去|搬到|搬运|挪过去|导入/g,'迁移').replace(/封皮/g,'封面');}
 function queryTokens(q){
  const text=canonical(q),segments=segmenter?[...segmenter.segment(text)].filter(x=>x.isWordLike).map(x=>x.segment):text.match(/[a-z0-9]+|[\u4e00-\u9fff]{2}/g)||[];
  return [...new Set(segments.filter(s=>s.length>=2&&!stopWords.has(s)))].slice(0,16);
 }
 function scopedData(data,range){
  const index=searchIndex(data),key=range.start+':'+range.end;
  index.scopes ||= new Map();if(index.scopes.has(key))return index.scopes.get(key);
  const included=x=>!x.timePrecision?.includes('消息时间缺失')&&dayKey(x.date)>=range.start&&dayKey(x.date)<=range.end;
  const items=rows=>rows.map(t=>{const nodes=t.nodes.filter(included);return {...t,nodes,summary:'',recap:'',date:nodes.at(-1)?.date,decisions:(t.decisions||[]).filter(d=>nodes.some(n=>n.id===d.node))};}).filter(t=>t.nodes.length);
  const threads=(data.threads||[]).map(t=>({...t,inheritedPrefix:undefined,messages:t.messages.filter((m,i)=>!(t.inheritedPrefix&&i<t.inheritedPrefix.messages)&&included(m))})).filter(t=>t.messages.length);
  const result={...data,items:items(data.items),legacyItems:items(data.legacyItems||[]),threads};
  if(index.scopes.size>=8)index.scopes.delete(index.scopes.keys().next().value);index.scopes.set(key,result);return result;
 }
 function naturalIndex(data){
  const index=searchIndex(data);if(index.natural)return index.natural;
  const entries=index.items.map(t=>({thing:t,anchor:canonical([t.title,...(t.terms||[]),t.summary||t.recap].join(' ')),nodes:t.nodes.map(n=>({node:n,anchor:canonical(n.title+' '+eventSummary(n)),text:canonical(n.quote)}))}));
  const rows=(data.threads||[]).flatMap(t=>t.messages.filter((m,i)=>!(t.inheritedPrefix&&i<t.inheritedPrefix.messages)).map(m=>({thread:t,message:m,text:canonical(m.text)})));
  return index.natural={entries,rows};
 }
 function naturalRecall(data,q,existing,represented){
  const index=searchIndex(data),{entries,rows}=naturalIndex(data),tokens=queryTokens(q);
  if(tokens.length<2)return {groups:[],sources:[],terms:tokens};
  const weights=tokens.map(term=>1+Math.min(3,Math.log((entries.length+1)/(1+entries.filter(e=>e.anchor.includes(term)||e.nodes.some(n=>n.anchor.includes(term))).length))));
  const total=weights.reduce((a,b)=>a+b,0);
  function score(text){let best=0;for(let i=0;i<text.length;i+=200){const part=text.slice(i,i+320),hits=tokens.map(t=>part.includes(t)),count=hits.filter(Boolean).length,coverage=hits.reduce((v,yes,j)=>v+(yes?weights[j]:0),0)/total;if(count>=2&&count>=Math.ceil(tokens.length*.6)&&coverage>=.6)best=Math.max(best,coverage);}return best;}
  const groups=[];
  for(const e of entries){
   if(existing.has(e.thing.id))continue;
   const direct=score(e.anchor),ranked=e.nodes.map(n=>{const anchor=score(n.anchor),quote=(index.owners.get(n.node.thread+':'+n.node.messageId)?.size||0)<=1?score(n.text):0;return {node:n.node,evidence:n.node.quote,score:Math.max(anchor,quote*.8)};}).filter(n=>n.score>0).sort((a,b)=>b.score-a.score||b.node.date.localeCompare(a.node.date));
   const anchorShare=tokens.filter(t=>e.anchor.includes(t)).length/tokens.length;
   const best=ranked[0],value=Math.max(direct*1.15,(best?.score||0)+(best?anchorShare*.15:0));if(!value)continue;
   const target=best?.node||e.thing.nodes.at(-1);
   groups.push({thing:e.thing,tier:0,approx:'按整句中的关键线索匹配',score:value,fields:best?[]:[{label:'小结',text:e.thing.summary||e.thing.recap,node:target?.id}],nodes:best?ranked.slice(0,5):target?[{node:target,evidence:target.quote,score:value}]:[]});
  }
  groups.sort((a,b)=>b.score-a.score||b.thing.date.localeCompare(a.thing.date));
  const selected=groups.slice(0,6),used=new Set(represented);
  for(const g of selected)for(const {node:n} of g.nodes)used.add(n.thread+':'+n.messageId);
  const sources=new Map();
  for(const row of rows){if(used.has(row.thread.id+':'+row.message.id))continue;const value=score(row.text);if(!value)continue;if(!sources.has(row.thread.id))sources.set(row.thread.id,{thread:row.thread,messages:[],titleMatch:false,approx:true});sources.get(row.thread.id).messages.push({...row.message,searchScore:value});}
  for(const s of sources.values())s.messages.sort((a,b)=>b.searchScore-a.searchScore||b.date.localeCompare(a.date));
  return {groups:selected,sources:[...sources.values()].sort((a,b)=>b.messages[0].searchScore-a.messages[0].searchScore),terms:tokens};
 }
 function searchData(data,q,now=new Date().toISOString(),selectedRange){
  const index=searchIndex(data),parsed=parseQuery(q,now),key=ZONE+'|'+dayKey(now)+'|'+(selectedRange||'inferred')+'|'+words(q).join(' ');
  if(selectedRange)parsed.range=rangeBounds(selectedRange,now);
  index.queries ||= new Map();if(index.queries.has(key))return index.queries.get(key);
  const scoped=parsed.range?scopedData(data,parsed.range):data,text=parsed.text;
  let result;
  if(parsed.range&&!text){
   const represented=new Set();const groups=searchIndex(scoped).items.map(t=>{const nodes=[...t.nodes].reverse().map(n=>{represented.add(n.thread+':'+n.messageId);return {node:n,evidence:n.quote,score:1};});return {thing:t,tier:2,score:1,fields:[],nodes};});
   groups.sort((a,b)=>b.thing.date.localeCompare(a.thing.date));
   result={terms:[],groups,suggestions:[],represented,rawCount:scoped.threads.reduce((n,t)=>n+t.messages.length,0),sources:scoped.threads.map(t=>({thread:t,titleMatch:false,messages:t.messages.filter(m=>!represented.has(t.id+':'+m.id))})).filter(t=>t.messages.length)};
  }else{
   const exact=exactSearch(scoped,text);result={...exact,suggestions:[...exact.suggestions],sources:[...exact.sources]};
   if(text&&result.groups.filter(g=>g.tier===2).length<3){
    const recall=naturalRecall(scoped,text,new Set(result.groups.map(g=>g.thing.id)),result.represented);
    const merged=new Map(recall.groups.map(g=>[g.thing.id,g]));for(const g of result.suggestions){const boosted={...g,score:g.score*1.3,nodes:g.nodes.length?g.nodes:(merged.get(g.thing.id)?.nodes||[])};if(!merged.has(g.thing.id)||merged.get(g.thing.id).score<boosted.score)merged.set(g.thing.id,boosted);}
    result.suggestions=[...merged.values()].sort((a,b)=>b.score-a.score||b.thing.date.localeCompare(a.thing.date)).slice(0,6);
    const byThread=new Map(result.sources.map(s=>[s.thread.id,{...s,messages:[...s.messages]}]));
    const shown=new Set(result.represented);for(const g of result.suggestions)for(const {node:n} of g.nodes)shown.add(n.thread+':'+n.messageId);
    for(const s of recall.sources){if(!byThread.has(s.thread.id))byThread.set(s.thread.id,{...s,messages:[]});const dest=byThread.get(s.thread.id),ids=new Set(dest.messages.map(m=>m.id));for(const m of s.messages)if(!ids.has(m.id))dest.messages.push(m);}
    result.sources=[...byThread.values()].map(s=>({...s,messages:s.messages.filter(m=>!shown.has(s.thread.id+':'+m.id))})).filter(s=>s.titleMatch||s.messages.length);
    result.terms=[...new Set([...result.terms,...recall.terms])];
   }
  }
  if(parsed.range)for(const g of [...result.groups,...result.suggestions]){if(!g.nodes.length){const n=g.thing.nodes.at(-1);if(n)g.nodes=[{node:n,evidence:n.quote,score:0}];}for(const f of g.fields)if(!f.node)f.node=g.nodes[0]?.node.id;}
  for(const g of result.suggestions)if(!g.nodes.length){const n=g.thing.nodes.at(-1);if(n)g.nodes=[{node:n,evidence:n.quote,score:0}];}
  result.approxRawCount=result.sources.reduce((n,s)=>n+s.messages.filter(m=>m.searchScore).length,0);
  result.timeRange=parsed.range;result.withoutTime=parsed.range?text:null;
  if(index.queries.size>=40)index.queries.delete(index.queries.keys().next().value);index.queries.set(key,result);return result;
 }

 function excerpts(text,terms,radius=55){
  const value=String(text||''),lower=value.toLowerCase(),ranges=[];
  for(const w of terms){const i=lower.indexOf(w);if(i>=0)ranges.push([Math.max(0,i-radius),Math.min(value.length,i+w.length+radius)]);}
  if(!ranges.length)return value.slice(0,160)+(value.length>160?'…':'');
  ranges.sort((a,b)=>a[0]-b[0]);const merged=[];for(const r of ranges){const last=merged.at(-1);if(last&&r[0]<=last[1])last[1]=Math.max(last[1],r[1]);else merged.push(r);}
  return merged.map(([a,b])=>(a?'…':'')+value.slice(a,b)+(b<value.length?'…':'')).join(' … ');
 }
 function plainExcerpt(text){return String(text||'').replace(/!\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/\[([^\]]+)\]\((?:<[^>]*>|[^)])*\)/g,'$1').replace(/(?:\/Users\/|\/private\/)[^\s<>]+/g,'[本地文件路径]').replace(/https?:\/\/[^\s<>]+/g,'[链接]').replace(/\*\*|__|`+/g,'').replace(/^\s{0,3}#{1,6}\s+/gm,'').replace(/\s+/g,' ').trim();}
 function eventSummary(n){const text=String(n.event||'').replace(/[；，。]?具体说法见下方原话[。]?/g,'').trim();return text.replace(/[。；]$/,'')===String(n.title).replace(/[。；]$/,'')?'':text;}
 const api={setTimeZone,asDate,dayKey,age,relative,inRange,rangeBounds,date,clock,dateTime,words,matches,nearby,parseQuery,queryTokens,dailyGroups,searchData,excerpts,plainExcerpt,eventSummary};if(typeof module==='object')module.exports=api;else root.Workbench=api;
})(typeof window!=='undefined'?window:globalThis);
