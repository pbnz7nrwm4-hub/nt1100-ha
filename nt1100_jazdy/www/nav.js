/* Zakładka „Nawigacja” strony dodatku NT1100 Jazdy.
   Ładowany po index.html; korzysta z jego pomocników (el, api, fmt, loadLeaflet, isHA, tab, detail).
   Na stronie skrzynki ten plik nie jest serwowany (404) i zakładka się nie pojawia. */
(function(){
'use strict';
const NV={data:null,map:null,pts:[],legs:[],skip:[],rt:null,mk:[],lines:[],plan:null,sel:null,mode:'add',poi:null,poiOn:false,shown:null,ready:false,locked:false,fit:null};
const VCOL={szybko:'#3d8bfd',lekko:'#40c057',kreto:'#f76707',bardzo:'#e03131',mix:'#7950f2'};
// nazwy wariantów razem z „Mój plan” (trasa z odcinków o różnych wariantach)
const VARS=()=>NV.data.variants.concat([NV.data.mix||['mix','Mój plan']]);
const VN=v=>(VARS().find(x=>x[0]===v)||[v,v])[1];
const SHORT={szybko:'szybko',lekko:'lekko',kreto:'kręto',bardzo:'b. kręto'};
const AVN={gruntowe:'drogi gruntowe (polne, leśne)',szutrowe:'drogi szutrowe',platne:'drogi płatne',autostrady:'autostrady',promy:'promy'};
const KIND={1:['fotoradar','#e03131'],2:['odcinkowy pomiar – początek','#e03131'],3:['odcinkowy pomiar – koniec','#e03131'],10:['stacja paliw','#1c7ed6'],11:['restauracja','#f08c00'],12:['kawiarnia','#a0522d'],13:['punkt widokowy','#2f9e44'],14:['przełęcz','#087f5b'],15:['nocleg','#7950f2'],16:['ładowarka','#15aabf'],17:['sklep/serwis moto','#d6336c'],18:['miejsce piknikowe','#94d82d']};
const CATS=[['Stacje','10'],['Jedzenie','11'],['Kawa','12'],['Nocleg','15'],['Widoki','13,14,18'],['Serwis moto','17'],['Ładowarki','16']];
const LEG=[[1,'fotoradar / odcinek'],[10,'stacja paliw'],[11,'restauracja'],[12,'kawiarnia'],[15,'nocleg'],[13,'widok / przełęcz / piknik'],[17,'serwis moto'],[16,'ładowarka']];
const css=document.createElement('style');
css.textContent='#navmap{height:420px;border-radius:10px;background:var(--card2)}#navmap.add{cursor:crosshair}'+
'.npt{display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}.npt:last-child{border:0}.npt .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.npt .lb{flex:0 0 58px;font-size:12px;color:var(--mut)}.npt button{padding:4px 8px;font-size:13px}'+
'.nsr{position:relative}.nsr ul{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--card);max-height:220px;overflow:auto}.nsr li{padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--line)}.nsr li:hover{background:var(--card2)}.nsr li small{display:block}'+
'.nrt.ndrv{border:1px solid var(--acc);border-radius:10px;padding:10px 12px;margin:0 0 8px}.nrt.ndrv[hidden]{display:none}.nveh{margin:2px 0 8px}.nveh .chip{font-size:14px;padding:6px 14px}.nfav .chip.nadd{border-style:dashed;color:var(--mut)}.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.chip{font-size:13px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--card2);cursor:pointer}.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}'+
'.nres{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:10px;margin:6px 0;cursor:pointer}.nres.on{border-color:var(--acc)}.nres .sw{width:12px;height:12px;border-radius:50%;flex:0 0 12px}.nres .tx{flex:1;min-width:0}.nres small{display:block}'+
'.nrt{display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}.nrt:last-child{border:0}.nrt .tx{flex:1;min-width:0}.nrt small{display:block}.nrt .cur{font-size:11px;padding:2px 7px;border-radius:8px;background:var(--ok);color:#fff}'+
'.nrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.nrow input{flex:1;min-width:160px;padding:9px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card2)}'+
'.nleg[hidden]{display:none}.nleg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--mut);margin:6px 0}.nleg span{display:inline-flex;align-items:center;gap:5px}.nleg i{width:11px;height:11px;border-radius:50%;display:inline-block;border:1.5px solid #fff}'+
'.npo{display:flex;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}.npo:last-child{border:0}.npo i{width:11px;height:11px;border-radius:50%;flex:0 0 11px}.npo .tx{flex:1;min-width:0}.npo small{display:block;color:var(--mut)}.npo button{padding:4px 9px;font-size:13px}.nlist{max-height:340px;overflow:auto}'+
'.nlg{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:2px 0 6px 66px;font-size:12px;color:var(--mut)}.nlg .chip{font-size:12px;padding:3px 9px;display:inline-flex;align-items:center;gap:5px}.nlg .chip i{width:8px;height:8px;border-radius:50%;display:inline-block}.nlg .chip.on{background:var(--card);color:var(--txt,inherit);border-width:2px}'+
'.nsl{display:grid;grid-template-columns:110px 1fr 38px;gap:4px 10px;align-items:center;font-size:13px;margin:4px 0}.nsl input[type=range]{width:100%}.nsl b{grid-column:1/-1;margin-top:8px;font-size:14px;display:flex;align-items:center;gap:6px}.nsl b i{width:10px;height:10px;border-radius:50%;display:inline-block}.nsl output{text-align:right;color:var(--mut)}'+
'.nlv{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13px}.nlv input{width:70px;padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--card2)}'+
'.nlock{background:var(--card);border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.35);display:flex;flex-direction:column;overflow:hidden}.nlock button{border:0;border-radius:0;background:var(--card);color:inherit;width:38px;height:38px;font-size:18px;padding:0;cursor:pointer}.nlock button+button{border-top:1px solid var(--line)}'+
'.nrt{flex-wrap:wrap}.nrt .tx{flex:1 1 220px}.nrt .acts{flex:0 1 auto}'+
'details.ngrp{border-top:1px solid var(--line);margin-top:8px}details.ngrp>summary{cursor:pointer;font-weight:600;padding:12px 0;list-style:none;display:flex;justify-content:space-between}details.ngrp>summary::-webkit-details-marker{display:none}details.ngrp>summary::after{content:"▸";color:var(--mut)}details.ngrp[open]>summary::after{content:"▾"}'+
'.nsl input[type=range]{padding:0;margin:0;height:26px;border:0;background:none}.nsl{row-gap:2px}'+
'html,body{overscroll-behavior:none}#navmap.nfull{position:fixed!important;left:0;top:0;width:100vw;height:100vh;height:100dvh;z-index:10000;border-radius:0;touch-action:none}body.nfull-on{overflow:hidden;touch-action:none}'+
'.ntoast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:rgba(20,24,36,.92);color:#fff;padding:9px 14px;border-radius:10px;font-size:14px;z-index:10001;pointer-events:none;max-width:90vw;text-align:center}'+
'@media(max-width:600px){.nlg{padding-left:8px}}#navmap.locked.add{cursor:grab}'+
'.nmsg{margin:6px 0;font-size:14px}.nmsg.bad{color:var(--bad)}.nmsg.ok{color:var(--ok)}.ndev{font-size:13px;color:var(--mut)}'+
/* 1.5.0: zakładka Trasy = mapa na cały ekran + wysuwany panel */
'body.ntab header.top,body.ntab footer{display:none}body.ntab main{padding:0;max-width:none}body.ntab{overflow:hidden;padding-bottom:0}'+
'#nwrap{position:fixed;left:0;right:0;top:0;bottom:calc(64px + env(safe-area-inset-bottom,0px))}#nwrap #navmap{position:absolute;inset:0;height:auto;border-radius:0}'+
'#nwrap .leaflet-top{top:calc(64px + env(safe-area-inset-top,0px))}'+
'.nbar{position:absolute;left:10px;right:10px;top:calc(10px + env(safe-area-inset-top,0px));z-index:900;display:flex;flex-direction:column;gap:8px;pointer-events:none}.nbar>*{pointer-events:auto}'+
'.nbar .nrow{flex-wrap:nowrap}.nbar .nrow input{height:46px;border-radius:12px;background:var(--card);box-shadow:0 2px 10px rgba(0,0,0,.35);min-width:0}.nbar .nrow button{height:46px;border-radius:12px;background:var(--card);box-shadow:0 2px 10px rgba(0,0,0,.35)}.nbar ul{box-shadow:0 6px 18px rgba(0,0,0,.4)}'+
'.ntrip{align-self:flex-start;display:flex;align-items:center;gap:8px;border-radius:10px;padding:8px 12px;font-size:13px;font-weight:500;background:color-mix(in srgb,var(--acc2) 22%,var(--card));border:1px solid var(--acc2);color:var(--ink);cursor:pointer}.ntrip i{width:8px;height:8px;border-radius:4px;background:var(--acc2)}'+
'.nsheet{position:absolute;left:0;right:0;bottom:0;z-index:950;background:var(--card);border-top:1px solid var(--line);border-radius:18px 18px 0 0;box-shadow:0 -6px 24px rgba(0,0,0,.35);display:flex;flex-direction:column;height:var(--sh,46%);max-height:calc(100% - 72px);transition:height .2s}'+
'.nsheet.drag{transition:none}.ngrab{padding:9px 0 5px;display:flex;justify-content:center;cursor:grab;touch-action:none;flex:none}.ngrab i{width:44px;height:5px;border-radius:3px;background:var(--line)}'+
'.nsc{overflow:auto;padding:0 14px 24px;overscroll-behavior:contain;flex:1;-webkit-overflow-scrolling:touch}.nsc .card{background:none;border:0;padding:0;margin:0;border-radius:0}'+
'.nsc .card>b:first-child{font-size:17px;color:var(--ink);text-transform:none;letter-spacing:0;margin:2px 0 8px}.nsec{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}'+
'.nhead{display:flex;justify-content:space-between;align-items:baseline;gap:8px}.nhead small{color:var(--mut)}'+
'.npt{padding:4px 0;border:0}.npt .dt{width:12px;height:12px;border-radius:6px;flex:0 0 12px;background:var(--ink)}.npt .dt.s{background:var(--ok)}.npt .dt.c{background:var(--bad)}.npt button{padding:5px 9px}'+
'.nleg2{display:flex;align-items:center;gap:10px;padding:2px 0 2px 4px}.nleg2 .bar{width:4px;height:30px;border-radius:2px;background:var(--line)}'+
'.lpill{height:32px;border-radius:16px;padding:0 13px;font-size:13px;font-weight:600;display:inline-flex;align-items:center;gap:6px;background:var(--card2)}.lpill i{width:9px;height:9px;border-radius:5px}'+
'.npick{position:fixed;inset:0;z-index:10002;background:rgba(5,9,18,.5);display:flex;align-items:flex-end;justify-content:center}.npick>div{background:var(--card);border-radius:20px 20px 0 0;width:100%;max-width:560px;padding:12px 16px calc(20px + env(safe-area-inset-bottom,0px));display:flex;flex-direction:column;gap:10px}'+
'.npick h3{margin:4px 0 0;font-size:18px}.npick .opt{display:flex;align-items:center;gap:12px;text-align:left;padding:12px 14px;border-radius:12px;min-height:56px}.npick .opt i{width:14px;height:14px;border-radius:7px;flex:none}.npick .opt span{flex:1;display:flex;flex-direction:column}.npick .opt small{color:var(--mut)}.npick .opt.on{border-width:2px}'+
'.npick .row2{display:flex;gap:8px}.npick .row2 button{flex:1}'+
'.ncard{border:1px solid var(--line);background:var(--card2);border-radius:14px;padding:12px 14px;margin:8px 0;cursor:pointer;display:flex;flex-direction:column;gap:6px}.ncard.on{border-width:2px}.ncard .h{display:flex;justify-content:space-between;align-items:center;gap:8px}.ncard .h b{display:flex;align-items:center;gap:8px;font-size:16px}.ncard .h b i{width:12px;height:12px;border-radius:6px}'+
'.ncard .lb{display:flex;height:8px;border-radius:4px;overflow:hidden}.ncard .ac{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px}.ncard .ac .pri{grid-column:1/-1;height:48px;font-size:16px}'+
'.nopts>summary{color:var(--acc)}'+
'.nskip .chip{display:inline-flex;align-items:center;gap:6px;border-color:var(--bad)}.nskip .chip b{color:var(--bad)}.nsr li{display:flex;align-items:center;gap:8px}.nsr li .tx{flex:1;min-width:0}.nsr li button{padding:4px 10px;font-size:13px}.nrtc .chip{min-width:56px;text-align:center}'+
'@media(min-width:900px){.nsheet{left:12px;top:12px;bottom:12px;right:auto;width:420px;height:auto!important;max-height:none;border-radius:16px;border:1px solid var(--line)}.ngrab{display:none}.nbar{left:446px;max-width:560px}#nwrap .leaflet-top{top:12px}}'+
'body.nmin .nsheet{height:58px!important}body.nmin .nbar,body.nmin .nsc{visibility:hidden}body.nmin .nbar{display:none}.nsheet.min .nsc{visibility:hidden}#nwrap .leaflet-bottom{display:none}.nattr{font-size:11px;color:var(--mut);margin-top:18px}'+
'.nseg{margin:4px 0 10px}.card.sgc{padding:0}.card.sgc>details>summary{padding:15px 16px;font-weight:600;font-size:15px;list-style:none;display:flex;justify-content:space-between;align-items:center;cursor:pointer;color:var(--ink);margin:0}.card.sgc>details>summary::-webkit-details-marker{display:none}.card.sgc>details>summary::after{content:"›";color:var(--mut);font-size:22px;line-height:1;transition:transform .15s}.card.sgc>details[open]>summary::after{transform:rotate(90deg)}.card.sgc .sgb{padding:0 16px 14px}';
document.head.append(css);
const msg=(e,t,c)=>{e.className='nmsg'+(c?' '+c:'');e.textContent=t||''};
const km=m=>(m/1000).toFixed(m<10000?1:0)+' km';
const when=t=>t?new Date(t*1000).toLocaleString('pl-PL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'–';
const ago=t=>{if(!t)return 'nigdy';const s=Math.max(0,Date.now()/1000-t);if(s<90)return 'przed chwilą';if(s<3600)return Math.round(s/60)+' min temu';if(s<86400)return Math.round(s/3600)+' h temu';return Math.round(s/86400)+' dni temu'};
async function J(url,o){const r=await (o?api(url,o):fetch(url));let j=null;try{j=await r.json()}catch(e){}if(!r.ok)throw new Error((j&&j.error)||('błąd '+r.status));return j}
const post=(url,body)=>J(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});

/* ---- zakładka */
function inject(){
  const tabs=document.querySelector('nav.tabs');const ref=document.getElementById('t-rides');if(!tabs||!ref||document.getElementById('t-nav'))return;
  // 1.5.0: cztery zakładki – Jazdy (lista i statystyki), Trasy, Motocykl (stan), Ustawienia
  for(const id of ['t-stats','t-scan']){const t=document.getElementById(id);if(t)t.style.display='none'}
  const ts=document.getElementById('t-state');if(ts)ts.innerHTML='<svg viewBox="0 0 24 24"><circle cx="5.5" cy="16.5" r="3.5"/><circle cx="18.5" cy="16.5" r="3.5"/><path d="M5.5 16.5l4-7h5l4 7M9.5 9.5l-1-3h-2M14.5 9.5l2-3h2"/></svg>Motocykl';
  const b=el('button');b.id='t-nav';b.hidden=true;b.onclick=()=>tab('nav');
  b.innerHTML='<svg viewBox="0 0 24 24"><path d="M12 2l7 19-7-4-7 4z"/></svg>Trasy';ref.after(b);
  const sec=el('section');sec.id='v-nav';sec.hidden=true;document.getElementById('v-stats').after(sec);
  // przełącznik Lista | Statystyki nad listą jazd i nad statystykami
  const seg=()=>{const d=el('div','seg nseg');const l=el('button',null,'Lista'),st=el('button',null,'Statystyki');l.onclick=()=>tab('rides');st.onclick=()=>tab('stats');d.append(l,st);return d};
  const sr=seg(),ss=seg();document.getElementById('v-rides').prepend(sr);document.getElementById('v-stats').before(ss);ss.id='seg-stats';
  const det=document.getElementById('detail');new MutationObserver(()=>{sr.style.display=det.hidden?'':'none'}).observe(det,{attributes:true,attributeFilter:['hidden']});
  const segOn=v=>{sr.children[0].classList.toggle('on',v==='rides');sr.children[1].classList.toggle('on',v==='stats');ss.children[0].classList.toggle('on',v==='rides');ss.children[1].classList.toggle('on',v==='stats');ss.style.display=v==='stats'?'':'none'};segOn('rides');
  const t0=window.tab;window.tab=function(v){document.body.classList.toggle('ntab',v==='nav');document.body.classList.remove('nmin');NV.full=false;
    if(v==='nav'){if(STOP)STOP();for(const k of['rides','stats','scan','state','set','nav']){const s=document.getElementById('v-'+k),t=document.getElementById('t-'+k);if(s)s.hidden=k!==v;if(t)t.classList.toggle('on',k===v)}ss.style.display='none';scrollTo(0,0);navGuard();navView();return}
    const s=document.getElementById('v-nav'),t=document.getElementById('t-nav');if(s)s.hidden=true;if(t)t.classList.remove('on');if(NV.map){try{NV.map.remove()}catch(e){}NV.map=null}
    const r=t0(v);segOn(v);if(v==='stats')document.getElementById('t-rides').classList.add('on');return r};
  const d0=window.detail;window.detail=async function(r){await d0(r);try{await planCard(r)}catch(e){}};
  // Ustawienia nawigacji w zakładce Ustawienia, „Ekran i mapa” w zakładce Motocykl
  const sv0=window.setView;window.setView=async function(){await sv0();if(!isHA())return;const V=document.getElementById('v-set');
    try{if(!NV.data)NV.data=await J('api/nav/routes');settingsCard(V)}catch(e){}groupCards(V)};
  const st0=window.stateView;window.stateView=async function(){await st0();if(!isHA())return;const V=document.getElementById('v-state');
    const moto=[...V.querySelectorAll(':scope>.card')].find(c=>c.firstChild&&/^Motocykl/i.test(c.firstChild.textContent||''));if(moto)V.prepend(moto);
    try{NV.data=await J('api/nav/routes');statusCard(V)}catch(e){}};
}
// Karty ustawień jako zwijana lista (tytuł → treść), jak w telefonie.
function groupCards(V){for(const c of [...V.querySelectorAll(':scope>.card')]){if(c.classList.contains('sgc'))continue;const t=c.firstElementChild;if(!t||t.tagName!=='B')continue;
    const d=el('details');const sm=el('summary',null,t.textContent);d.append(sm);const body=el('div','sgb');while(t.nextSibling)body.append(t.nextSibling);t.remove();d.append(body);c.append(d);c.classList.add('sgc')}}
async function probe(){for(let i=0;i<40&&!DATA;i++)await new Promise(r=>setTimeout(r,250));if(!isHA())return;try{const r=await fetch('api/nav/routes');if(!r.ok)return;NV.data=await r.json()}catch(e){return}document.getElementById('t-nav').hidden=false;NV.ready=true}

/* ---- widok: mapa na cały ekran, nad nią wyszukiwarka, pod spodem wysuwany panel */
const SH={min:58,mid:.46,max:.88};
async function navView(){const V=document.getElementById('v-nav');V.textContent='';V.append(el('p','mut','wczytywanie...'));
  try{NV.data=await J('api/nav/routes')}catch(e){V.textContent='';V.append(el('p','bad-msg','Nie udało się wczytać nawigacji: '+e.message));return}
  V.textContent='';const W=el('div');W.id='nwrap';V.append(W);const mapDiv=el('div');mapDiv.id='navmap';W.append(mapDiv);
  P.bar=el('div','nbar');W.append(P.bar);
  P.sheet=el('div','nsheet');const g=el('div','ngrab');g.append(el('i'));P.sheet.append(g);P.sc=el('div','nsc');P.sheet.append(P.sc);W.append(P.sheet);sheetDrag(g);
  plannerCard(P.sc);const rs=el('div','nsec');P.sc.append(rs);RC=null;routesCard(rs);const ts=el('div','nsec');ts.id='ntripsec';P.sc.append(ts);tripCard(ts);P.sc.append(el('div','nattr','Mapa: © OpenStreetMap, OpenMapTiles, OpenFreeMap · Leaflet, MapLibre'));
  const S=NV.data.settings;if(!NV.pts.length){const st=NV.data.screen,fresh=st&&st.t&&Date.now()/1000-st.t<3*3600;if(fresh)setPts([{lat:st.lat,lon:st.lon,name:'pozycja motocykla'}]);else if(S.home)setPts([{lat:S.home.lat,lon:S.home.lon,name:S.home.name||'Dom'}])}
  sheet(NV.sheetH||'mid');await initMap();renderSkip();drawFav()}
// wysokość panelu: 'min' | 'mid' | 'max' albo piksele
function sheet(h){if(!P.sheet)return;NV.sheetH=h;const H=document.getElementById('nwrap').clientHeight||600;const px=typeof h==='number'?h:h==='min'?SH.min:Math.round(H*SH[h]);P.sheet.style.setProperty('--sh',px+'px');P.sheet.classList.toggle('min',h==='min');document.body.classList.remove('nmin')}
function sheetPx(){return P.sheet?P.sheet.getBoundingClientRect().height:0}
function sheetDrag(g){let y0=null,h0=0,moved=false;
  g.addEventListener('pointerdown',e=>{y0=e.clientY;h0=sheetPx();moved=false;P.sheet.classList.add('drag');g.setPointerCapture(e.pointerId)});
  g.addEventListener('pointermove',e=>{if(y0===null)return;const d=y0-e.clientY;if(Math.abs(d)>4)moved=true;const H=document.getElementById('nwrap').clientHeight;P.sheet.style.setProperty('--sh',Math.max(SH.min,Math.min(H-72,h0+d))+'px')});
  const up=()=>{if(y0===null)return;y0=null;P.sheet.classList.remove('drag');const H=document.getElementById('nwrap').clientHeight,h=sheetPx();
    if(!moved){sheet(NV.sheetH==='mid'?'max':NV.sheetH==='max'?'min':'mid');return}
    const c=[['min',SH.min],['mid',H*SH.mid],['max',H*SH.max]].sort((a,b)=>Math.abs(a[1]-h)-Math.abs(b[1]-h))[0][0];sheet(c)};
  g.addEventListener('pointerup',up);g.addEventListener('pointercancel',up)}

function statusCard(V){const d=NV.data,k=el('div','card');k.append(el('b',null,'Ekran i mapa'));
  const add=(lv,t,n)=>{const r=el('div','row');const a=el('span');const dot=el('span','dot'+(lv?' '+lv:''));a.append(dot,' ',t);r.append(a,el('small',null,n||''));k.append(r)};
  const s=d.screen;if(s&&s.t){const fresh=Date.now()/1000-s.t<600;add(fresh?'ok':'',"Ekran: "+(fresh?'połączony':'ostatnio '+ago(s.t)),(s.fw?'wersja '+s.fw+' · ':'')+(s.battery!==undefined?'bateria '+s.battery+'% · ':'')+(s.map?'mapa '+s.map:''))}else add('','Ekran: jeszcze się nie zgłosił','klucz jak w skrzynce (zakładka Ustawienia)');
  const m=d.map;if(m.available)add('ok','Mapa na kartę: '+m.files+' plików, '+m.mb+' MB','zbudowana '+(m.built||'?')+(m.sync&&m.sync.t?' · sprawdzono '+ago(m.sync.t):''));else add('warn','Mapa na kartę: brak',m.source_url?'pobierz z kontenera (przycisk niżej)':'podaj adres kontenera: Ustawienia → Ustawienia nawigacji');
  add(d.engine?'ok':'warn','Silnik tras: '+(d.engine?'skonfigurowany':'brak adresu'),d.engine?d.settings.engine_url:'bez niego działa tylko GPX i trasy proste');
  const b=d.build;if(b&&b.pracuje)add('warn','Kontener: przebudowa '+(b.krok||'?')+'/'+(b.z||5)+(b.proc!==undefined?' · '+b.proc+'%':''),(b.etap||'')+' · od '+ago(b.od));
  else if(b&&b.ok===false&&Date.now()/1000-b.t<7*86400)add('bad','Kontener: ostatnia przebudowa nieudana',b.etap||'');
  else if(b&&b.ok&&b.t)add('ok','Kontener: mapy aktualne','przebudowa skończona '+ago(b.t));
  add(d.settings.tomtom_key?'ok':'','Korki: '+(d.settings.tomtom_key?'włączone (TomTom)':'wyłączone'),d.settings.tomtom_key?'':'klucz TomTom: Ustawienia → Ustawienia nawigacji');
  const a=el('div','acts');const sb=el('button',null,'Pobierz mapę z kontenera');const sm=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;msg(sm,'sprawdzanie i pobieranie... (może potrwać kilka minut)');try{const j=await post('api/nav/map/sync',{});msg(sm,j.ok?(j.changed?'pobrano '+j.files+' plików, mapa z '+j.built:'mapa aktualna ('+j.built+')'):j.error,j.ok?'ok':'bad')}catch(e){msg(sm,e.message,'bad')}sb.disabled=false};a.append(sb,sm);k.append(a);
  if(m.available){const z=d.zip||{};const a2=el('div','acts');const zm=el('span','nmsg');
    if(z.ready){const l=el('button',null,'Pobierz paczkę ZIP na kartę ('+z.mb+' MB)');l.onclick=()=>{const x=document.createElement('a');x.href='api/nav/mapa.zip';x.download='mapa-ekranu.zip';document.body.append(x);x.click();x.remove()};a2.append(l)}
    else{const zb=el('button',null,z.working?'Paczka ZIP się przygotowuje…':'Przygotuj paczkę ZIP na kartę');zb.disabled=!!z.working;zb.onclick=async()=>{zb.disabled=true;try{await fetch('api/nav/mapa.zip')}catch(e){}msg(zm,'przygotowuję paczkę, to potrwa kilka minut; wróć tu później','ok')};a2.append(zb)}
    a2.append(zm);k.append(a2);k.append(el('small','mut','Pierwsze wgranie: rozpakuj ZIP na kartę ekranu (powstanie folder „mapa”). Dalej ekran dociąga w domu tylko zmienione kwadraty.'))}
  V.append(k)}

/* ---- planer */
let P={};
function plannerCard(V){const k=el('div','card');V.append(k);
  const hd=el('div','nhead');hd.append(el('b',null,'Nowa trasa'));P.hint=el('small',null,'');hd.append(P.hint);k.append(hd);
  P.veh=el('div','chips nveh');for(const [v,t] of [['moto','🏍 Motocykl'],['auto','🚗 Samochód']]){const c=el('span','chip',t);c._v=v;c.onclick=()=>setVehicle(v);P.veh.append(c)}k.append(P.veh);P.drv=el('div','nrt ndrv');P.drv.hidden=true;k.append(P.drv);
  // wyszukiwarka nad mapą
  const sr=el('div','nsr');const row=el('div','nrow');P.q=el('input');P.q.placeholder='Dodaj punkt: miejsce, adres albo link';const sb=el('button',null,'Dodaj');row.append(P.q,sb);P.res=el('ul');P.res.hidden=true;sr.append(row,P.res);P.bar.append(sr);
  P.q.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search()}};sb.onclick=search;
  P.trip=el('div','ntrip');P.trip.hidden=true;P.trip.append(el('i'),el('span',null,'Motocykl w trasie · co po drodze ›'));P.trip.onclick=()=>{sheet('max');const t=document.getElementById('ntripsec');if(t)t.scrollIntoView({behavior:'smooth'})};P.bar.append(P.trip);
  P.list=el('div');k.append(P.list);
  const quick=el('div','acts');const b1=el('button',null,'Start: motocykl');b1.onclick=()=>{const s=NV.data.screen;if(!(s&&s.t)){toast('Ekran jeszcze nie przysłał pozycji.');return}setStart({lat:s.lat,lon:s.lon,name:'pozycja motocykla'})};
  const b2=el('button',null,'Start: dom');b2.onclick=()=>{const h=NV.data.settings.home;if(!h){toast('Ustaw dom: Ustawienia → Ustawienia nawigacji.');return}setStart({lat:h.lat,lon:h.lon,name:h.name||'Dom'})};
  const b3=el('button',null,'Wyczyść');b3.onclick=()=>{setPts([]);NV.skip=[];NV.rt=null;renderSkip();renderRt();clearPlan()};quick.append(b1,b2,b3);k.append(quick);
  P.favBox=el('div','nfav');k.insertBefore(P.favBox,P.list);renderFav();
  // trasa okrężna jednym dotknięciem: od startu (albo domu) na km albo na czas
  P.rtBox=el('div','nsec');P.rtBox.append(el('small','mut','Trasa okrężna od startu (bez startu: od domu):'));P.rtc=el('div','chips nrtc');P.rtBox.append(P.rtc);k.append(P.rtBox);
  for(const [t,o] of RT_OPTS){const c=el('span','chip',t);c._o=o;c.onclick=()=>pickRt(o);P.rtc.append(c)}
  // pomijane miejscowości
  P.skipBox=el('div','nsec nskip');k.append(P.skipBox);renderSkip();
  const S=NV.data.settings;
  const op=el('details','ngrp nopts');op.append(el('summary',null,'Warianty, omijanie dróg, okrężna na inną długość, GPX'));k.append(op);
  P.var={};P.varC={};const vc=el('div','chips');for(const [v,t] of NV.data.variants){const c=el('span','chip on',t);c.onclick=()=>{c.classList.toggle('on');P.var[v]=c.classList.contains('on')};P.var[v]=true;P.varC[v]=c;vc.append(c)}op.append(el('small',null,'Warianty do porównania:'),vc);
  P.av={};const ac=el('div','chips');for(const v of NV.data.avoid_all){const on=(S.avoid||[]).includes(v);const c=el('span','chip'+(on?' on':''),'omijaj: '+AVN[v]);c.onclick=()=>{c.classList.toggle('on');P.av[v]=c.classList.contains('on')};P.av[v]=on;ac.append(c)}op.append(ac);
  const r2=el('div','nrow');P.rt=el('input');P.rt.type='number';P.rt.placeholder='trasa okrężna: ile km';P.rt.min=10;P.rt.max=1500;P.rt.oninput=()=>{NV.rt=null;renderRt()};P.name=el('input');P.name.placeholder='nazwa trasy (opcjonalnie)';P.name.maxLength=40;r2.append(P.rt,P.name);op.append(r2);
  const mo=el('div','acts');P.poiBtn=el('button',null,'Pokaż na mapie: fotoradary, stacje, widoki');P.poiBtn.onclick=togglePoi;mo.append(P.poiBtn);op.append(mo);P.leg=el('div','nleg');P.leg.hidden=true;for(const [kd,t] of LEG){const sp=el('span');const i=el('i');i.style.background=KIND[kd][1];sp.append(i,t);P.leg.append(sp)}P.legHint=el('small','mut','');P.leg.append(P.legHint);op.append(P.leg);
  const g=el('div','acts');const f=el('input');f.type='file';f.accept='.gpx,application/gpx+xml';f.hidden=true;const gb=el('button',null,'Wczytaj GPX (np. z Kurvigera) i wyślij na ekran');const gm=el('span','nmsg');gb.onclick=()=>f.click();
  f.onchange=async()=>{const file=f.files[0];if(!file)return;gb.disabled=true;msg(gm,'wczytywanie...');try{const body=await file.arrayBuffer();const r=await api('api/nav/gpx?name='+encodeURIComponent(file.name.replace(/\.gpx$/i,'')),{method:'POST',headers:{'Content-Type':'application/gpx+xml'},body});const j=await r.json();if(!r.ok)throw new Error(j.error||'błąd');msg(gm,'trasa „'+j.route.name+'” ('+j.route.km+' km) zapisana i ustawiona na ekran','ok');NV.data=await J('api/nav/routes');routesCard(null);showRoute(j.route)}catch(e){msg(gm,e.message,'bad')}gb.disabled=false;f.value=''};
  g.append(gb,f,gm);op.append(g);
  const a=el('div','acts');P.go=el('button','pri','Policz trasę');P.go.style.flex='1';P.go.style.height='50px';P.go.style.fontSize='16px';P.go.onclick=plan;a.append(P.go);k.append(a);P.msg=el('div','nmsg');k.append(P.msg);
  P.out=el('div');k.append(P.out);
  P.along=el('div');P.along.hidden=true;k.append(P.along);
  renderVehicle(true);renderDrive();renderPts()}
/* tryb pojazdu: w samochodzie liczona tylko najszybsza (inne warianty można włączyć ręcznie),
   ekran bez „wyniku zakrętu”; „jedź do” z iPhone’a i objazdy też najszybciej */
function renderVehicle(vars){const v=NV.data.settings.vehicle||'moto';if(P.veh)for(const c of P.veh.children)c.classList.toggle('on',c._v===v);
  if(vars&&P.varC)for(const k of Object.keys(P.varC)){const on=v==='moto'||k==='szybko';P.varC[k].classList.toggle('on',on);P.var[k]=on}}
async function setVehicle(v){if((NV.data.settings.vehicle||'moto')===v)return;try{const s=await post('api/nav/settings',{vehicle:v});NV.data.settings=s;renderVehicle(true);if(NV.plan)clearPlan();toast(v==='auto'?'Tryb samochód: najszybsza trasa, ekran bez wyniku zakrętu':'Tryb motocykl: wszystkie warianty krętości')}catch(e){alert(e.message)}}

const RT_OPTS=[['50 km',{km:50}],['100 km',{km:100}],['150 km',{km:150}],['200 km',{km:200}],['30 min',{min:30}],['1 h',{min:60}],['1,5 h',{min:90}],['2 h',{min:120}],['3 h',{min:180}]];
function rtLabel(o){return o.km?o.km+' km':(o.min>=60?(o.min/60+'').replace('.',',')+' h':o.min+' min')}
function renderRt(){if(!P.rtc)return;for(const c of P.rtc.children)c.classList.toggle('on',!!NV.rt&&c._o===NV.rt)}
function pickRt(o){if(NV.rt===o){NV.rt=null;renderRt();return}NV.rt=o;if(P.rt)P.rt.value='';renderRt();
  if(!NV.pts.length){const h=NV.data.settings.home;const s=NV.data.screen;
    if(h)setPts([{lat:h.lat,lon:h.lon,name:h.name||'Dom'}]);else if(s&&s.t)setPts([{lat:s.lat,lon:s.lon,name:'pozycja motocykla'}]);
    else{toast('Ustaw dom (Ustawienia → Ustawienia nawigacji) albo dodaj start.');NV.rt=null;renderRt();return}}
  else if(NV.pts.length>1)toast('Trasa okrężna liczy się tylko od startu; pozostałe punkty pominę.');
  plan()}
function skipRadius(r){if(r.r)return r.r;const e=r.extent;if(e&&e.length===4){const dy=(e[1]-e[3])*110540/2,dx=(e[2]-e[0])*111320*Math.cos(r.lat*Math.PI/180)/2;return Math.round(Math.min(6000,Math.max(500,Math.hypot(dx,dy)*0.9)))}
  return {city:3500,town:1800,village:800,hamlet:400,suburb:1200}[r.type]||700}
function addSkip(r){const sp={lat:r.lat,lon:r.lon,name:(r.name||'').slice(0,40),r:skipRadius(r)};NV.skip.push(sp);renderSkip();if(NV.map)NV.map.panTo([sp.lat,sp.lon]);if(NV.plan)toast('Pomijam „'+(sp.name||'miejsce')+'”. Policz trasę jeszcze raz.')}
function renderSkip(){if(!P.skipBox)return;P.skipBox.textContent='';const row=el('div','chips');
  for(const sp of NV.skip){const c=el('span','chip');c.append(el('b',null,'✕'),'omiń: '+(sp.name||'miejsce'));c.title='usuń z pomijanych';c.onclick=()=>{NV.skip=NV.skip.filter(x=>x!==sp);renderSkip()};row.append(c)}
  const add=el('span','chip','+ pomiń miejscowość');add.onclick=()=>{toast('Wpisz u góry nazwę i dotknij „Pomiń”, albo dotknij miejsca na mapie.');NV.mode='skip';if(NV.map)NV.map.getContainer().classList.add('add');sheet('min')};row.append(add);P.skipBox.append(row);
  if(NV.map){if(NV.skipL)NV.skipL.remove();NV.skipL=L.layerGroup().addTo(NV.map);for(const sp of NV.skip)L.circle([sp.lat,sp.lon],{radius:sp.r,color:'#e03131',weight:2,dashArray:'6 6',fillOpacity:.08}).bindTooltip('omijam: '+(sp.name||'miejsce')).addTo(NV.skipL)}}
function setPts(p){NV.pts=p;const n=Math.max(0,p.length-1);NV.legs=NV.legs.slice(0,n);while(NV.legs.length<n)NV.legs.push('');renderPts();drawMarkers()}
function setStart(p){const rest=NV.pts.slice(1);setPts([p].concat(rest))}
function addPt(p){setPts(NV.pts.concat([p]))}
function renderPts(){if(!P.list)return;P.list.textContent='';drawLegs();if(P.hint)P.hint.textContent=NV.pts.length>1?'dotknij odcinka, żeby wybrać krętość':'';if(!NV.pts.length){P.list.append(el('p','mut','Dodaj start i cel: wyszukaj u góry, wklej link albo dotknij mapy.'));return}
  NV.pts.forEach((p,i)=>{if(i>0)P.list.append(legRow(i-1));const r=el('div','npt');const last=i===NV.pts.length-1&&i>0;r.append(el('span','dt'+(i===0?' s':last?' c':'')));const nm=el('span','nm',p.name||(p.lat.toFixed(5)+', '+p.lon.toFixed(5)));nm.title=(i===0?'start':last?'cel':'punkt '+i)+' · '+p.lat.toFixed(5)+', '+p.lon.toFixed(5);r.append(nm);
    const up=el('button',null,'↑');up.title='wyżej';up.disabled=i===0;up.onclick=()=>{const a=NV.pts.slice();[a[i-1],a[i]]=[a[i],a[i-1]];setPts(a)};const dn=el('button',null,'↓');dn.title='niżej';dn.disabled=i===NV.pts.length-1;dn.onclick=()=>{const a=NV.pts.slice();[a[i+1],a[i]]=[a[i],a[i+1]];setPts(a)};const x=el('button',null,'✕');x.title='usuń punkt';x.onclick=()=>{const a=NV.pts.slice();a.splice(i,1);setPts(a)};const st=el('button',null,isFav(p)?'★':'☆');st.title='zapisz w ulubionych';st.onclick=()=>saveFav(p);r.append(st,up,dn,x);P.list.append(r)})}
// odcinek między punktami: przycisk z wybraną krętością (pusty = jak cała trasa)
const LDESC={szybko:'główne drogi, najkrócej w czasie',lekko:'boczne drogi, niewiele dłużej',kreto:'szuka zakrętów, wyraźnie dłużej',bardzo:'przełęcze i serpentyny, czas mniej ważny'};
function legRow(k){const r=el('div','nleg2');const v=NV.legs[k];const bar=el('span','bar');if(v)bar.style.background=VCOL[v];r.append(bar);
  const b=el('button','lpill');const i=el('i');i.style.background=v?VCOL[v]:'var(--mut)';b.append(i,(v?VN(v):'jak cała trasa')+' ▾');if(v){b.style.borderColor=VCOL[v]}b.onclick=()=>pickLeg(k);r.append(b);return r}
function legName(k){const N=NV.pts.length;const n=i=>(NV.pts[i]&&NV.pts[i].name)||(i===0?'start':i===N-1?'cel':'punkt '+i);return n(k)+' → '+n(k+1)}
function pickLeg(k){const o=el('div','npick');const d=el('div');o.append(d);const close=()=>o.remove();o.onclick=e=>{if(e.target===o)close()};
  d.append(el('h3',null,'Jak jechać ten odcinek?'),el('small','mut',legName(k)+'. Reszta trasy zostaje bez zmian.'));
  for(const [v,t] of NV.data.variants){const b=el('button','opt'+(NV.legs[k]===v?' on':''));const i=el('i');i.style.background=VCOL[v];const sp=el('span');sp.append(el('b',null,t),el('small',null,LDESC[v]||''));b.append(i,sp);if(NV.legs[k]===v)b.style.borderColor=VCOL[v];b.onclick=()=>{NV.legs[k]=v;close();renderPts()};d.append(b)}
  const r2=el('div','row2');const all=el('button',null,'Jak cała trasa');all.onclick=()=>{NV.legs[k]='';close();renderPts()};const sl=el('button',null,'Dostosuj suwaki');sl.onclick=()=>{close();tab('set');setTimeout(()=>{const c=[...document.querySelectorAll('#v-set details')].find(x=>/Krętość/.test(x.firstChild&&x.firstChild.textContent||''));if(c){let p=c;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement}c.scrollIntoView({block:'start'})}},700)};r2.append(all,sl);d.append(r2);document.body.append(o)}
// odcinki na mapie przed liczeniem: kreska w kolorze wybranej krętości, dotknięcie = wybór
function drawLegs(){if(!NV.map)return;if(NV.legL)NV.legL.remove();NV.legL=L.layerGroup().addTo(NV.map);if(NV.lines.length)return;
  for(let k=0;k<NV.pts.length-1;k++){const a=NV.pts[k],b=NV.pts[k+1],v=NV.legs[k];const ll=[[a.lat,a.lon],[b.lat,b.lon]];
    L.polyline(ll,{color:'#000',weight:14,opacity:0}).on('click',e=>{L.DomEvent.stop(e);pickLeg(k)}).addTo(NV.legL);
    L.polyline(ll,{color:v?VCOL[v]:'#8b98ae',weight:v?4:3,opacity:.9,dashArray:'6 8',interactive:false}).addTo(NV.legL)}}
const isLink=t=>/https?:\/\//i.test(t)||/^geo:/i.test(t)||/^-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+$/.test(t.trim());
async function search(){let q=P.q.value.trim();if(!q)return;const sk=/^(pomi[nń]|omi[nń])\s+/i.test(q);if(sk)q=q.replace(/^\S+\s+/,'');P.res.hidden=true;P.res.textContent='';P.q.disabled=true;
  try{if(isLink(q)){const j=await J('api/nav/resolve?text='+encodeURIComponent(q));addPt({lat:j.place.lat,lon:j.place.lon,name:j.place.name||q.slice(0,40)});P.q.value='';fitAll()}
    else{const c=NV.pts.length?NV.pts[0]:(NV.map?{lat:NV.map.getCenter().lat,lon:NV.map.getCenter().lng}:{});const j=await J('api/nav/search?q='+encodeURIComponent(q)+(c.lat?'&lat='+c.lat+'&lon='+c.lon:''));
      const fm=favMatch(q);for(const f of fm){const li=el('li');const tx=el('span','tx');tx.append('★ '+f.name,el('small','mut','ulubione'));li.append(tx);li.onclick=()=>{if(sk)addSkip(f);else{addPt({lat:f.lat,lon:f.lon,name:f.name});fitAll()}P.res.hidden=true;P.q.value=''};P.res.append(li)}
      if(!j.results.length&&!fm.length){P.res.append(el('li','mut','nic nie znaleziono'));P.res.hidden=false}else{for(const r of j.results){const li=el('li');const tx=el('span','tx');tx.append(r.name,el('small','mut',r.label));const sb=el('button',null,'Pomiń');sb.title='nie jedź przez to miejsce';
          sb.onclick=e=>{e.stopPropagation();addSkip(r);P.res.hidden=true;P.q.value=''};const fb=el('button',null,'☆');fb.title='zapisz w ulubionych';fb.onclick=e=>{e.stopPropagation();saveFav({lat:r.lat,lon:r.lon,name:r.name});P.res.hidden=true;P.q.value=''};li.append(tx,fb,sb);li.onclick=()=>{if(sk){addSkip(r)}else{addPt({lat:r.lat,lon:r.lon,name:r.name});fitAll()}P.res.hidden=true;P.q.value=''};P.res.append(li)}P.res.hidden=false}}}
  catch(e){P.res.append(el('li','bad-msg',e.message));P.res.hidden=false}P.q.disabled=false}

/* ---- mapa */
async function initMap(){const div=document.getElementById('navmap');if(!div)return;const ok=await loadLeaflet();if(!ok){div.replaceWith(el('p','mut','Mapa wymaga internetu (OpenStreetMap).'));return}
  try{NV.map=L.map(div,{zoomControl:!(L.Browser.touch&&(navigator.maxTouchPoints||0)>0)});baseLayer(NV.map);
    if(window.ResizeObserver)new ResizeObserver(()=>{if(!NV.map)return;NV.map.invalidateSize(false);if(NV.pendingFit)safeFit(NV.pendingFit)}).observe(div);
    const S=NV.data.settings,c=NV.pts[0]||S.home||{lat:52.1,lon:19.4};NV.map.setView([c.lat,c.lon],NV.pts.length?10:6);div.classList.add('add');
    lockControl();
    NV.map.on('click',async e=>{if(NV.mode==='skip'){NV.mode='add';NV.map.getContainer().classList.remove('add');const r={lat:e.latlng.lat,lon:e.latlng.lng,name:'zaznaczone miejsce'};addSkip(r);
      try{const j=await J('api/nav/search?q='+encodeURIComponent(r.lat.toFixed(4)+' '+r.lon.toFixed(4)));const f=j.results&&j.results[0];const sp=NV.skip[NV.skip.length-1];if(f&&sp&&sp.lat===r.lat){sp.name=(f.name||f.label||'').slice(0,40);if(['city','town','village'].includes(f.type)||f.extent)sp.r=skipRadius(Object.assign({},f,{lat:sp.lat}));renderSkip()}}catch(x){}return}
    if(NV.mode==='home'){await setHome({lat:e.latlng.lat,lon:e.latlng.lng,name:'Dom'});NV.mode='add';return}if(NV.locked){if(P.msg)msg(P.msg,'Mapa zablokowana: dotknij 🔒 w rogu mapy, żeby dodawać i przesuwać punkty.');return}addPt({lat:e.latlng.lat,lon:e.latlng.lng,name:''});nameLater(NV.pts.length-1)});
    NV.map.on('moveend',()=>{if(NV.poiOn)loadPoi()});drawMarkers();if(NV.data.current){const r=NV.data.routes.find(x=>x.id===NV.data.current);if(r&&!NV.pts.length)try{showRoute(await J('api/nav/route?id='+r.id))}catch(e){}}}catch(e){div.replaceWith(el('p','mut','Nie udało się uruchomić mapy.'))}}
async function nameLater(i){try{const p=NV.pts[i];const j=await J('api/nav/search?q='+encodeURIComponent(p.lat.toFixed(4)+' '+p.lon.toFixed(4)));if(j.results&&j.results[0]&&NV.pts[i]===p){p.name=j.results[0].label||j.results[0].name;renderPts()}}catch(e){}}
function drawMarkers(){if(!NV.map)return;drawLegs();for(const m of NV.mk)m.remove();NV.mk=[];NV.pts.forEach((p,i)=>{const last=i===NV.pts.length-1;const m=L.marker([p.lat,p.lon],{draggable:!NV.locked,title:p.name||''}).addTo(NV.map);m.bindTooltip(i===0?'start':last?'cel':String(i),{permanent:true,direction:'top',offset:[-15,-10],className:'lab'});
  m.on('dragend',()=>{const ll=m.getLatLng();NV.pts[i]={lat:ll.lat,lon:ll.lng,name:''};renderPts();nameLater(i)});NV.mk.push(m)})}
// Blokada mapy po policzeniu trasy: na telefonie jeden palec przewija stronę
// (mapa tylko powiększana dwoma palcami), kliknięcie nie dodaje punktów,
// punktów nie da się przeciągnąć. Kłódka odblokowuje, ⤢ wraca do całej trasy.
function lockMap(on){NV.locked=!!on;const m=NV.map;if(!m)return;
  m.dragging.enable();m.scrollWheelZoom.enable();m.doubleClickZoom.enable();
  m.touchZoom.enable();const c=m.getContainer();c.classList.toggle('locked',NV.locked);
  for(const mk of NV.mk){if(mk.dragging){if(NV.locked)mk.dragging.disable();else mk.dragging.enable()}}
  if(NV.lockBtn){NV.lockBtn.textContent=NV.locked?'🔒':'🔓';NV.lockBtn.title=NV.locked?'Mapa zablokowana – dotknij, by edytować punkty':'Mapa do edycji – dotknij, by zablokować'}}
function lockControl(){const C=L.Control.extend({options:{position:'topright'},onAdd(){const d=L.DomUtil.create('div','nlock');L.DomEvent.disableClickPropagation(d);
    const b=L.DomUtil.create('button','',d);b.type='button';b.onclick=()=>lockMap(!NV.locked);NV.lockBtn=b;
    const f=L.DomUtil.create('button','',d);f.type='button';f.textContent='⤢';f.title='Pokaż całą trasę';f.onclick=()=>{if(NV.fit)safeFit(NV.fit);else fitAll()};
    const fs=L.DomUtil.create('button','',d);fs.type='button';fs.textContent='⛶';fs.title='Pełny ekran mapy';fs.onclick=()=>fullMap(!NV.full);NV.fullBtn=fs;return d}});
  new C().addTo(NV.map);lockMap(NV.locked)}
// Pełny ekran mapy: mapa na cały ekran, przesuwanie jednym palcem, strona
// pod spodem stoi (aplikacja HA nie łapie gestów przewijania ani „wstecz”).
function fullMap(on){const m=NV.map;if(!m)return;on=!!on;if(on===!!NV.full)return;NV.full=on;
  if(on){NV.lockBefore=NV.locked;document.body.classList.add('nmin');lockMap(false)}else{document.body.classList.remove('nmin');lockMap(NV.lockBefore)}
  if(NV.fullBtn){NV.fullBtn.textContent=on?'✕':'⛶';NV.fullBtn.title=on?'Pokaż panel':'Sama mapa (schowaj panel)'}
  setTimeout(()=>m.invalidateSize(),260)}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&NV.full)fullMap(false)});
function toast(t){const d=el('div','ntoast',t);document.body.append(d);setTimeout(()=>d.remove(),2600)}
// Gest „wstecz” (przesunięcie od krawędzi w aplikacji HA) w Nawigacji nie wychodzi
// z dodatku: zamyka pełny ekran albo zostaje na miejscu.
let GUARD=false;
function navGuard(){if(GUARD)return;GUARD=true;try{history.pushState({nt1100:'nav'},'')}catch(e){return}
  addEventListener('popstate',()=>{const v=document.getElementById('v-nav');if(!v||v.hidden)return;
    if(NV.full)fullMap(false);else toast('Zostajesz w Nawigacji – do Home Assistanta wrócisz menu z boku.');
    try{history.pushState({nt1100:'nav'},'')}catch(e){}})}
function fitPad(){const wide=innerWidth>=900;return wide?{paddingTopLeft:[450,30],paddingBottomRight:[30,30]}:{paddingTopLeft:[24,70],paddingBottomRight:[24,Math.min(sheetPx(),(document.getElementById('nwrap')||{}).clientHeight*.5||300)+16]}}
/* Dopasowanie widoku odporne na mapę, która ma jeszcze zerowy rozmiar (strona otwarta w tle,
   klawiatura iPhone'a, przełączanie zakładek): Leaflet liczyłby wtedy zoom NaN („Invalid LatLng”). */
function safeFit(b){const m=NV.map;if(!m||!b||!b.isValid())return;m.invalidateSize(false);const s=m.getSize();
  if(s.x<60||s.y<60){NV.pendingFit=b;return}NV.pendingFit=null;let p=fitPad();
  const fits=pp=>s.x-pp.paddingTopLeft[0]-pp.paddingBottomRight[0]>40&&s.y-pp.paddingTopLeft[1]-pp.paddingBottomRight[1]>40;
  if(!fits(p))p={paddingTopLeft:[10,10],paddingBottomRight:[10,10]};try{m.fitBounds(b,p)}catch(e){try{m.fitBounds(b)}catch(x){}}}
function fitRoute(b){NV.fit=b;safeFit(b);lockMap(true)}
function fitAll(){if(!NV.map||!NV.pts.length)return;if(NV.pts.length===1){NV.map.setView([NV.pts[0].lat,NV.pts[0].lon],11);return}safeFit(L.latLngBounds(NV.pts.map(p=>[p.lat,p.lon])))}
function clearPlan(){for(const l of NV.lines)l.remove();NV.lines=[];setTimeout(drawLegs,0);NV.plan=null;NV.sel=null;if(P.out)P.out.textContent='';if(P.along){P.along.hidden=true;P.along.textContent=''}if(NV.alongL){NV.alongL.remove();NV.alongL=null}}
function showRoute(r){clearPlan();if(!NV.map||!r.pts)return;const ll=r.pts.map(p=>[p[0],p[1]]);const l=L.polyline(ll,{color:VCOL[r.variant]||'#3d8bfd',weight:5,opacity:.85}).addTo(NV.map);NV.lines.push(l);fitRoute(l.getBounds());if(r.id)alongFor('id='+r.id,r.name||'trasa',ll);
  if(r.waypoints)for(const w of r.waypoints){if(!w.name||w.name==='cel'||w.name==='start')continue}NV.shown=r.id}
async function togglePoi(){NV.poiOn=!NV.poiOn;P.leg.hidden=!NV.poiOn;P.poiBtn.textContent=NV.poiOn?'Ukryj POI':'Pokaż POI z mapy (fotoradary, stacje, widoki)';if(NV.poiOn)await loadPoi();else if(NV.poi){NV.poi.remove();NV.poi=null}}
async function loadPoi(){if(!NV.map)return;const b=NV.map.getBounds();if(NV.map.getZoom()<9){if(NV.poi)NV.poi.clearLayers();P.legHint.textContent='przybliż mapę, żeby zobaczyć punkty';return}P.legHint.textContent='';
  try{const j=await J('api/nav/poi?bbox='+[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].map(x=>x.toFixed(4)).join(','));if(j.too_big)P.legHint.textContent='przybliż mapę, żeby zobaczyć punkty';else if(j.points.length>=400)P.legHint.textContent='pokazano część punktów – przybliż, żeby zobaczyć wszystkie';if(!NV.poi)NV.poi=L.layerGroup().addTo(NV.map);NV.poi.clearLayers();
    for(const p of j.points){const k=KIND[p.kind]||['punkt','#888'];const m=L.circleMarker([p.lat,p.lon],{radius:6,color:'#fff',weight:1.5,fillColor:k[1],fillOpacity:.95}).bindPopup(popupHtml(p,k)+'<br><a href="#" data-add="1">dodaj jako punkt trasy</a>');
      m.on('popupopen',e=>{const a=e.popup.getElement().querySelector('[data-add]');if(a)a.onclick=ev=>{ev.preventDefault();addPt({lat:p.lat,lon:p.lon,name:p.name||k[0]});m.closePopup()}});NV.poi.addLayer(m)}}catch(e){}}

/* ---- POI: wspólne */
const esc=t=>String(t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function popupHtml(p,k){k=k||KIND[p.kind]||['punkt','#888'];return '<b>'+esc(p.name||k[0])+'</b>'+(p.name?'<br>'+esc(k[0]):'')+(p.limit?' · '+p.limit+' km/h':'')}
const kmTxt=x=>(x<10?x.toFixed(1):Math.round(x))+' km';
function nearIdx(ll,lat,lon){let b=1e18,bi=0;for(let i=0;i<ll.length;i++){const a=ll[i],dy=a[0]-lat,dx=(a[1]-lon)*0.64,d=dy*dy+dx*dx;if(d<b){b=d;bi=i}}return bi}
function insertWaypoint(p,ll){if(NV.pts.length<2){addPt(p);return}const a=NV.pts.slice();const last=a.pop();const k=nearIdx(ll,p.lat,p.lon);let at=a.length;for(let i=1;i<a.length;i++){if(nearIdx(ll,a[i].lat,a[i].lon)>k){at=i;break}}a.splice(at,0,p);a.push(last);setPts(a)}
function poiMarker(layer,p,extra){const k=KIND[p.kind]||['punkt','#888'];const m=L.circleMarker([p.lat,p.lon],{radius:8,color:'#fff',weight:2,fillColor:k[1],fillOpacity:1}).bindPopup(popupHtml(p,k)+(extra?'<br>'+extra:''));layer.addLayer(m);return m}
// lista POI: wiersze z nazwą, odległością i przyciskami
function poiRows(box,points,opt){box.textContent='';if(!points.length){box.append(el('p','mut',opt.empty));return}
  for(const p of points){const k=KIND[p.kind]||['punkt','#888'];const r=el('div','npo');const dot=el('i');dot.style.background=k[1];const tx=el('div','tx');tx.append(el('span',null,p.name||k[0]));
    tx.append(el('small',null,(p.name?k[0]+' · ':'')+opt.dist(p)+(p.off_m!==null&&p.off_m!==undefined?' · '+(p.off_m<1000?p.off_m+' m':(p.off_m/1000).toFixed(1)+' km')+' od trasy':'')));
    const sh=el('button',null,'Pokaż');sh.onclick=()=>{if(!NV.map)return;sheet('mid');NV.map.setView([p.lat,p.lon],15);if(p._m)p._m.openPopup()};
    r.append(dot,tx,sh);for(const b of opt.buttons(p))r.append(b);box.append(r)}}

/* ---- po drodze: POI wzdłuż wybranej trasy */
async function alongFor(q,label,ll){if(!P.along)return;NV.alongQ=q;NV.alongLL=ll;NV.alongLabel=label;if(NV.alongCat===undefined)NV.alongCat=0;P.along.hidden=false;renderAlong()}
async function renderAlong(){const A=P.along;A.textContent='';A.append(el('h2',null,'Po drodze: '+NV.alongLabel));
  const ch=el('div','chips');CATS.forEach((c,i)=>{const b=el('span','chip'+(i===NV.alongCat?' on':''),c[0]);b.onclick=()=>{NV.alongCat=i;renderAlong()};ch.append(b)});A.append(ch);
  const box=el('div','nlist');box.append(el('p','mut','szukanie...'));A.append(box);
  try{const j=await J('api/nav/along?'+NV.alongQ+'&kinds='+CATS[NV.alongCat][1]+'&max=2000');if(NV.alongL)NV.alongL.remove();NV.alongL=L.layerGroup().addTo(NV.map);
    for(const p of j.points)p._m=poiMarker(NV.alongL,p,'km '+p.km+' trasy');
    poiRows(box,j.points,{empty:j.no_map?'Brak mapy w dodatku – kliknij „Pobierz mapę z kontenera” na górze.':'Nic w tej kategorii do 2 km od trasy.',dist:p=>'km '+p.km+' trasy',
      buttons:p=>{const b=el('button',null,'Dodaj');b.title='dodaj jako punkt po drodze (potem policz trasy jeszcze raz)';b.onclick=()=>{insertWaypoint({lat:p.lat,lon:p.lon,name:p.name||(KIND[p.kind]||['punkt'])[0]},NV.alongLL||[]);msg(P.msg,'dodano „'+(p.name||'punkt')+'” jako punkt po drodze – kliknij „Policz trasy”','ok')};return [b]}})}
  catch(e){box.textContent='';box.append(el('p','nmsg bad',e.message))}}

/* ---- w trasie: decyzje na miejscu (pozycja motocykla, co jest przed nami) */
let T={};
function tripCard(V){const k=el('div','card');k.append(el('b',null,'W trasie'));k.append(el('p','mut','Co jest przed motocyklem: stacje, jedzenie, nocleg. „Jedź tam” wysyła miejsce na ekran jako postój, a potem prowadzi dalej po trasie.'));
  T.pos=el('div','ndev');k.append(T.pos);
  const ch=el('div','chips');if(T.cat===undefined)T.cat=0;CATS.forEach((c,i)=>{const b=el('span','chip'+(i===T.cat?' on':''),c[0]);b.onclick=()=>{T.cat=i;ch.querySelectorAll('.chip').forEach((x,n)=>x.classList.toggle('on',n===i));tripLoad()};ch.append(b)});k.append(ch);
  const a=el('div','acts');const rf=el('button',null,'Odśwież');rf.onclick=()=>tripLoad();T.phoneB=el('button',null,'Użyj pozycji telefonu');T.phoneB.onclick=phonePos;T.msg=el('span','nmsg');a.append(rf,T.phoneB,T.msg);k.append(a);
  T.box=el('div','nlist');k.append(T.box);V.append(k);tripLoad()}
function phonePos(){if(!navigator.geolocation){msg(T.msg,'ta przeglądarka nie podaje pozycji','bad');return}msg(T.msg,'ustalanie pozycji...');
  navigator.geolocation.getCurrentPosition(p=>{T.phone={lat:p.coords.latitude,lon:p.coords.longitude};msg(T.msg,'');tripLoad()},e=>msg(T.msg,'brak zgody na pozycję albo brak sygnału','bad'),{enableHighAccuracy:true,timeout:15000,maximumAge:60000})}
async function tripLoad(){if(!T.box)return;T.box.textContent='';T.box.append(el('p','mut','szukanie...'));
  const q='kinds='+CATS[T.cat][1]+(T.phone?'&lat='+T.phone.lat+'&lon='+T.phone.lon:'');
  try{const j=await J('api/nav/nearby?'+q);T.last=j;if(P.trip)P.trip.hidden=!(j.pos&&j.pos.src==='ekran'&&j.pos.age_s<1800);
    if(!j.pos){T.pos.textContent='Nie znam pozycji motocykla: ekran nie łączył się od 30 min. Włącz hotspot w telefonie albo użyj pozycji telefonu.';T.box.textContent='';return}
    T.pos.textContent=(j.pos.src==='ekran'?'Pozycja z ekranu ('+(j.pos.age_s<90?'przed chwilą':Math.round(j.pos.age_s/60)+' min temu')+')':'Pozycja z telefonu')+' · '+(j.mode==='trasa'?'jedziesz po bieżącej trasie: miejsca przed Tobą, do 3 km od trasy':'bez trasy (albo poza nią): najbliższe wokół, do 15 km');
    if(NV.map){if(NV.tripL)NV.tripL.remove();NV.tripL=L.layerGroup().addTo(NV.map);L.circleMarker([j.pos.lat,j.pos.lon],{radius:9,color:'#fff',weight:3,fillColor:'#212529',fillOpacity:1}).bindTooltip('motocykl').addTo(NV.tripL);for(const p of j.points)p._m=poiMarker(NV.tripL,p)}
    poiRows(T.box,j.points,{empty:j.no_map?'Brak mapy w dodatku – kliknij „Pobierz mapę z kontenera”.':'Nic w tej kategorii w pobliżu.',dist:p=>j.mode==='trasa'?kmTxt(p.dist_km)+' przed Tobą':kmTxt(p.dist_km)+' stąd',
      buttons:p=>{const b=el('button','pri','Jedź tam');b.onclick=()=>goVia(p,b);return [b]}})}
  catch(e){T.box.textContent='';T.box.append(el('p','nmsg bad',e.message))}}
async function goVia(p,b){const nm=p.name||(KIND[p.kind]||['postój'])[0];if(!confirm('Wysłać „'+nm+'” na ekran jako postój? Ekran poprowadzi tam, a potem dalej po trasie.'))return;b.disabled=true;msg(T.msg,'liczenie...');
  try{const j=await post('api/nav/via',{lat:p.lat,lon:p.lon,name:nm,from:T.phone||null});msg(T.msg,'„'+nm+'” na ekranie: '+j.route.km+' km, '+dur(j.route.min)+'. Ekran pobierze trasę przy najbliższym połączeniu (hotspot).','ok');NV.data=await J('api/nav/routes');routesCard(null);try{showRoute(await J('api/nav/route?id='+j.route.id))}catch(e){}}
  catch(e){msg(T.msg,e.message,'bad')}b.disabled=false}

/* ---- liczenie i wysyłka */
async function plan(){const vars=Object.keys(P.var).filter(v=>P.var[v]);const rt=P.rt.value?+P.rt.value:(NV.rt&&NV.rt.km)||null;const rtm=!P.rt.value&&NV.rt&&NV.rt.min||null;
  if(!NV.pts.length){msg(P.msg,'dodaj przynajmniej start i cel','bad');return}if(NV.pts.length<2&&!rt&&!rtm){msg(P.msg,'dodaj cel albo podaj długość trasy okrężnej','bad');return}if(!vars.length){msg(P.msg,'zaznacz choć jeden wariant','bad');return}
  if(!NV.data.engine){msg(P.msg,'brak adresu silnika tras – wpisz go w Ustawienia → Ustawienia nawigacji (albo wczytaj GPX)','bad');return}
  const dv=NV.data.settings.go_variant||NV.data.settings.default_variant;let legs=null;
  if(!rt&&!rtm&&NV.pts.length>=2&&NV.legs.some(x=>x)){legs=NV.legs.map(x=>x||dv);if(new Set(legs).size<2){if(!vars.includes(legs[0]))vars.push(legs[0]);legs=null}}
  P.go.disabled=true;msg(P.msg,'liczenie '+(vars.length+(legs?1:0))+' wariantów...');clearPlan();
  try{const j=await post('api/nav/plan',{points:NV.pts,variants:vars,legs,avoid:Object.keys(P.av).filter(v=>P.av[v]),name:P.name.value,round_trip_km:rt,round_trip_min:rtm,skip:NV.skip,weather:true});NV.plan=j;msg(P.msg,j.routes.length?'':'żaden wariant się nie policzył',j.routes.length?'':'bad');results(j)}catch(e){msg(P.msg,e.message,'bad')}P.go.disabled=false}
function results(j){P.out.textContent='';for(const v of Object.keys(j.errors||{}))P.out.append(el('p','nmsg bad',VN(v)+': '+j.errors[v]));
  const order=j.routes.map((r,i)=>i).sort((a,b)=>(j.routes[b].variant==='mix')-(j.routes[a].variant==='mix'));
  if(j.routes.length)P.out.append(el('small','mut','Dotknij wariantu, żeby go wybrać. Pogrubiona linia na mapie = wybrany.'));
  const bnds=[];const cards=[];
  j.routes.forEach((r,i)=>{const ll=r.pts.map(p=>[p[0],p[1]]);const l=L.polyline(ll,{color:VCOL[r.variant]||'#888',weight:4,opacity:.75}).addTo(NV.map);l.on('click',()=>pick(i));NV.lines.push(l);bnds.push(...ll)});
  const pick=i=>{const r=j.routes[i];NV.sel=i;cards.forEach(c=>{const on=c._i===i;c.classList.toggle('on',on);c.style.borderColor=on?(VCOL[j.routes[c._i].variant]||''):'';c.querySelector('.ac').hidden=!on});NV.lines.forEach((x,k)=>x.setStyle({opacity:k===i?1:.35,weight:k===i?7:3}));NV.lines[i].bringToFront();alongFor('token='+j.token+'&variant='+r.variant,VN(r.variant),r.pts.map(p=>[p[0],p[1]]))};
  for(const i of order){const r=j.routes[i];const d=el('div','ncard');d._i=i;const vn=VN(r.variant);
    const h=el('div','h');const t=el('b');const sw=el('i');sw.style.background=VCOL[r.variant]||'#888';t.append(sw,vn);h.append(t,el('span',null,r.km+' km · '+dur(r.min)));d.append(h);
    if(r.legs&&r.legs.length){const bar=el('div','lb');const lm=r.leg_m&&r.leg_m.length===r.legs.length?r.leg_m:r.legs.map(()=>1);r.legs.forEach((v,k)=>{const s=el('span');s.style.flex=String(Math.max(1,lm[k]));s.style.background=VCOL[v]||'#888';bar.append(s)});d.append(bar);
      const per={};r.legs.forEach((v,k)=>{per[v]=(per[v]||0)+(r.leg_m?r.leg_m[k]:0)});d.append(el('small','mut',Object.keys(per).map(v=>(SHORT[v]||v)+(r.leg_m?' '+km(per[v]):'')).join(' · ')))}
    const rain=r.weather&&r.weather.length?Math.max(...r.weather.map(w=>w.rain_prob||0)):null;const temps=r.weather&&r.weather.length?r.weather.map(w=>w.temp).filter(x=>x!==null&&x!==undefined):[];
    d.append(el('small','mut',[r.curvy?r.curvy.level+' ('+r.curvy.deg_km+'°/km)':'','fotoradary: '+(r.cameras||[]).length,rain!==null?'deszcz do '+rain+'%':'',temps.length?Math.min(...temps).toFixed(0)+'–'+Math.max(...temps).toFixed(0)+'°C':''].filter(x=>x).join(' · ')));
    const ac=el('div','ac');ac.hidden=true;
    const b=el('button','pri','Wyślij „'+vn+'” na ekran');b.onclick=async ev=>{ev.stopPropagation();b.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:true});msg(P.msg,'trasa „'+s.route.name+'” zapisana; ekran pobierze ją przy najbliższym połączeniu','ok');NV.data=await J('api/nav/routes');routesCard(null)}catch(e){msg(P.msg,e.message,'bad');b.disabled=false}};
    const sv=el('button',null,'Zapisz');sv.title='zapisz bez wysyłania na ekran';sv.onclick=async ev=>{ev.stopPropagation();sv.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});NV.data=await J('api/nav/routes');routesCard(null);msg(P.msg,'trasa „'+s.route.name+'” zapisana w „Moich trasach”','ok')}catch(e){msg(P.msg,e.message,'bad');sv.disabled=false}};
    const g=el('button',null,'GPX');g.title='zapisz i udostępnij plik GPX';g.onclick=async ev=>{ev.stopPropagation();g.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});NV.data=await J('api/nav/routes');routesCard(null);await shareGpx(s.id,s.route.name);msg(P.msg,'trasa „'+s.route.name+'” zapisana (bez wysyłania na ekran)','ok')}catch(e){msg(P.msg,e.message,'bad')}g.disabled=false};
    const dr=el('button','pri','🚗 Jadę (OsmAnd)');dr.title='zapisz, otwórz w OsmAnd i pilnuj korków po drodze';dr.onclick=async ev=>{ev.stopPropagation();dr.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});await startDrive(s.id,s.route.name)}catch(e){msg(P.msg,e.message,'bad')}dr.disabled=false};
    if(NV.data.settings.vehicle==='auto')ac.append(dr,sv,g);else ac.append(b,sv,g);d.append(ac);d.onclick=()=>pick(i);cards.push(d);P.out.append(d)}
  if(bnds.length)fitRoute(L.latLngBounds(bnds));if(order.length){pick(order[0]);sheet('mid');setTimeout(()=>P.out.scrollIntoView({behavior:'smooth',block:'start'}),250)}}

/* ---- GPX: arkusz udostępniania na telefonie (Wiadomości, WhatsApp, Pliki), na komputerze pobranie */
async function shareGpx(id,name,osm){const r=await fetch('api/nav/gpx?id='+id);if(!r.ok)throw new Error('nie udało się pobrać GPX');const blob=await r.blob();
  const PL={ą:'a',ć:'c',ę:'e',ł:'l',ń:'n',ó:'o',ś:'s',ź:'z',ż:'z',Ą:'A',Ć:'C',Ę:'E',Ł:'L',Ń:'N',Ó:'O',Ś:'S',Ź:'Z',Ż:'Z'};
  const fn=((name||'trasa').replace(/[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]/g,c=>PL[c]).replace(/[^\w.\-]+/g,'_').replace(/^_+|_+$/g,'').slice(0,40)||'trasa')+'.gpx';
  const file=new File([blob],fn,{type:'application/gpx+xml'});
  if(navigator.canShare&&navigator.canShare({files:[file]})){try{await navigator.share({files:[file],title:name||'Trasa'});return}catch(e){if(e&&e.name==='AbortError')return}}
  const u=URL.createObjectURL(file);const a=document.createElement('a');a.href=u;a.download=fn;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),5000)}

/* ---- zapisane trasy */
let RC=null;
function routesCard(V){if(!RC){RC=el('div','card');V.append(RC)}RC.textContent='';RC.append(el('b',null,'Zapisane trasy'));const d=NV.data;
  const dm=el('div','acts');dm.style.margin='4px 0 8px';const db=el('button',null,'Dodaj trasę demo (Bieruń – Pszczyna, 22 km)');db.title='Przykładowa trasa z rondami, fotoradarem, odcinkowym pomiarem i postojem. Możesz ją puścić w „Symulacji” albo wysłać na ekran.';
  db.onclick=async()=>{db.disabled=true;try{const j=await post('api/nav/demo',{});NV.data=await J('api/nav/routes');routesCard(null);const r=NV.data.routes.find(x=>x.id===j.id);if(r)simulate(r)}catch(e){alert(e.message)}db.disabled=false};dm.append(db);RC.append(dm);
  if(!d.routes.length){RC.append(el('p','mut','Jeszcze nic nie zaplanowano.'));return}
  for(const r of d.routes){const row=el('div','nrt');const tx=el('div','tx');const t=el('span',null,r.name||('trasa '+r.id));tx.append(t);if(r.id===d.current)tx.append(' ',el('span','cur','na ekranie'));
    tx.append(el('small','mut',r.km+' km · '+dur(r.min)+(r.variant?' · '+VN(r.variant).toLowerCase():'')+(r.source?' · '+r.source:'')+' · '+when(r.created)));
    const a=el('div','acts');a.style.margin='0';const sh=el('button',null,'Pokaż');sh.onclick=async()=>{try{const full=await J('api/nav/route?id='+r.id);sheet('mid');showRoute(full)}catch(e){alert(e.message)}};
    const cu=el('button',null,r.id===d.current?'Zdejmij z ekranu':'Na ekran');cu.onclick=async()=>{try{await post('api/nav/current',{id:r.id===d.current?0:r.id});NV.data=await J('api/nav/routes');routesCard(null)}catch(e){alert(e.message)}};
    const gx=el('button',null,'GPX');gx.title='pobierz albo udostępnij plik GPX';gx.onclick=()=>shareGpx(r.id,r.name).catch(e=>alert(e.message));
    const rm=el('button','warn','Usuń');rm.onclick=async()=>{if(!confirm('Usunąć trasę „'+(r.name||r.id)+'”?'))return;try{await post('api/nav/delete',{id:r.id});NV.data=await J('api/nav/routes');routesCard(null)}catch(e){alert(e.message)}};
    const sm=el('button',null,'Symulacja');sm.title='Przejazd trasy na niby: mapa i podgląd ekranu z kierownicy';sm.onclick=()=>simulate(r);
    const jd=el('button',null,'🚗 Jadę');jd.title='otwórz w OsmAnd i pilnuj korków po drodze';jd.onclick=()=>startDrive(r.id,r.name).catch(e=>alert(e.message));
    if(NV.data.settings.vehicle==='auto')a.append(sh,jd,gx,rm);else a.append(sh,sm,cu,gx,rm);row.append(tx,a);RC.append(row)}}
/* ---- jazda autem z OsmAnd: dodatek pilnuje korków i wysyła powiadomienie z objazdem */
async function startDrive(id,name){const j=await post('api/nav/drive',{id});NV.data.drive=j.drive;renderDrive();
  if(!j.phone)toast('Ustaw telefon w Ustawienia nawigacji → Jazda autem, żeby dodatek znał pozycję.');
  await shareGpx(id,name);msg(P.msg,'„'+name+'” w OsmAnd; pilnuję korków co '+NV.data.settings.traffic_min+' min i dam znać powiadomieniem','ok')}
function renderDrive(){if(!P.drv)return;const d=NV.data.drive;P.drv.hidden=!d;P.drv.textContent='';if(!d)return;
  const tx=el('div','tx');tx.append(el('b',null,'🚗 Pilnuję korków: '+d.name),el('small','mut',d.status||''));
  const a=el('div','acts');a.style.margin='0';const g=el('button',null,'GPX');g.onclick=()=>{const id=d.rids[d.rids.length-1];shareGpx(id,d.name).catch(e=>alert(e.message))};
  const x=el('button','warn','Zakończ');x.onclick=async()=>{try{await post('api/nav/drive',{stop:true});NV.data.drive=null;renderDrive()}catch(e){alert(e.message)}};a.append(g,x);P.drv.append(tx,a)}
setInterval(async()=>{if(!P.drv||!NV.data||!NV.data.drive||document.hidden)return;try{const j=await J('api/nav/drive');NV.data.drive=j.drive;renderDrive()}catch(e){}},60000);

/* ---- symulacja przejazdu (to samo co „Demo trasy” na ekranie, w przeglądarce) */
const SIM={};
const ARW={0:'↑',1:'↗',2:'←',3:'↙',4:'↗',5:'→',6:'↘',7:'↶',8:'⟳',9:'↖',10:'↗',11:'•',12:'⚑',13:'⛴'};
const ARWL={1:'↖',4:'↗'};
const TTX={0:'prosto',1:'lekko w lewo',2:'w lewo',3:'ostro w lewo',4:'lekko w prawo',5:'w prawo',6:'ostro w prawo',7:'zawróć',8:'rondo',9:'trzymaj się lewej',10:'trzymaj się prawej',11:'punkt trasy',12:'cel',13:'prom'};
function arrow(t){return ARWL[t]||ARW[t]||'↑'}
function brg(a,b){const y=Math.sin((b[1]-a[1])*Math.PI/180)*Math.cos(b[0]*Math.PI/180),x=Math.cos(a[0]*Math.PI/180)*Math.sin(b[0]*Math.PI/180)-Math.sin(a[0]*Math.PI/180)*Math.cos(b[0]*Math.PI/180)*Math.cos((b[1]-a[1])*Math.PI/180);return (Math.atan2(y,x)*180/Math.PI+360)%360}
function adiff(a,b){return ((b-a+540)%360)-180}
function fdist(m){m=Math.max(0,m);return m<950?(Math.round(m/10)*10)+' m':m<9950?(m/1000).toFixed(1).replace('.',',')+' km':Math.round(m/1000)+' km'}
function simStop(){if(SIM.timer)clearInterval(SIM.timer);SIM.timer=null;if(SIM.map){SIM.map.remove();SIM.map=null}if(SIM.card){SIM.card.remove();SIM.card=null}}
async function simulate(r0){simStop();let r;try{r=await J('api/nav/route?id='+r0.id+'&full=1')}catch(e){alert(e.message);return}
  if(!r.pts||r.pts.length<2||!r.cum){alert('ta trasa nie ma punktów');return}
  const k=el('div','card');SIM.card=k;const anchor=RC||document.getElementById('v-nav');anchor.after(k);sheet('max');
  const hd=el('div','nrow');hd.append(el('b',null,'Symulacja: '+(r.name||'trasa')));k.append(hd);
  k.append(el('p','mut','Przejazd na niby, bez skrzynki: „motocykl” trzyma limity, zwalnia przed zakrętami, staje na pierwszym punkcie po drodze. Po prawej to, co pokazałby ekran na kierownicy (uproszczone). Na prawdziwym ekranie to samo robi „Demo trasy”.'));
  const wrap=el('div');wrap.style.cssText='display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start';
  const md=el('div');md.style.cssText='flex:1 1 320px;height:300px;border-radius:10px;background:var(--card2)';
  const cv=document.createElement('canvas');cv.width=320;cv.height=240;cv.style.cssText='flex:0 0 auto;width:320px;max-width:100%;border-radius:10px;border:6px solid #222;background:#000';
  wrap.append(md,cv);k.append(wrap);
  const ctl=el('div','chips');const speeds=[1,4,10];const btn={};for(const x of speeds){const b=el('span','chip'+(x===4?' on':''),'×'+x);b.onclick=()=>{SIM.k=x;for(const y of speeds)btn[y].className='chip'+(y===x?' on':'')};btn[x]=b;ctl.append(b)}
  const pa=el('span','chip','pauza');pa.onclick=()=>{SIM.pause=!SIM.pause;pa.className='chip'+(SIM.pause?' on':'')};const rs=el('span','chip','od początku');rs.onclick=()=>{S.s=0;S.v=0;S.stopUntil=0;S.stopDone=false;S.arrived=false;S.t=0};const en=el('span','chip','zamknij');en.onclick=simStop;
  ctl.append(pa,rs,en);k.append(ctl);
  const pts=r.pts,cum=r.cum,n=pts.length,LEN=cum[n-1];
  // prędkość dopuszczalna w punktach: limit, zakręty (~4,2 m/s² w bok), hamowanie
  const cap=new Array(n).fill(80/3.6),cur=new Array(n).fill(0),hdg=new Array(n);
  let li=0,lim=0;const lims=r.limits||[];for(let i=0;i<n;i++){while(li<lims.length&&lims[li].idx<=i)lim=lims[li++].kmh;if(lim)cap[i]=lim/3.6}
  for(let i=0;i<n;i++){let a=i,b=i;while(a>0&&cum[i]-cum[a]<12)a--;while(b<n-1&&cum[b]-cum[i]<12)b++;hdg[i]=a===b?0:brg(pts[a],pts[b])}
  for(let i=1;i<n-1;i++){let a=i,b=i;while(a>0&&cum[i]-cum[a]<15)a--;while(b<n-1&&cum[b]-cum[i]<15)b++;const ds=cum[b]-cum[a];if(ds<5)continue;const kk=adiff(hdg[a],hdg[b])*Math.PI/180/ds;cur[i]=kk;if(Math.abs(kk)>1e-4)cap[i]=Math.min(cap[i],Math.max(3,Math.sqrt(4.2/Math.abs(kk))))}
  const wps=r.waypoints||[];const via=wps.find(w=>w.kind===1&&w.idx>0&&w.idx<n-1);const stopAt=via?cum[via.idx]:-1;if(via)cap[via.idx]=0;cap[n-1]=0;
  for(let i=n-2;i>=0;i--){const v=Math.sqrt(cap[i+1]*cap[i+1]+2*2.2*(cum[i+1]-cum[i]));if(v<cap[i])cap[i]=v}
  const S={s:0,v:0,lean:0,stopUntil:0,stopDone:false,arrived:false,t:0,leanMax:0,inCorner:false,calm:0,leanShow:0,leanRes:0};SIM.k=4;SIM.pause=false;
  const idxAt=s=>{let lo=0,hi=n-1;while(lo<hi){const m=(lo+hi+1)>>1;if(cum[m]<=s)lo=m;else hi=m-1}return lo};
  const at=(arr,s)=>{const i=idxAt(s);if(i>=n-1)return arr[n-1];const t=(s-cum[i])/Math.max(1,cum[i+1]-cum[i]);return arr[i]+(arr[i+1]-arr[i])*t};
  const posAt=s=>{s=Math.max(0,Math.min(LEN,s));const i=idxAt(s);if(i>=n-1)return pts[n-1];const t=(s-cum[i])/Math.max(1,cum[i+1]-cum[i]);return [pts[i][0]+(pts[i+1][0]-pts[i][0])*t,pts[i][1]+(pts[i+1][1]-pts[i][1])*t]};
  if(!(await loadLeaflet())){md.replaceWith(el('p','mut','Mapa wymaga internetu (OpenStreetMap).'))}
  else{SIM.map=L.map(md,{zoomControl:true});baseLayer(SIM.map);L.polyline(pts,{color:'#3d8bfd',weight:5,opacity:.8}).addTo(SIM.map);
    for(const c of r.cameras||[])if(c.type!==3)L.circleMarker(pts[c.idx],{radius:7,color:'#fff',weight:2,fillColor:'#e03131',fillOpacity:1}).bindTooltip(c.type===2?'odcinkowy '+c.limit:'fotoradar '+c.limit).addTo(SIM.map);
    SIM.mk=L.circleMarker(pts[0],{radius:9,color:'#fff',weight:3,fillColor:'#f76707',fillOpacity:1}).addTo(SIM.map);SIM.map.setView(pts[0],15)}
  const cams=r.cameras||[],turns=(r.turns||[]).filter(t=>t.type!==0&&t.type!==11);
  let secEnd=-1,secStartT=0,secStartS=0,secLim=0,last=performance.now(),lastPan=0;
  const ctx=cv.getContext('2d');
  function step(dt){if(S.arrived)return;if(S.stopUntil){if(S.t>=S.stopUntil){S.stopUntil=0;S.stopDone=true;S.s+=1}return}
    for(let left=dt;left>1e-6;){const h=Math.min(0.1,left);left-=h;
      if(stopAt>=0&&!S.stopDone&&S.s<stopAt&&stopAt-S.s<4){S.s=stopAt;S.v=0;S.stopUntil=S.t+40;break}
      if(LEN-S.s<3){S.s=LEN;S.v=0;S.arrived=true;break}
      const vt=Math.max(1.5,at(cap,S.s)+(S.stopDone&&Math.abs(S.s-stopAt)<5?3:0));S.v=S.v<vt?Math.min(vt,S.v+1.8*h):Math.max(vt,S.v-3.3*h);S.s+=S.v*h;if(stopAt>=0&&!S.stopDone&&S.s>stopAt)S.s=stopAt}
    const tgt=Math.atan(S.v*S.v*at(cur,S.s)/9.81)*180/Math.PI;S.lean+=(tgt-S.lean)*Math.min(1,dt/0.6)}
  function view(){const s=S.s,i=idxAt(s),kmh=S.v*3.6,o={};
    o.limit=0;for(const l of lims){if(l.idx<=i)o.limit=l.kmh;else break}
    o.turn=null;o.turn2=null;for(const t of turns){if(t.idx<=i&&t.type!==12)continue;const d=cum[t.idx]-s;if(!o.turn)o.turn=Object.assign({d},t);else{o.turn2=Object.assign({d},t);break}}
    o.cam=null;if(secEnd>=0){if(i>=secEnd)secEnd=-1;else o.cam={sec:true,limit:secLim,left:cum[secEnd]-s,avg:S.t-secStartT>2?(s-secStartS)/(S.t-secStartT)*3.6:kmh}}
    if(!o.cam)for(const c of cams){if(c.idx<=i){if(c.type===2&&c.idx+1>=i&&secEnd<0){secEnd=(cams.find(e=>e.type===3&&e.idx>c.idx)||{idx:n-1}).idx;secStartT=S.t;secStartS=s;secLim=c.limit}continue}if(c.type===3)continue;const d=cum[c.idx]-s;if(d<=1000)o.cam={sec:false,type:c.type,limit:c.limit,d};break}
    const a=Math.abs(S.lean);if(a>=10&&kmh>15){if(!S.inCorner){S.inCorner=true;S.leanMax=0}if(a>Math.abs(S.leanMax))S.leanMax=S.lean;S.calm=0}else if(S.inCorner&&a<8){if(!S.calm)S.calm=S.t;if(S.t-S.calm>=1.5){S.inCorner=false;if(Math.abs(S.leanMax)>=20){S.leanRes=S.leanMax;S.leanShow=S.t+4}}}
    o.wp=null;let no=0;for(const w of wps){no++;if(w.idx>i+1||(w.kind===2&&w.idx>=i)){o.wp={no,d:cum[w.idx]-s,name:w.name};break}}
    o.v=S.arrived?'cel':o.cam?'cam':(o.turn&&(o.turn.d<=500||(kmh>5&&o.turn.d/(kmh/3.6)<=30)))?'turn':S.t<S.leanShow?'lean':'map';
    return o}
  function draw(o){const W=320,H=240,kmh=Math.round(S.v*3.6);ctx.fillStyle='#101418';ctx.fillRect(0,0,W,H);
    ctx.fillStyle='#1f2a36';ctx.fillRect(0,0,W,26);ctx.fillStyle='#fff';ctx.font='bold 16px sans-serif';ctx.textBaseline='middle';ctx.textAlign='left';
    const d=new Date();ctx.fillText(String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'),6,13);ctx.textAlign='right';ctx.fillText(kmh+' km/h',120,13);
    ctx.font='13px sans-serif';const prog=o.wp&&o.wp.no<wps.length?'P'+o.wp.no+' '+fdist(o.wp.d)+' · cel '+fdist(LEN-S.s):'cel '+fdist(LEN-S.s);ctx.fillText(prog,W-6,13);
    const my=26,mh=178;ctx.textAlign='center';
    if(o.v==='turn'){const t=o.turn;ctx.fillStyle='#fff';ctx.font='bold 110px sans-serif';ctx.textAlign='left';ctx.fillText(arrow(t.type),14,my+mh/2);ctx.textAlign='right';ctx.font='bold 44px sans-serif';ctx.fillText(fdist(t.d),W-12,my+60);ctx.font='17px sans-serif';ctx.fillText((t.type===8&&t.exit?t.exit+'. zjazd · ':'')+(t.text||TTX[t.type]||''),W-12,my+108);if(o.turn2&&o.turn2.d-t.d<700){ctx.fillStyle='#9aa7b4';ctx.font='15px sans-serif';ctx.fillText('potem '+arrow(o.turn2.type)+' za '+fdist(o.turn2.d-t.d),W-12,my+140)}}
    else if(o.v==='cam'){const c=o.cam;ctx.fillStyle='#e03131';ctx.fillRect(0,my,W,mh);ctx.fillStyle='#fff';ctx.font='bold 20px sans-serif';ctx.fillText(c.sec?'ODCINKOWY POMIAR':(c.type===2?'ODCINEK ZA':'FOTORADAR'),W/2,my+26);
      ctx.beginPath();ctx.arc(70,my+100,42,0,7);ctx.fillStyle='#fff';ctx.fill();ctx.lineWidth=8;ctx.strokeStyle='#c92a2a';ctx.stroke();ctx.fillStyle='#000';ctx.font='bold 34px sans-serif';ctx.fillText(c.limit||'?',70,my+102);
      ctx.fillStyle='#fff';ctx.textAlign='right';ctx.font='bold 38px sans-serif';if(c.sec){ctx.fillText('śr. '+Math.round(c.avg),W-14,my+88);ctx.font='16px sans-serif';ctx.fillText('do końca '+fdist(c.left),W-14,my+128)}else ctx.fillText(fdist(c.d),W-14,my+100)}
    else if(o.v==='lean'){ctx.fillStyle='#fff';ctx.font='bold 64px sans-serif';ctx.fillText(Math.round(Math.abs(S.leanRes))+'°',W/2,my+75);ctx.fillStyle='#9aa7b4';ctx.font='18px sans-serif';ctx.fillText('zakręt '+(S.leanRes<0?'w lewo':'w prawo'),W/2,my+125)}
    else if(o.v==='cel'){ctx.fillStyle='#fff';ctx.font='bold 26px sans-serif';ctx.fillText('Jesteś na miejscu',W/2,my+80);ctx.fillStyle='#9aa7b4';ctx.font='15px sans-serif';ctx.fillText(r.name||'',W/2,my+115)}
    else{ctx.fillStyle='#9aa7b4';ctx.font='15px sans-serif';ctx.fillText(S.stopUntil?'postój – ekran pokaże strony postoju':'mapa (jak na mapie obok)',W/2,my+80);ctx.fillStyle='#fff';ctx.font='bold 28px sans-serif';ctx.fillText('przechył '+Math.round(Math.abs(S.lean))+'°',W/2,my+120)}
    const y0=H-36;ctx.fillStyle='#1f2a36';ctx.fillRect(0,y0,W,36);
    if(o.limit){ctx.beginPath();ctx.arc(22,y0+18,15,0,7);ctx.fillStyle='#fff';ctx.fill();ctx.lineWidth=4;ctx.strokeStyle='#c92a2a';ctx.stroke();ctx.fillStyle='#000';ctx.font='bold 13px sans-serif';ctx.textAlign='center';ctx.fillText(o.limit,22,y0+19)}
    if(o.turn){ctx.fillStyle='#fff';ctx.textAlign='left';ctx.font='bold 26px sans-serif';ctx.fillText(arrow(o.turn.type),48,y0+18);ctx.font='bold 15px sans-serif';ctx.fillText(fdist(o.turn.d),82,y0+11);ctx.font='12px sans-serif';ctx.fillText((o.turn.text||TTX[o.turn.type]||'').slice(0,26),82,y0+27)}
    if(o.cam){ctx.beginPath();ctx.arc(W-20,y0+18,11,0,7);ctx.fillStyle='#e03131';ctx.fill()}
    ctx.fillStyle='#f59f00';ctx.fillRect(W-110,y0-24,104,20);ctx.fillStyle='#000';ctx.font='bold 12px sans-serif';ctx.textAlign='center';ctx.fillText('SYMULACJA ×'+SIM.k,W-58,y0-14)}
  SIM.timer=setInterval(()=>{if(!SIM.card||!document.body.contains(SIM.card)){simStop();return}const now=performance.now();const dt=Math.min(1,(now-last)/1000);last=now;if(SIM.pause)return;const k=dt*SIM.k;S.t+=k;step(k);const o=view();draw(o);
    if(SIM.mk){const p=posAt(S.s);SIM.mk.setLatLng(p);if(now-lastPan>700){lastPan=now;SIM.map.panTo(p,{animate:true,duration:.6})}}},100);
  k.scrollIntoView({behavior:'smooth',block:'start'})}

/* ---- ustawienia */
/* ---- ulubione miejsca (szkoła, praca...): chipy nad trasą, gwiazdka przy punkcie i wyniku */
const favs=()=>NV.data.settings.fav||[];
function isFav(p){return favs().some(f=>Math.abs(f.lat-p.lat)<1e-4&&Math.abs(f.lon-p.lon)<1e-4)}
function favMatch(q){q=q.toLowerCase();return favs().filter(f=>f.name.toLowerCase().includes(q)).slice(0,5)}
async function putFav(list,ok){try{const j=await post('api/nav/fav',{fav:list});NV.data.settings.fav=j.fav;renderFav();renderPts();drawFav();renderFavSet();if(ok)toast(ok)}catch(e){alert(e.message)}}
function saveFav(p){const i=favs().findIndex(f=>Math.abs(f.lat-p.lat)<1e-4&&Math.abs(f.lon-p.lon)<1e-4);
  if(i>=0){if(confirm('Usunąć „'+favs()[i].name+'” z ulubionych?')){const a=favs().slice();a.splice(i,1);putFav(a,'usunięto z ulubionych')}return}
  const nm=(prompt('Nazwa ulubionego miejsca (np. Praca, Szkoła):',(p.name||'').split(',')[0].slice(0,30))||'').trim();if(!nm)return;
  putFav(favs().concat([{lat:p.lat,lon:p.lon,name:nm.slice(0,30)}]),'„'+nm+'” w ulubionych')}
function goFav(f){const p={lat:f.lat,lon:f.lon,name:f.name};if(NV.rt){NV.rt=null;renderRt()}addPt(p);fitAll();toast('„'+f.name+'” dodane jako '+(NV.pts.length>1?'cel':'start'))}
function renderFav(){if(!P.favBox)return;P.favBox.textContent='';const S=NV.data.settings,row=el('div','chips');
  if(S.home){const c=el('span','chip','⌂ '+(S.home.name||'Dom'));c.onclick=()=>goFav({lat:S.home.lat,lon:S.home.lon,name:S.home.name||'Dom'});row.append(c)}
  for(const f of favs()){const c=el('span','chip','★ '+f.name);c.title='dodaj do trasy';c.onclick=()=>goFav(f);row.append(c)}
  const ad=el('span','chip nadd','+ ulubione');ad.title='zapisz miejsce';ad.onclick=()=>{if(NV.pts.length){saveFav(NV.pts[NV.pts.length-1]);return}toast('Wyszukaj miejsce i dotknij ☆ przy wyniku albo przy punkcie trasy.')};row.append(ad);
  P.favBox.append(row)}
function drawFav(){if(!NV.map)return;if(NV.favL)NV.favL.remove();NV.favL=L.layerGroup().addTo(NV.map);for(const f of favs())L.circleMarker([f.lat,f.lon],{radius:6,color:'#fff',weight:2,fillColor:'#f59f00',fillOpacity:1}).bindTooltip('★ '+f.name).on('click',()=>goFav(f)).addTo(NV.favL)}
function renderFavSet(){if(!SF.fav)return;SF.fav.textContent='';if(!favs().length){SF.fav.append(el('p','mut','Brak. Zapisz miejsce gwiazdką ☆ przy wyniku wyszukiwania albo przy punkcie trasy w zakładce Trasy.'));return}
  favs().forEach((f,i)=>{const r=el('div','npt');r.append(el('span','nm','★ '+f.name+' · '+f.lat.toFixed(4)+', '+f.lon.toFixed(4)));
    const ed=el('button',null,'✎');ed.title='zmień nazwę';ed.onclick=()=>{const nm=(prompt('Nowa nazwa:',f.name)||'').trim();if(!nm||nm===f.name)return;const a=favs().map(x=>Object.assign({},x));a[i].name=nm.slice(0,30);putFav(a)};
    const up=el('button',null,'↑');up.disabled=i===0;up.onclick=()=>{const a=favs().slice();[a[i-1],a[i]]=[a[i],a[i-1]];putFav(a)};
    const x=el('button',null,'✕');x.title='usuń';x.onclick=()=>{if(!confirm('Usunąć „'+f.name+'”?'))return;const a=favs().slice();a.splice(i,1);putFav(a)};r.append(ed,up,x);SF.fav.append(r)})}
async function setHome(h){try{const j=await post('api/nav/home',{home:h});NV.data.settings.home=j.home;if(SF.home)SF.home.textContent=j.home?(j.home.name+' · '+j.home.lat.toFixed(4)+', '+j.home.lon.toFixed(4)):'nie ustawiony';if(NV.map&&j.home){if(NV.homeMk)NV.homeMk.remove();NV.homeMk=L.circleMarker([j.home.lat,j.home.lon],{radius:7,color:'#fff',fillColor:'#7950f2',fillOpacity:1}).bindTooltip('dom').addTo(NV.map)}renderFav()}catch(e){alert(e.message)}}
let SF={};
function settingsCard(V){const S=NV.data.settings;const k0=el('div','card');k0.append(el('b',null,'Ustawienia nawigacji'));V.append(k0);
  const grp=(t,open)=>{const d=el('details','ngrp');if(open)d.open=true;d.append(el('summary',null,t));k0.append(d);return d};
  let k=grp('Połączenie (silnik tras, mapa, korki)',!S.engine_url);
  const eu=field(k,'Silnik tras (kontener Proxmox, np. http://192.168.1.50:8989)','url',null,S.engine_url);
  const mu=field(k,'Mapa na kartę (ten sam kontener, np. http://192.168.1.50:8988)','url',null,S.map_url);
  const tk=field(k,'Klucz TomTom (korki; puste = wyłączone)','password',null,'',S.tomtom_key);
  const kp=grp('Planowanie i dom');const kc=grp('Jazda autem (OsmAnd): korki i objazdy');const ke=grp('Ekran w trasie');k=ke;
  kc.append(el('p','mut','Po „🚗 Jadę (OsmAnd)” dodatek co tyle minut, ile „Sprawdzanie korków”, patrzy na korki przed telefonem (TomTom). Gdy objazd jest szybszy, przychodzi powiadomienie z nową trasą do otwarcia w OsmAnd.'));
  const pt=field(kc,'Telefon (encja z pozycją; puste = z celu powiadomień: '+(NV.data.phone_entity||'brak')+')','text',null,S.phone_tracker);pt.placeholder='device_tracker.iphone';
  const ca=field(kc,'Powiadom od opóźnienia (min)','number',null,S.car_alert_min);
  const dv=field(kp,'Domyślny wariant (skrót „jedź do…” z iPhone’a)','select',NV.data.variants,S.default_variant);
  const ld=field(k,'Wynik zakrętu na ekranie od pochyłu (°)','number',null,S.lean_popup_deg);
  const tm=field(k,'Sprawdzanie korków co (min)','number',null,S.traffic_min);
  const om=field(k,'Zjazd z trasy od (m)','number',null,S.offroute_m);
  const fk=field(k,'„Jadę po swojemu” po (km) poza trasą','number',null,S.free_km);
  const cs=curvySliders(kp,S);
  const hd=el('div','f');hd.append(el('label',null,'Dom (start, gdy ekran nie podał pozycji)'));SF.home=el('div',null,S.home?(S.home.name+' · '+S.home.lat.toFixed(4)+', '+S.home.lon.toFixed(4)):'nie ustawiony');const ha=el('div','acts');const hb=el('button',null,'Wskaż dom na mapie');hb.onclick=()=>{NV.mode='home';tab('nav');setTimeout(()=>{lockMap(false);toast('Dotknij na mapie miejsca domu.')},800)};
  const hs=el('button',null,'Dom = start z listy punktów');hs.onclick=()=>{if(!NV.pts.length){alert('Najpierw dodaj punkt startu w zakładce Trasy.');return}setHome({lat:NV.pts[0].lat,lon:NV.pts[0].lon,name:NV.pts[0].name||'Dom'})};ha.append(hb,hs);hd.append(SF.home,ha);kp.insertBefore(hd,kp.children[2]||null);const fd=el('div','f');fd.append(el('label',null,'Ulubione miejsca (szkoła, praca...): w zakładce Trasy jako przyciski; skrót iPhone’a rozumie też samą nazwę, np. text=Praca'));SF.fav=el('div');fd.append(SF.fav);kp.insertBefore(fd,hd.nextSibling);renderFavSet();k=k0;
  const a=el('div','acts');const sb=el('button','pri','Zapisz ustawienia');const m=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;const body={engine_url:eu.value,map_url:mu.value,default_variant:dv.value,lean_popup_deg:ld.value,traffic_min:tm.value,offroute_m:om.value,free_km:fk.value,phone_tracker:pt.value.trim(),car_alert_min:ca.value,avoid:P.av?Object.keys(P.av).filter(v=>P.av[v]):(NV.data.settings.avoid||[]),curvy:cs.curvy(),curvy_levels:cs.levels()};if(tk.value)body.tomtom_key=tk.value;
    try{const s=await post('api/nav/settings',body);NV.data.settings=s;NV.data.engine=!!s.engine_url;msg(m,'zapisano','ok');tk.value='';tk.placeholder=s.tomtom_key?'•••••• (bez zmian)':''}catch(e){msg(m,e.message,'bad')}sb.disabled=false};a.append(sb,m);k.append(a);
  k.append(el('p','mut','Omijanie zaznaczone w zakładce Trasy („omijaj: …”) zapisuje się razem z ustawieniami jako domyślne. Skrót iPhone’a „Wyślij na motocykl”: adres z zakładki Ustawienia → Połączenie, ścieżka /api/nav/goto?klucz=KLUCZ&text=LINK.'));
  const SH=NV.data.settings.home;if(SH&&NV.map&&!NV.homeMk)NV.homeMk=L.circleMarker([SH.lat,SH.lon],{radius:7,color:'#fff',fillColor:'#7950f2',fillOpacity:1}).bindTooltip('dom').addTo(NV.map)}

// Suwaki krętości wariantów i progi opisu; zwraca odczyt do zapisu.
function curvySliders(k,S){const box=el('details','ngrp');box.append(el('summary',null,'Krętość wariantów (suwaki i opis)'));
  box.append(el('p','mut','Unikaj głównych: jak bardzo omijać autostrady i drogi krajowe. Szukaj zakrętów: jak mocno karać proste drogi. Dłuższa trasa: na ile wolno nadłożyć drogi dla lepszych zakrętów. Działa przy następnym liczeniu.'));
  const D=NV.data.curvy_default||{},C=JSON.parse(JSON.stringify(S.curvy||D)),inputs={};
  const names=[['glowne','Unikaj głównych'],['zakrety','Szukaj zakrętów'],['dluzej','Dłuższa trasa']];
  const g=el('div','nsl');
  for(const [v,t] of NV.data.variants){if(v==='szybko')continue;const h=el('b');const i=el('i');i.style.background=VCOL[v];h.append(i,t);g.append(h);inputs[v]={};
    for(const [key,lab] of names){const r=el('input');r.type='range';r.min=0;r.max=100;r.step=5;r.value=(C[v]||{})[key]??50;const o=el('output',null,String(r.value));r.oninput=()=>{o.textContent=r.value};inputs[v][key]=r;g.append(el('span',null,lab),r,o)}}
  box.append(g);
  const lv=S.curvy_levels||NV.data.curvy_levels_default||[30,80,150];const lw=el('div','nlv');const li=[];
  lw.append('Opis krętości (°/km): prosta do');for(let n=0;n<3;n++){const x=el('input');x.type='number';x.min=1;x.max=1000;x.value=lv[n];li.push(x);lw.append(x);if(n<2)lw.append(n===0?', lekko kręta do':', kręta do')}lw.append(', wyżej bardzo kręta');
  const rs=el('button',null,'Przywróć domyślne');rs.onclick=()=>{for(const v in inputs)for(const key in inputs[v]){inputs[v][key].value=(D[v]||{})[key]??50;inputs[v][key].oninput()}const dl=NV.data.curvy_levels_default||[30,80,150];li.forEach((x,n)=>x.value=dl[n])};
  const a=el('div','acts');a.append(rs);box.append(el('label',null,'Opis krętości tras i jazd'),lw,a);k.append(box);
  return {curvy:()=>{const o={};for(const v in inputs){o[v]={};for(const key in inputs[v])o[v][key]=+inputs[v][key].value}return o},levels:()=>li.map(x=>+x.value)}}

/* ---- zgodność jazdy z planem (w szczegółach jazdy) */
async function planCard(r){if(!isHA())return;const D=document.getElementById('detail');if(!D||D.hidden)return;
  let j;try{j=await J('api/nav/plan?n='+r.n)}catch(e){return}const c=j.plan;if(!c)return;
  const k=el('div','card');k.append(el('b',null,'Trasa planowana'));const pct=c.pct;const lv=pct>=90?'ok':pct>=60?'warn':'bad';const row=el('div','row');const a=el('span');a.append(el('span','dot '+lv),' „'+(c.name||'trasa')+'”: zgodność '+fmt(pct)+'%');row.append(a);k.append(row);
  if(c.deviations&&c.deviations.length){k.append(el('p','ndev','Odstępstwa od planu: '+c.deviations.map(d=>(d.from/1000).toFixed(1)+'–'+(d.to/1000).toFixed(1)+' km').join(', ')))}
  const ev=(c.events||[]).filter(e=>['reroute','skip','detour','offroute','free'].includes(e.what));if(ev.length){const N={reroute:'przeliczenie trasy',skip:'pominięty punkt',detour:'objazd',offroute:'zjazd z trasy',free:'jadę po swojemu'};k.append(el('p','ndev','Zdarzenia na ekranie: '+ev.map(e=>N[e.what]+' '+new Date(e.t*1000).toLocaleTimeString('pl-PL',{hour:'2-digit',minute:'2-digit'})).join(', ')))}
  const md=el('div');md.style.cssText='height:300px;border-radius:10px;background:var(--card2);margin-top:8px';k.append(md);D.append(k);
  if(await loadLeaflet()){try{const map=L.map(md,{zoomControl:false});baseLayer(map);const pl=L.polyline(c.pts.map(p=>[p[0],p[1]]),{color:'#3d8bfd',weight:5,opacity:.6}).addTo(map);
    try{const tr=parse(await text('dl?view=1&f=/rides/'+pad(r.n)+'.trk')).map(p=>[p[0],p[1]]);if(tr.length)L.polyline(tr,{color:'#e8590c',weight:3,opacity:.9}).addTo(map)}catch(e){}map.fitBounds(pl.getBounds(),{padding:[20,20]});
    const lg=el('div','ndev');lg.textContent='niebieska: plan · pomarańczowa: przejechana';k.append(lg)}catch(e){md.remove()}}else md.remove()}

inject();probe();
})();
