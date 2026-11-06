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
css.textContent='#navmap{height:420px;border-radius:10px;background:var(--card2)}#navmap.add{cursor:crosshair}.nmapfail{height:100%;min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:8px;text-align:center;padding:min(22vh,200px) 20px 20px}'+
'.npt{display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}.npt:last-child{border:0}.npt .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.npt .lb{flex:0 0 58px;font-size:12px;color:var(--mut)}.npt button{padding:4px 8px;font-size:13px}'+
'.nsr{position:relative}.nsr ul{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--card);max-height:220px;overflow:auto}.nsr li{padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--line)}.nsr li:hover{background:var(--card2)}.nsr li small{display:block}'+
'.nrt.ndrv{border:1px solid var(--acc);border-radius:10px;padding:10px 12px;margin:0 0 8px}.nrt.ndrv[hidden]{display:none}.nveh{margin:2px 0 8px}.nveh .chip{font-size:14px;padding:6px 14px}.nfav .chip.nadd{border-style:dashed;color:var(--mut)}.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.chip{font-size:13px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--card2);cursor:pointer}.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}'+
'.nres{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:10px;margin:6px 0;cursor:pointer}.nres.on{border-color:var(--acc)}.nres .sw{width:12px;height:12px;border-radius:50%;flex:0 0 12px}.nres .tx{flex:1;min-width:0}.nres small{display:block}'+
'.nrt{display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}.nrt:last-child{border:0}.nrt .tx{flex:1;min-width:0}.nrt small{display:block}.nrt .cur{font-size:11px;padding:2px 7px;border-radius:8px;background:var(--ok);color:#fff}'+
'.nrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.nrow input{flex:1;min-width:160px;padding:9px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card2)}'+
'.fprice{margin-top:2px;color:#1c7ed6;font-weight:600}.npo .fprice{display:block;font-size:12px}.nleg[hidden]{display:none}.nleg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--mut);margin:6px 0}.nleg span{display:inline-flex;align-items:center;gap:5px}.nleg i{width:11px;height:11px;border-radius:50%;display:inline-block;border:1.5px solid #fff}'+
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
'.ntrip[hidden]{display:none}.ntrip{align-self:flex-start;display:flex;align-items:center;gap:8px;border-radius:10px;padding:8px 12px;font-size:13px;font-weight:500;background:color-mix(in srgb,var(--acc2) 22%,var(--card));border:1px solid var(--acc2);color:var(--ink);cursor:pointer}.ntrip i{width:8px;height:8px;border-radius:4px;background:var(--acc2)}'+
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
/* 1.5.26: formularz Start/Cel, wyszukiwarka na cały ekran, pinezki, zakładki panelu */
const css2=document.createElement('style');
css2.textContent=[
'.nstabs{margin:2px 0 12px}.nstabs button{font-size:14px;padding:8px 4px}.npane[hidden]{display:none}',
'.nhead{align-items:center;margin-bottom:8px}.nhead>b{font-size:19px;font-weight:700}',
'.nvseg{display:flex;background:var(--card2);border-radius:999px;padding:3px;gap:2px}.nvseg button{border:0;background:none;border-radius:999px;padding:5px 11px;font-size:13px;color:var(--mut)}.nvseg button.on{background:var(--card);color:var(--ink);font-weight:600;box-shadow:0 1px 3px #0003}',
'.nmode{margin:0 0 10px}.nmode button{font-size:14px}',
'.nform{position:relative;display:flex;flex-direction:column;background:var(--card2);border:1px solid var(--line);border-radius:14px;padding:6px 6px 6px 4px}',
'.nfr{display:flex;align-items:center;gap:6px;min-height:48px}.nfr .nic{flex:0 0 30px;display:flex;justify-content:center;align-items:center;height:30px;font-size:12px;font-weight:700;color:#fff}',
'.nfr.s .nic::before{content:"";width:14px;height:14px;border-radius:50%;border:4px solid #2f9e44;background:var(--card)}',
'.nfr.v .nic{width:20px;height:20px;flex:0 0 20px;margin:0 5px;border-radius:50%;background:#1c6ef2}',
'.nfr.c .nic::before{content:"";width:14px;height:18px;background:#e03131;clip-path:path("M7 18C7 18 0 10.5 0 6.5a7 7 0 0 1 14 0C14 10.5 7 18 7 18z")}',
'.nfld{flex:1;min-width:0;text-align:left;border:1px solid transparent;background:var(--card);border-radius:10px;padding:11px 12px;font-size:15px;min-height:44px}.nfld .t{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nfld.ph{color:var(--mut)}.nfr.c .nfld.ph{color:var(--ink);font-weight:600;border-color:var(--acc)}.nfld:hover{border-color:var(--acc)}',
'.nib{flex:none;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;padding:0;border:0;background:none;border-radius:12px;color:var(--mut)}.nib:hover{background:var(--card);color:var(--ink)}',
'.nform .nleg2{padding:0 0 0 13px;min-height:28px;gap:14px}.nform .nleg2 .bar{width:4px;height:26px;background:repeating-linear-gradient(var(--mut) 0 3px,transparent 3px 7px);opacity:.7}.nform .nleg2 .bar[style]{opacity:1}',
'.nform .lpill{height:26px;font-size:12px;font-weight:500;padding:0 10px;border:1px solid var(--line);background:var(--card);color:var(--mut)}',
'.nfa{display:flex;align-items:center;gap:4px;padding:4px 4px 0 36px;flex-wrap:wrap}.nfa small{margin-left:auto;font-size:11.5px}',
'.nlink{border:0;background:none;color:var(--acc);font-weight:600;padding:8px 8px;display:inline-flex;align-items:center;gap:4px;font-size:14px}.nlink:hover{text-decoration:underline}',
'.nfav{margin:10px 0 0}.nfav .chips{align-items:center}.nfl{margin-right:2px}.nloop{margin:12px 0 0}.nloop[hidden],.nfav[hidden]{display:none}.nloop .nrow{margin-top:8px}.nloop .nrow input{max-width:200px}',
'.nskip{margin-top:10px}.nskip .chips{margin:0}.nskip .chip.nadd{border-style:dashed;color:var(--mut)}',
'.ngo{margin:14px 0 4px}.ngo .pri{flex:1;height:52px;font-size:16px;border-radius:14px}',
'.nmsg.busy{color:var(--mut);display:flex;align-items:center;gap:8px}.nmsg.busy::before,.nsoload::before{content:"";width:16px;height:16px;border-radius:50%;border:2px solid var(--line);border-top-color:var(--acc);animation:nspin .7s linear infinite;flex:none}@keyframes nspin{to{transform:rotate(360deg)}}',
'.nsbtn{display:flex;align-items:center;gap:10px;width:100%;max-width:560px;height:50px;border-radius:14px;border:1px solid var(--line);background:var(--card);box-shadow:0 4px 16px rgba(0,0,0,.28);padding:0 16px;font-size:16px;color:var(--mut);text-align:left}.nsbtn svg{color:var(--acc);flex:none}',
'.npickbar{display:flex;align-items:center;gap:10px;justify-content:space-between;background:var(--acc);color:#fff;border-radius:12px;padding:6px 6px 6px 14px;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,.3)}.npickbar[hidden]{display:none}.npickbar button{background:#fff2;border:0;color:#fff;padding:8px 12px}',
'.nso{position:fixed;inset:0;z-index:10005;background:var(--bg);display:flex;flex-direction:column;animation:nsoin .16s ease-out}@keyframes nsoin{from{opacity:0;transform:translateY(12px)}}body.nso-on{overflow:hidden}',
'.nsotop{display:flex;align-items:center;gap:4px;padding:calc(8px + env(safe-area-inset-top,0px)) 10px 8px 4px;border-bottom:1px solid var(--line);background:var(--card)}',
'.nsotop{justify-content:center}.nsoin{max-width:600px;flex:1;display:flex;align-items:center;background:var(--card2);border:1px solid var(--line);border-radius:12px;padding-right:2px}.nsoin:focus-within{border-color:var(--acc)}.nsoin input{flex:1;min-width:0;border:0;background:none;outline:0;height:46px;padding:0 12px;font-size:17px}.nsoin input::-webkit-search-cancel-button{display:none}.nsoin .nib{width:38px;height:38px}',
'.nsobody{flex:1;overflow:auto;padding:6px 12px 30px;-webkit-overflow-scrolling:touch;max-width:640px;width:100%;margin:0 auto}',
'.nsoh{font-size:12px;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.07em;margin:16px 6px 4px}',
'.nsol{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-top:8px}',
'.nsr2{display:flex;align-items:center;border-top:1px solid var(--line)}.nsr2:first-child{border-top:0}.nsrb{flex:1;min-width:0;display:flex;align-items:center;gap:12px;border:0;border-radius:0;background:none;text-align:left;padding:10px 12px;min-height:56px}.nsrb:hover{background:var(--card2)}',
'.nsri{flex:0 0 36px;height:36px;border-radius:50%;background:var(--card2);display:flex;align-items:center;justify-content:center;font-size:17px}.nsrb .tx{flex:1;min-width:0}.nsrb b{display:block;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nsrb small{display:block;color:var(--mut);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
'.nfavb{color:var(--warn)}.nsotip{color:var(--mut);font-size:13.5px;margin:14px 6px;line-height:1.5}.nsoload{display:flex;justify-content:center;padding:12px}',
'.npin{background:none;border:0}.npin svg{display:block;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}',
'.ntapp .leaflet-popup-content-wrapper{border-radius:14px;padding:0}.ntapp .leaflet-popup-content{margin:8px}.ntap{display:flex;flex-direction:column;gap:6px;min-width:150px}.ntap button{padding:9px 12px;font-size:14px;color:#141a26;background:#f4f6fa;border-color:#dde3ec}.ntap button.pri{color:#fff;background:#1c6ef2;border-color:#1c6ef2}',
'.ncard{gap:8px;padding:14px}.ncard .ntm{display:flex;flex-direction:column;align-items:flex-end;line-height:1.15}.ncard .ntm b{font-size:19px;font-variant-numeric:tabular-nums}.ncard .ntm small{color:var(--mut);font-size:12.5px}.ncard .ac{grid-template-columns:repeat(auto-fit,minmax(90px,1fr))}.ncard .ac button{min-height:44px}',
'.nrt{align-items:center;flex-wrap:nowrap;gap:6px;padding:4px 0}.nrtb{border:0;background:none;text-align:left;padding:8px 2px;border-radius:8px}.nrtb b{font-weight:600}.nrt .acts button{min-height:40px}.nrt .acts .pri{padding:8px 14px}',
'.ndemo{margin:12px 0 0}.ndemo .nlink{font-weight:500;font-size:13px;color:var(--mut)}.nempty{text-align:center;padding:22px 10px 8px}.nempty b{display:block;font-size:16px;margin-bottom:4px}',
'.npick .opt.warn{color:var(--bad)}.npick>div{max-height:85vh;overflow:auto}',
'.nhero{display:grid;grid-template-columns:1fr 1fr;gap:10px}.nht{background:var(--card2);border-radius:12px;padding:10px 12px;min-width:0}.nhl{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--mut)}.nht b{display:block;font-size:19px;margin:3px 0 1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nht small{display:block;color:var(--mut);font-size:12px;line-height:1.3}@media(min-width:620px){.nhero{grid-template-columns:repeat(4,1fr)}}',
'@media(min-width:900px){.nsbtn{max-width:480px}}'
].join('');
document.head.append(css2);
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
    try{NV.data=await J('api/nav/routes');statusCard(V)}catch(e){}try{heroCard(V)}catch(e){}};
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
  // 1.5.26: panel w trzech zakładkach zamiast jednej długiej listy
  P.tabs=el('div','seg nstabs');P.pane={};
  for(const [k,t] of [['plan','Planuj'],['saved','Moje trasy'],['trip','W trasie']]){const b=el('button',null,t);b.type='button';b._k=k;b.onclick=()=>{paneTab(k);if(NV.sheetH==='min')sheet('mid')};P.tabs.append(b);const d=el('div','npane');d.hidden=true;P.pane[k]=d}
  P.sc.append(P.tabs,P.pane.plan,P.pane.saved,P.pane.trip);
  plannerCard(P.pane.plan);RC=null;routesCard(P.pane.saved);tripCard(P.pane.trip);P.sc.append(el('div','nattr','Mapa: © OpenStreetMap, OpenMapTiles, OpenFreeMap · Leaflet, MapLibre'));
  if(!NV.pts.length){const d=defStart();if(d)setPts([d])}
  paneTab(NV.pane||'plan');sheet(NV.sheetH||'mid');await initMap();renderSkip();drawFav()}
function paneTab(k){NV.pane=k;if(!P.tabs)return;for(const b of P.tabs.children)b.classList.toggle('on',b._k===k);for(const x in P.pane)P.pane[x].hidden=x!==k;if(k==='trip'&&T.box)tripLoad();if(P.sc)P.sc.scrollTop=0}
// domyślny start: świeża pozycja motocykla z ekranu, inaczej dom
function defStart(){const s=NV.data.screen,fresh=s&&s.t&&Date.now()/1000-s.t<3*3600;if(fresh)return{lat:s.lat,lon:s.lon,name:'pozycja motocykla'};const h=NV.data.settings.home;return h?{lat:h.lat,lon:h.lon,name:h.name||'Dom'}:null}
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

// 1.5.26: Motocykl – na górze cztery kafle: przebieg, serwis, skrzynka, ekran (szczegóły niżej)
function heroCard(V){const h=(typeof ST!=='undefined'&&ST&&ST.ha)||{},k=el('div','card nhero');
  const tile=(lv,ttl,big,sub)=>{const d=el('div','nht');const t=el('span','nhl');t.append(el('i','dot '+lv),ttl);d.append(t,el('b',null,big),el('small',null,sub||''));k.append(d)};
  const ms=v=>v===null||v===undefined?null:typeof v==='number'?(v<1e12?v*1000:v):Date.parse(v);
  tile(h.odo?'ok':'','Przebieg',h.odo?fmt(h.odo)+' km':'–',h.odo?'liczony z jazd':'wpisz stan licznika w Ustawieniach');
  const sv=(h.service||[]).filter(x=>x.left_km!==null&&x.left_km!==undefined).sort((a,b)=>a.left_km-b.left_km)[0];
  tile(sv?(sv.left_km<0?'bad':sv.left_km<300?'warn':'ok'):'','Serwis',sv?(sv.left_km<0?'po terminie':'za '+fmt(sv.left_km)+' km'):'–',sv?sv.name:'brak danych o ostatnim serwisie');
  const bs=ms(h.box_seen);tile(bs?(Date.now()-bs<86400e3*3?'ok':'warn'):'','Skrzynka',bs?since(bs):'nie zgłosiła się',[h.box_fw?'wersja '+h.box_fw:'',h.box_battery!==null&&h.box_battery!==undefined?'bateria '+h.box_battery+'%':''].filter(Boolean).join(' · '));
  const sc=NV.data&&NV.data.screen,fr=sc&&sc.t&&Date.now()/1000-sc.t<600;tile(fr?'ok':sc&&sc.t?'':'','Ekran',fr?'połączony':sc&&sc.t?ago(sc.t):'nie zgłosił się',sc&&sc.t?[sc.fw?'wersja '+sc.fw:'',sc.battery!==undefined?'bateria '+sc.battery+'%':''].filter(Boolean).join(' · '):'');
  V.prepend(k)}
function statusCard(V){const d=NV.data,k=el('div','card');k.append(el('b',null,'Ekran i mapa'));
  const add=(lv,t,v,n)=>sRow(k,lv,t,v,n);
  const s=d.screen;if(s&&s.t){const fresh=Date.now()/1000-s.t<600;add(fresh?'ok':'','Ekran',fresh?'połączony':'ostatnio '+ago(s.t),[s.fw?'wersja '+s.fw:'',s.battery!==undefined?'bateria '+s.battery+'%':'',s.map?'mapa '+s.map:'',fresh?ago(s.t):''].filter(Boolean).join(' · '))}else add('','Ekran','jeszcze się nie zgłosił','klucz jak w skrzynce (zakładka Ustawienia)');
  const m=d.map;if(m.available)add('ok','Mapa na kartę',m.mb+' MB','zbudowana '+(m.built||'?')+' · '+m.files+' plików'+(m.sync&&m.sync.t?' · sprawdzono '+ago(m.sync.t):''));else add('warn','Mapa na kartę','brak',m.source_url?'pobierz z kontenera (przycisk niżej)':'podaj adres kontenera: Ustawienia → Ustawienia nawigacji');
  add(d.engine?'ok':'warn','Silnik tras',d.engine?'ustawiony':'brak adresu',d.engine?d.settings.engine_url:'bez niego działa tylko GPX i trasy proste');
  const b=d.build;if(b&&b.pracuje)add('warn','Kontener z mapą','przebudowa '+(b.krok||'?')+'/'+(b.z||5)+(b.proc!==undefined?' · '+b.proc+'%':''),(b.etap||'')+' · od '+ago(b.od));
  else if(b&&b.ok===false&&Date.now()/1000-b.t<7*86400)add('bad','Kontener z mapą','przebudowa nieudana',b.etap||'');
  else if(b&&b.ok&&b.t)add('ok','Kontener z mapą','mapy aktualne','przebudowa skończona '+ago(b.t));
  add(d.settings.tomtom_key?'ok':'','Korki',d.settings.tomtom_key?'włączone (TomTom)':'wyłączone',d.settings.tomtom_key?'':'klucz TomTom w Ustawieniach nawigacji');
  const a=el('div','acts');const sb=el('button',null,'Pobierz mapę z kontenera');const sm=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;msg(sm,'sprawdzanie i pobieranie... (może potrwać kilka minut)');try{const j=await post('api/nav/map/sync',{});msg(sm,j.ok?(j.changed?'pobrano '+j.files+' plików, mapa z '+j.built:'mapa aktualna ('+j.built+')'):j.error,j.ok?'ok':'bad')}catch(e){msg(sm,e.message,'bad')}sb.disabled=false};a.append(sb,sm);k.append(a);
  if(m.available){const z=d.zip||{};const a2=el('div','acts');const zm=el('span','nmsg');
    if(z.ready){const l=el('button',null,'Pobierz paczkę ZIP na kartę ('+z.mb+' MB)');l.onclick=()=>{const x=document.createElement('a');x.href='api/nav/mapa.zip';x.download='mapa-ekranu.zip';document.body.append(x);x.click();x.remove()};a2.append(l)}
    else{const zb=el('button',null,z.working?'Paczka ZIP się przygotowuje…':'Przygotuj paczkę ZIP na kartę');zb.disabled=!!z.working;zb.onclick=async()=>{zb.disabled=true;try{await fetch('api/nav/mapa.zip')}catch(e){}msg(zm,'przygotowuję paczkę, to potrwa kilka minut; wróć tu później','ok')};a2.append(zb)}
    a2.append(zm);k.append(a2);k.append(el('small','mut','Pierwsze wgranie: rozpakuj ZIP na kartę ekranu (powstanie folder „mapa”). Dalej ekran dociąga w domu tylko zmienione kwadraty.'))}
  V.append(k)}

/* ---- planer: pola Start / Cel jak w nawigacji (1.5.26) */
let P={};
const ICO={search:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>',
  up:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M12 5l-6 6M12 5l6 6"/></svg>',
  down:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M12 19l-6-6M12 19l6-6"/></svg>',
  swap:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4v16M7 4L3 8M7 4l4 4M17 20V4M17 20l-4-4M17 20l4-4"/></svg>',
  x:'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  back:'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  plus:'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  more:'<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>'};
function ib(svg,label,cls){const b=el('button','nib'+(cls?' '+cls:''));b.type='button';b.innerHTML=svg;b.title=label;b.setAttribute('aria-label',label);return b}
function plannerCard(V){const k=el('div','card');V.append(k);
  const hd=el('div','nhead');hd.append(el('b',null,'Nowa trasa'));
  P.veh=el('div','nvseg');for(const [v,t,ti] of [['moto','🏍 Motocykl','motocykl: warianty krętości'],['auto','🚗 Auto','samochód: najszybsza trasa']]){const c=el('button',null,t);c.type='button';c._v=v;c.title=ti;c.onclick=()=>setVehicle(v);P.veh.append(c)}hd.append(P.veh);k.append(hd);
  P.drv=el('div','nrt ndrv');P.drv.hidden=true;k.append(P.drv);
  // nad mapą: jedno duże pole „Dokąd jedziesz?” (otwiera wyszukiwarkę celu)
  const sb=el('button','nsbtn');sb.type='button';sb.innerHTML=ICO.search;sb.append(el('span',null,'Dokąd jedziesz?'));sb.onclick=()=>openSearch('cel');P.bar.append(sb);
  P.trip=el('div','ntrip');P.trip.hidden=true;P.trip.append(el('i'),el('span',null,'Motocykl w trasie · co po drodze ›'));P.trip.onclick=()=>{paneTab('trip');sheet('max')};P.bar.append(P.trip);
  P.pickBar=el('div','npickbar');P.pickBar.hidden=true;P.bar.append(P.pickBar);
  // do celu albo pętla
  P.mode=el('div','seg nmode');for(const [m,t] of [['to','Do celu'],['loop','Pętla z powrotem']]){const b=el('button',null,t);b.type='button';b._m=m;b.onclick=()=>setMode(m);P.mode.append(b)}k.append(P.mode);
  P.list=el('div','nform');k.append(P.list);
  P.favBox=el('div','nfav');k.append(P.favBox);renderFav();
  P.rtBox=el('div','nloop');P.rtBox.append(el('small','mut','Ile chcesz pojeździć? Pętla zaczyna się i kończy na starcie.'));P.rtc=el('div','chips nrtc');P.rtBox.append(P.rtc);
  for(const [t,o] of RT_OPTS){const c=el('span','chip',t);c._o=o;c.onclick=()=>pickRt(o);P.rtc.append(c)}
  const r2=el('div','nrow');P.rt=el('input');P.rt.type='number';P.rt.inputMode='numeric';P.rt.placeholder='inna długość (km)';P.rt.min=10;P.rt.max=1500;P.rt.oninput=()=>{NV.rt=null;renderRt()};r2.append(P.rt);P.rtBox.append(r2);k.append(P.rtBox);
  // pomijane miejscowości
  P.skipBox=el('div','nskip');k.append(P.skipBox);renderSkip();
  const S=NV.data.settings;
  const op=el('details','ngrp nopts');op.append(el('summary',null,'Więcej: warianty, omijanie dróg, nazwa, punkty na mapie, GPX'));k.append(op);
  P.var={};P.varC={};const vc=el('div','chips');for(const [v,t] of NV.data.variants){const c=el('span','chip on',t);c.onclick=()=>{c.classList.toggle('on');P.var[v]=c.classList.contains('on')};P.var[v]=true;P.varC[v]=c;vc.append(c)}op.append(el('small',null,'Warianty do porównania:'),vc);
  P.av={};const ac=el('div','chips');for(const v of NV.data.avoid_all){const on=(S.avoid||[]).includes(v);const c=el('span','chip'+(on?' on':''),'omijaj: '+AVN[v]);c.onclick=()=>{c.classList.toggle('on');P.av[v]=c.classList.contains('on')};P.av[v]=on;ac.append(c)}op.append(ac);
  const r3=el('div','nrow');P.name=el('input');P.name.placeholder='nazwa trasy (opcjonalnie)';P.name.maxLength=40;r3.append(P.name);op.append(r3);
  const mo=el('div','acts');P.poiBtn=el('button',null,'Pokaż na mapie: fotoradary, stacje, widoki');P.poiBtn.onclick=togglePoi;mo.append(P.poiBtn);op.append(mo);P.leg=el('div','nleg');P.leg.hidden=true;for(const [kd,t] of LEG){const sp=el('span');const i=el('i');i.style.background=KIND[kd][1];sp.append(i,t);P.leg.append(sp)}P.legHint=el('small','mut','');P.leg.append(P.legHint);op.append(P.leg);
  const g=el('div','acts');const f=el('input');f.type='file';f.accept='.gpx,application/gpx+xml';f.hidden=true;const gb=el('button',null,'Wczytaj GPX (np. z Kurvigera) i wyślij na ekran');const gm=el('span','nmsg');gb.onclick=()=>f.click();
  f.onchange=async()=>{const file=f.files[0];if(!file)return;gb.disabled=true;msg(gm,'wczytywanie...');try{const body=await file.arrayBuffer();const r=await api('api/nav/gpx?name='+encodeURIComponent(file.name.replace(/\.gpx$/i,'')),{method:'POST',headers:{'Content-Type':'application/gpx+xml'},body});const j=await r.json();if(!r.ok)throw new Error(j.error||'błąd');msg(gm,'trasa „'+j.route.name+'” ('+j.route.km+' km) zapisana i ustawiona na ekran','ok');NV.data=await J('api/nav/routes');routesCard(null);showRoute(j.route)}catch(e){msg(gm,e.message,'bad')}gb.disabled=false;f.value=''};
  g.append(gb,f,gm);op.append(g);
  const a=el('div','acts ngo');P.go=el('button','pri','Policz trasę');P.go.onclick=plan;a.append(P.go);k.append(a);P.msg=el('div','nmsg');k.append(P.msg);
  P.out=el('div');k.append(P.out);
  P.along=el('div');P.along.hidden=true;k.append(P.along);
  renderVehicle(true);renderDrive();renderMode()}
function setMode(m){NV.loop=m==='loop';if(!NV.loop){NV.rt=null;if(P.rt)P.rt.value='';renderRt()}clearPlan();renderMode()}
function renderMode(){if(P.mode)for(const b of P.mode.children)b.classList.toggle('on',(b._m==='loop')===!!NV.loop);if(P.rtBox)P.rtBox.hidden=!NV.loop;if(P.favBox)P.favBox.hidden=!!NV.loop;
  renderModeBtn();renderPts()}
/* tryb pojazdu: w samochodzie liczona tylko najszybsza (inne warianty można włączyć ręcznie),
   ekran bez „wyniku zakrętu”; „jedź do” z iPhone’a i objazdy też najszybciej */
function renderVehicle(vars){const v=NV.data.settings.vehicle||'moto';if(P.veh)for(const c of P.veh.children)c.classList.toggle('on',c._v===v);
  if(vars&&P.varC)for(const k of Object.keys(P.varC)){const on=v==='moto'||k==='szybko';P.varC[k].classList.toggle('on',on);P.var[k]=on}}
async function setVehicle(v){if((NV.data.settings.vehicle||'moto')===v)return;try{const s=await post('api/nav/settings',{vehicle:v});NV.data.settings=s;renderVehicle(true);if(NV.plan)clearPlan();toast(v==='auto'?'Tryb samochód: najszybsza trasa, ekran bez wyniku zakrętu':'Tryb motocykl: wszystkie warianty krętości')}catch(e){alert(e.message)}}

const RT_OPTS=[['50 km',{km:50}],['100 km',{km:100}],['150 km',{km:150}],['200 km',{km:200}],['30 min',{min:30}],['1 h',{min:60}],['1,5 h',{min:90}],['2 h',{min:120}],['3 h',{min:180}]];
function rtLabel(o){return o.km?o.km+' km':(o.min>=60?(o.min/60+'').replace('.',',')+' h':o.min+' min')}
function renderRt(){if(!P.rtc)return;for(const c of P.rtc.children)c.classList.toggle('on',!!NV.rt&&c._o===NV.rt)}
function pickRt(o){if(NV.rt===o){NV.rt=null;renderRt();return}NV.rt=o;if(!NV.loop){NV.loop=true;renderMode()}if(P.rt)P.rt.value='';renderRt();
  if(!NV.pts.length){const h=NV.data.settings.home;const s=NV.data.screen;
    if(h)setPts([{lat:h.lat,lon:h.lon,name:h.name||'Dom'}]);else if(s&&s.t)setPts([{lat:s.lat,lon:s.lon,name:'pozycja motocykla'}]);
    else{toast('Ustaw dom (Ustawienia → Ustawienia nawigacji) albo dodaj start.');NV.rt=null;renderRt();return}}
  plan()}
function skipRadius(r){if(r.r)return r.r;const e=r.extent;if(e&&e.length===4){const dy=(e[1]-e[3])*110540/2,dx=(e[2]-e[0])*111320*Math.cos(r.lat*Math.PI/180)/2;return Math.round(Math.min(6000,Math.max(500,Math.hypot(dx,dy)*0.9)))}
  return {city:3500,town:1800,village:800,hamlet:400,suburb:1200}[r.type]||700}
function addSkip(r){const sp={lat:r.lat,lon:r.lon,name:(r.name||'').slice(0,40),r:skipRadius(r)};NV.skip.push(sp);renderSkip();if(NV.map)NV.map.panTo([sp.lat,sp.lon]);if(NV.plan)toast('Pomijam „'+(sp.name||'miejsce')+'”. Policz trasę jeszcze raz.')}
function renderSkip(){if(!P.skipBox)return;P.skipBox.textContent='';const row=el('div','chips');
  for(const sp of NV.skip){const c=el('span','chip');c.append(el('b',null,'✕'),'omiń: '+(sp.name||'miejsce'));c.title='usuń z pomijanych';c.onclick=()=>{NV.skip=NV.skip.filter(x=>x!==sp);renderSkip()};row.append(c)}
  const add=el('span','chip nadd','+ omiń miejscowość');add.onclick=()=>openSearch('skip');row.append(add);P.skipBox.append(row);
  if(NV.map){if(NV.skipL)NV.skipL.remove();NV.skipL=L.layerGroup().addTo(NV.map);for(const sp of NV.skip)L.circle([sp.lat,sp.lon],{radius:sp.r,color:'#e03131',weight:2,dashArray:'6 6',fillOpacity:.08}).bindTooltip('omijam: '+(sp.name||'miejsce')).addTo(NV.skipL)}}
function setPts(p){NV.pts=p;const n=Math.max(0,p.length-1);NV.legs=NV.legs.slice(0,n);while(NV.legs.length<n)NV.legs.push('');renderPts();drawMarkers()}
function setStart(p){const rest=NV.pts.slice(1);setPts([p].concat(rest))}
function addPt(p){applyPick(NV.pts.length>=2?'stop':'cel',p)}
const coordTxt=p=>p.lat.toFixed(5)+', '+p.lon.toFixed(5);
// formularz trasy: Start, przystanki, Cel (dotknięcie pola = wyszukiwarka dla tego miejsca)
function renderPts(){if(!P.list)return;P.list.textContent='';drawLegs();renderFav();const N=NV.pts.length,loop=!!NV.loop;
  const row=(kind,i,p,ph)=>{const r=el('div','nfr '+kind);const ic=el('span','nic');if(kind==='v')ic.textContent=String(i);r.append(ic);
    const f=el('button','nfld'+(p?'':' ph'));f.type='button';const t=el('span','t',p?(p.name||coordTxt(p)):ph);f.append(t);if(p)f.title=coordTxt(p);
    f.onclick=()=>openSearch(kind==='s'?'start':kind==='c'?'cel':i);r.append(f);
    if(p&&kind==='v'){const mv=d=>{const a=NV.pts.slice(),j=i+d;[a[i],a[j]]=[a[j],a[i]];setPts(a);NV.plan?autoPlan():null};
      if(i>1){const u=ib(ICO.up,'przystanek wyżej');u.onclick=()=>mv(-1);r.append(u)}
      if(i<N-2){const d=ib(ICO.down,'przystanek niżej');d.onclick=()=>mv(1);r.append(d)}}
    if(p&&kind!=='s'){const x=ib(ICO.x,kind==='c'?'usuń cel':'usuń przystanek');x.onclick=()=>{const a=NV.pts.slice();a.splice(i,1);setPts(a);NV.plan?autoPlan():null};r.append(x)}
    else if(kind==='s'&&!loop&&N>=2){const sw=ib(ICO.swap,'zamień start z celem');sw.onclick=()=>{setPts(NV.pts.slice().reverse());NV.legs.reverse();renderPts();autoPlan()};r.append(sw)}
    return r};
  P.list.append(row('s',0,NV.pts[0],'Skąd? Dom, motocykl albo adres'));
  if(!loop){for(let i=1;i<N;i++){P.list.append(legRow(i-1));P.list.append(row(i===N-1?'c':'v',i,NV.pts[i]))}
    if(N<2)P.list.append(row('c',1,null,'Dokąd jedziesz?'));
    const a=el('div','nfa');if(N>=2){const st=el('button','nlink');st.type='button';st.innerHTML=ICO.plus;st.append(' przystanek');st.onclick=()=>openSearch('stop');a.append(st)}
    if(N>=2){const cl=el('button','nlink');cl.type='button';cl.textContent='Wyczyść';cl.onclick=()=>{const d=defStart();setPts(d?[d]:[]);NV.skip=[];renderSkip();clearPlan();renderMode()};a.append(cl)}
if(a.children.length)P.list.append(a)}}
// wybór miejsca dla pola: 'start' | 'cel' | 'stop' | 'skip' | numer punktu
function applyPick(slot,p){addRecent(p);if(slot==='skip'){addSkip(p);return}
  const a=NV.pts.slice();
  if(slot==='start'){if(a.length)a[0]=p;else a.push(p);setPts(a);if(NV.pendCel){const c=NV.pendCel;NV.pendCel=null;applyPick('cel',c);return}}
  else if(slot==='cel'||(slot==='stop'&&a.length<2)){if(NV.loop){NV.loop=false;NV.rt=null;renderRt();renderMode()}
    if(!a.length){const d=defStart();if(!d){NV.pendCel=p;toast('Skąd startujesz?');openSearch('start');return}a.push(d)}
    if(a.length>=2)a[a.length-1]=p;else a.push(p);setPts(a)}
  else if(slot==='stop'){a.splice(a.length-1,0,p);setPts(a)}
  else if(typeof slot==='number'){a[slot]=p;setPts(a)}
  fitAll();autoPlan()}
// po wybraniu celu trasa liczy się sama (jak w nawigacji)
function autoPlan(){if(NV.loop)return;clearTimeout(NV.apT);if(NV.pts.length>=2&&NV.data.engine)NV.apT=setTimeout(plan,200);else clearPlan()}
// odcinek między punktami: przycisk z wybraną krętością (pusty = jak cała trasa)
const LDESC={szybko:'główne drogi, najkrócej w czasie',lekko:'boczne drogi, niewiele dłużej',kreto:'szuka zakrętów, wyraźnie dłużej',bardzo:'przełęcze i serpentyny, czas mniej ważny'};
function legRow(k){const r=el('div','nleg2');const v=NV.legs[k];const bar=el('span','bar');if(v)bar.style.background=VCOL[v];r.append(bar);
  const b=el('button','lpill');b.type='button';b.title='jak jechać ten odcinek';const i=el('i');i.style.background=v?VCOL[v]:'var(--mut)';b.append(i,(v?VN(v):'odcinek: jak cała trasa')+' ▾');if(v){b.style.borderColor=VCOL[v]}b.onclick=()=>pickLeg(k);r.append(b);return r}
function legName(k){const N=NV.pts.length;const n=i=>(NV.pts[i]&&NV.pts[i].name)||(i===0?'start':i===N-1?'cel':'punkt '+i);return n(k)+' → '+n(k+1)}
function pickLeg(k){const o=el('div','npick');const d=el('div');o.append(d);const close=()=>o.remove();o.onclick=e=>{if(e.target===o)close()};
  d.append(el('h3',null,'Jak jechać ten odcinek?'),el('small','mut',legName(k)+'. Reszta trasy zostaje bez zmian.'));
  for(const [v,t] of NV.data.variants){const b=el('button','opt'+(NV.legs[k]===v?' on':''));const i=el('i');i.style.background=VCOL[v];const sp=el('span');sp.append(el('b',null,t),el('small',null,LDESC[v]||''));b.append(i,sp);if(NV.legs[k]===v)b.style.borderColor=VCOL[v];b.onclick=()=>{NV.legs[k]=v;close();renderPts();if(NV.plan)autoPlan()};d.append(b)}
  const r2=el('div','row2');const all=el('button',null,'Jak cała trasa');all.onclick=()=>{NV.legs[k]='';close();renderPts();if(NV.plan)autoPlan()};const sl=el('button',null,'Dostosuj suwaki');sl.onclick=()=>{close();tab('set');setTimeout(()=>{const c=[...document.querySelectorAll('#v-set details')].find(x=>/Krętość/.test(x.firstChild&&x.firstChild.textContent||''));if(c){let p=c;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement}c.scrollIntoView({block:'start'})}},700)};r2.append(all,sl);d.append(r2);document.body.append(o)}
// odcinki na mapie przed liczeniem: kreska w kolorze wybranej krętości, dotknięcie = wybór
function drawLegs(){if(!NV.map)return;if(NV.legL)NV.legL.remove();NV.legL=L.layerGroup().addTo(NV.map);if(NV.lines.length)return;
  for(let k=0;k<NV.pts.length-1;k++){const a=NV.pts[k],b=NV.pts[k+1],v=NV.legs[k];const ll=[[a.lat,a.lon],[b.lat,b.lon]];
    L.polyline(ll,{color:'#000',weight:14,opacity:0}).on('click',e=>{L.DomEvent.stop(e);pickLeg(k)}).addTo(NV.legL);
    L.polyline(ll,{color:v?VCOL[v]:'#8b98ae',weight:v?4:3,opacity:.9,dashArray:'6 8',interactive:false}).addTo(NV.legL)}}
const isLink=t=>/https?:\/\//i.test(t)||/^geo:/i.test(t)||/^-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+$/.test(t.trim());
/* ---- wyszukiwarka miejsca na cały ekran (1.5.26): podpowiedzi w trakcie pisania, skróty, ostatnie */
const RECENT='nt-ostatnie';
function recents(){try{const a=JSON.parse(localStorage.getItem(RECENT)||'[]');return Array.isArray(a)?a:[]}catch(e){return[]}}
function addRecent(p){if(!p||!p.name||/^(pozycja|zaznaczone|Dom$)/.test(p.name)||isFav(p))return;try{const a=recents().filter(x=>!(Math.abs(x.lat-p.lat)<1e-4&&Math.abs(x.lon-p.lon)<1e-4));a.unshift({lat:p.lat,lon:p.lon,name:p.name,label:p.label||''});localStorage.setItem(RECENT,JSON.stringify(a.slice(0,8)))}catch(e){}}
const SLOTN={start:'Skąd startujesz?',cel:'Dokąd jedziesz?',stop:'Gdzie po drodze?',skip:'Którą miejscowość ominąć?'};
const PIK={stacja:'⛽',jedzenie:'🍴',kawiarnia:'☕',widok:'👁',przełęcz:'⛰',nocleg:'🛏',ładowarka:'🔌','serwis moto':'🔧',odpoczynek:'🌲'};
const TIK={city:'🏙',town:'🏘',village:'🏡',hamlet:'🏡',suburb:'🏘',house:'📍',street:'🛣',road:'🛣',residential:'🛣',fuel:'⛽',restaurant:'🍴',cafe:'☕',hotel:'🛏'};
let SQ={};
function searchRef(){const p=NV.pts[0];if(p)return p;if(NV.map){const c=NV.map.getCenter();return{lat:c.lat,lon:c.lng}}return null}
function distTxt(p){const r=searchRef();if(!r||p.lat===undefined)return'';const d=Math.hypot((p.lat-r.lat)*110.5,(p.lon-r.lon)*111.3*Math.cos(r.lat*Math.PI/180));return d<1?Math.round(d*1000)+' m':kmTxt(d)}
function closeSearch(){if(SQ.o){SQ.o.remove();SQ={};document.body.classList.remove('nso-on')}}
function openSearch(slot){closeSearch();const o=el('div','nso');o.setAttribute('role','dialog');SQ={o,slot,seq:0};
  const top=el('div','nsotop');const back=ib(ICO.back,'wróć');back.onclick=closeSearch;const inp=el('input');inp.type='search';inp.enterKeyHint='search';inp.autocomplete='off';inp.spellcheck=false;
  inp.placeholder=typeof slot==='number'?'Zmień punkt '+slot:SLOTN[slot];inp.setAttribute('aria-label',inp.placeholder);const clr=ib(ICO.x,'wyczyść');clr.hidden=true;clr.onclick=()=>{inp.value='';clr.hidden=true;inp.focus();sQuick()};
  const w=el('div','nsoin');w.append(inp,clr);top.append(back,w);const body=el('div','nsobody');o.append(top,body);document.body.append(o);document.body.classList.add('nso-on');SQ.inp=inp;SQ.body=body;
  inp.oninput=()=>{clr.hidden=!inp.value;clearTimeout(SQ.t);SQ.t=setTimeout(()=>sQuery(false),260)};
  inp.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(SQ.t);sQuery(true)}else if(e.key==='Escape')closeSearch()};
  inp.focus();sQuick()}
function sItem(box,ico,name,sub,onPick,extra){const r=el('div','nsr2');const b=el('button','nsrb');b.type='button';const i=el('span','nsri',ico);const tx=el('span','tx');tx.append(el('b',null,name));if(sub)tx.append(el('small',null,sub));b.append(i,tx);b.onclick=onPick;r.append(b);if(extra)r.append(extra);box.append(r);return r}
function sHead(box,t){box.append(el('div','nsoh',t))}
function sPick(p){const slot=SQ.slot;closeSearch();applyPick(slot,p);const i=NV.pts.indexOf(p);if(i>=0&&!p.name)nameLater(i)}
function sQuick(){const B=SQ.body;if(!B)return;B.textContent='';const slot=SQ.slot,box=el('div','nsol');B.append(box);
  if(slot!=='skip'){const s=NV.data.screen;if(s&&s.t)sItem(box,'🏍','Pozycja motocykla',(Date.now()/1000-s.t<600?'teraz':'z ekranu, '+ago(s.t)),()=>sPick({lat:s.lat,lon:s.lon,name:'pozycja motocykla'}));
    const h=NV.data.settings.home;if(h)sItem(box,'⌂',h.name||'Dom','ustawiony w Ustawieniach nawigacji',()=>sPick({lat:h.lat,lon:h.lon,name:h.name||'Dom'}));
    if(navigator.geolocation)sItem(box,'◎','Moja pozycja','z telefonu',()=>{const b=SQ.body;navigator.geolocation.getCurrentPosition(p=>sPick({lat:p.coords.latitude,lon:p.coords.longitude,name:'moja pozycja'}),()=>{if(b){b.prepend(el('p','nmsg bad','Brak zgody na pozycję albo brak sygnału.'))}},{enableHighAccuracy:true,timeout:15000,maximumAge:60000})})}
  sItem(box,'🗺','Wskaż na mapie','dotknij miejsca na mapie',()=>{const sl=SQ.slot;closeSearch();pickOnMap(sl)});
  if(slot!=='skip'&&favs().length){sHead(B,'Ulubione');const fb=el('div','nsol');B.append(fb);for(const f of favs())sItem(fb,'★',f.name,distTxt(f),()=>sPick({lat:f.lat,lon:f.lon,name:f.name}))}
  const rc=recents();if(rc.length){sHead(B,'Ostatnio');const rb=el('div','nsol');B.append(rb);for(const r of rc)sItem(rb,'🕘',r.name,[r.label&&r.label!==r.name?r.label:'',distTxt(r)].filter(Boolean).join(' · '),()=>sPick({lat:r.lat,lon:r.lon,name:r.name}))}
  B.append(el('p','nsotip',slot==='skip'?'Wpisz nazwę miejscowości, przez którą trasa ma nie prowadzić.':'Wpisz nazwę miejsca albo adres, np. „Szczyrk”, „Bieruń Turyńska 5”, „Orlen Tychy”. Możesz też wkleić link z Map Google lub Apple albo współrzędne.'))}
async function sQuery(enter){const q0=SQ.inp?SQ.inp.value.trim():'';if(q0.length<2){sQuick();return}const B=SQ.body,my=++SQ.seq,slot=SQ.slot;
  if(isLink(q0)){B.textContent='';const box=el('div','nsol');B.append(box);const go=async()=>{try{const j=await J('api/nav/resolve?text='+encodeURIComponent(q0));if(my!==SQ.seq)return;sPick({lat:j.place.lat,lon:j.place.lon,name:j.place.name||'miejsce z linku'})}catch(e){if(SQ.body)SQ.body.prepend(el('p','nmsg bad',e.message))}};
    sItem(box,'🔗','Użyj tego linku',q0.slice(0,60),go);if(enter)go();return}
  if(!B.querySelector('.nsoload')){B.prepend(el('div','nsoload'))}
  const r=searchRef(),ll=r?'&lat='+r.lat.toFixed(4)+'&lon='+r.lon.toFixed(4):'';
  const [a,b]=await Promise.all([J('api/nav/search?q='+encodeURIComponent(q0)+ll).catch(e=>({err:e.message})),slot==='skip'?Promise.resolve({results:[]}):J('api/nav/miejsca?q='+encodeURIComponent(q0)+ll).catch(()=>({results:[]}))]);
  if(my!==SQ.seq||!SQ.body)return;B.textContent='';let n=0;
  const fm=slot==='skip'?[]:favMatch(q0);if(fm.length){const fb=el('div','nsol');B.append(fb);for(const f of fm){n++;sItem(fb,'★',f.name,'ulubione · '+distTxt(f),()=>sPick({lat:f.lat,lon:f.lon,name:f.name}))}}
  // Photon zwraca kilka razy tę samą miejscowość (różne ulice): ta sama nazwa w promieniu 3 km = jeden wynik
  const res=[];for(const x of (a&&a.results)||[]){if(res.some(y=>y.name===x.name&&Math.hypot((y.lat-x.lat)*110.5,(y.lon-x.lon)*71.5)<3))continue;res.push(x)}if(res.length){if(n)sHead(B,'Adresy i miejscowości');const box=el('div','nsol');B.append(box);
    for(const x of res){n++;const fv=slot==='skip'?null:ib('<span style="font-size:19px;line-height:1">☆</span>','zapisz w ulubionych','nfavb');if(fv)fv.onclick=()=>{closeSearch();saveFav({lat:x.lat,lon:x.lon,name:x.name})};
      sItem(box,TIK[x.type]||'📍',x.name,[x.label&&x.label!==x.name?x.label.replace(x.name+', ',''):'',distTxt(x)].filter(Boolean).join(' · '),()=>sPick(slot==='skip'?x:{lat:x.lat,lon:x.lon,name:x.name,label:x.label}),fv)}}
  const pl=(b&&b.results)||[];if(pl.length){sHead(B,'Miejsca z mapy (działa też bez internetu)');const box=el('div','nsol');B.append(box);
    for(const x of pl.slice(0,8)){n++;sItem(box,PIK[x.kind]||'📍',x.name,[x.kind,x.city,distTxt(x)].filter(Boolean).join(' · '),()=>sPick({lat:x.lat,lon:x.lon,name:x.name+(x.city?', '+x.city:'')}))}}
  if(a&&a.err&&pl.length)B.prepend(el('p','nsotip','Adresy wymagają internetu w Home Assistancie, poniżej tylko miejsca z mapy.'));
  if(!n)B.append(el('p','nsotip',a&&a.err?'Wyszukiwanie adresów nie działa ('+a.err+'). Spróbuj „Wskaż na mapie”.':'Nic nie znaleziono. Spróbuj krócej, np. samą miejscowość albo ulicę z miejscowością.'))}
// wskazanie miejsca dotknięciem mapy
function pickOnMap(slot){NV.mode='pick';NV.pickSlot=slot;sheet('min');lockMap(false);if(NV.map)NV.map.getContainer().classList.add('add');
  const b=P.pickBar;if(!b)return;b.textContent='';b.hidden=false;b.append(el('span',null,'Dotknij mapy: '+(slot==='start'?'start':slot==='skip'?'miejsce do ominięcia':slot==='stop'?'przystanek':typeof slot==='number'?'nowe miejsce punktu':'cel')));
  const x=el('button',null,'Anuluj');x.type='button';x.onclick=pickEnd;b.append(x)}
function pickEnd(){NV.mode='add';if(P.pickBar)P.pickBar.hidden=true;if(NV.map)NV.map.getContainer().classList.remove('add');sheet('mid')}
// dotknięcie mapy bez trybu: małe menu „Jedź tutaj / przystanek / start stąd”
function tapMenu(ll){const p={lat:ll.lat,lon:ll.lng,name:''};const d=el('div','ntap');
  const b=(t,slot,pri)=>{const x=el('button',pri?'pri':null,t);x.type='button';x.onclick=()=>{NV.map.closePopup();applyPick(slot,p);const i=NV.pts.indexOf(p);if(i>=0)nameLater(i)};d.append(x)};
  b('Jedź tutaj','cel',true);if(NV.pts.length>=2&&!NV.loop)b('Przystanek','stop');b('Start stąd','start');
  L.popup({closeButton:false,className:'ntapp',offset:[0,-2],autoPanPadding:[20,80]}).setLatLng(ll).setContent(d).openOn(NV.map)}
/* ---- mapa */
function mapFail(div,txt){div.textContent='';div.classList.remove('add');const w=el('div','nmapfail');w.append(el('b',null,txt||'Mapa się nie wczytała'),el('small','mut','Sprawdź internet albo kontener z mapą.'));const b=el('button',null,'Spróbuj jeszcze raz');b.onclick=()=>location.reload();w.append(b);div.append(w)}
async function initMap(){const div=document.getElementById('navmap');if(!div)return;const ok=await loadLeaflet();if(!ok){mapFail(div);return}
  try{NV.map=L.map(div,{zoomControl:false});if(!(L.Browser.touch&&(navigator.maxTouchPoints||0)>0))L.control.zoom({position:'topright'}).addTo(NV.map);baseLayer(NV.map);
    if(window.ResizeObserver)new ResizeObserver(()=>{if(!NV.map)return;NV.map.invalidateSize(false);if(NV.pendingFit)safeFit(NV.pendingFit)}).observe(div);
    const S=NV.data.settings,c=NV.pts[0]||S.home||{lat:52.1,lon:19.4};NV.map.setView([c.lat,c.lon],NV.pts.length?10:6);
    lockControl();
    NV.map.on('click',async e=>{const p={lat:e.latlng.lat,lon:e.latlng.lng,name:''};
      if(NV.mode==='pick'){const sl=NV.pickSlot;pickEnd();if(sl==='skip'){skipAt(p);return}applyPick(sl,p);const i=NV.pts.indexOf(p);if(i>=0)nameLater(i);return}
      if(NV.mode==='home'){await setHome({lat:p.lat,lon:p.lon,name:'Dom'});NV.mode='add';toast('Dom zapisany');return}
      tapMenu(e.latlng)});
    NV.map.on('moveend',()=>{if(NV.poiOn)loadPoi()});drawMarkers();if(NV.data.current){const r=NV.data.routes.find(x=>x.id===NV.data.current);if(r&&!NV.pts.length)try{showRoute(await J('api/nav/route?id='+r.id))}catch(e){}}}catch(e){mapFail(div,'Nie udało się uruchomić mapy')}}
async function skipAt(r){r.name='zaznaczone miejsce';addSkip(r);
  try{const j=await J('api/nav/search?q='+encodeURIComponent(r.lat.toFixed(4)+' '+r.lon.toFixed(4)));const f=j.results&&j.results[0];const sp=NV.skip[NV.skip.length-1];if(f&&sp&&sp.lat===r.lat){sp.name=(f.name||f.label||'').slice(0,40);if(['city','town','village'].includes(f.type)||f.extent)sp.r=skipRadius(Object.assign({},f,{lat:sp.lat}));renderSkip()}}catch(x){}}
async function nameLater(i){try{const p=NV.pts[i];const j=await J('api/nav/search?q='+encodeURIComponent(p.lat.toFixed(4)+' '+p.lon.toFixed(4)));if(j.results&&j.results[0]&&NV.pts[i]===p){p.name=j.results[0].label||j.results[0].name;renderPts()}}catch(e){}}
// pinezki: start (zielona), przystanki z numerem (niebieskie), cel z flagą (czerwona) – bez etykiet, które się ucinały
function pinIcon(kind,txt){const col=kind==='s'?'#2f9e44':kind==='c'?'#e03131':'#1c6ef2';
  const inner=kind==='c'?'<path d="M11.5 7.5v13M11.5 8h8l-2.2 3 2.2 3h-8" fill="#fff" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>':kind==='s'?'<circle cx="15" cy="14" r="5" fill="#fff"/>':'<text x="15" y="18.5" text-anchor="middle" font-size="13" font-weight="700" fill="#fff" font-family="system-ui,sans-serif">'+txt+'</text>';
  return L.divIcon({className:'npin',html:'<svg viewBox="0 0 30 40" width="30" height="40"><path d="M15 38.5C15 38.5 2.5 23.5 2.5 14a12.5 12.5 0 0 1 25 0c0 9.5-12.5 24.5-12.5 24.5z" fill="'+col+'" stroke="#fff" stroke-width="2"/>'+inner+'</svg>',iconSize:[30,40],iconAnchor:[15,39],tooltipAnchor:[0,-36]})}
function drawMarkers(){if(!NV.map)return;drawLegs();for(const m of NV.mk)m.remove();NV.mk=[];const N=NV.pts.length;NV.pts.forEach((p,i)=>{const last=i===N-1&&i>0;const kind=i===0?'s':last&&!NV.loop?'c':'v';
  const m=L.marker([p.lat,p.lon],{draggable:!NV.locked,title:p.name||'',icon:pinIcon(kind,String(i)),zIndexOffset:kind==='c'?500:kind==='s'?400:300}).addTo(NV.map);
  m.bindTooltip((i===0?'Start':last?'Cel':'Przystanek '+i)+(p.name?': '+p.name:''),{direction:'top'});
  m.on('dragend',()=>{const ll=m.getLatLng();NV.pts[i]={lat:ll.lat,lon:ll.lng,name:''};renderPts();nameLater(i);autoPlan()});NV.mk.push(m)})}
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
function showRoute(r){clearPlan();if(!NV.map||!r.pts)return;const ll=r.pts.map(p=>[p[0],p[1]]);const l=(r.legs&&r.legs.length>1?legLine(r,ll).setStyle({opacity:.9,weight:5}):L.polyline(ll,{color:VCOL[r.variant]||'#3d8bfd',weight:5,opacity:.85})).addTo(NV.map);NV.lines.push(l);fitRoute(l.getBounds());if(r.id)alongFor('id='+r.id,r.name||'trasa',ll);
  if(r.waypoints)for(const w of r.waypoints){if(!w.name||w.name==='cel'||w.name==='start')continue}NV.shown=r.id}
async function togglePoi(){NV.poiOn=!NV.poiOn;P.leg.hidden=!NV.poiOn;P.poiBtn.textContent=NV.poiOn?'Ukryj POI':'Pokaż POI z mapy (fotoradary, stacje, widoki)';if(NV.poiOn)await loadPoi();else if(NV.poi){NV.poi.remove();NV.poi=null}}
async function loadPoi(){if(!NV.map)return;const b=NV.map.getBounds();if(NV.map.getZoom()<9){if(NV.poi)NV.poi.clearLayers();P.legHint.textContent='przybliż mapę, żeby zobaczyć punkty';return}P.legHint.textContent='';
  try{const j=await J('api/nav/poi?bbox='+[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].map(x=>x.toFixed(4)).join(','));if(j.too_big)P.legHint.textContent='przybliż mapę, żeby zobaczyć punkty';else if(j.points.length>=400)P.legHint.textContent='pokazano część punktów – przybliż, żeby zobaczyć wszystkie';if(!NV.poi)NV.poi=L.layerGroup().addTo(NV.map);NV.poi.clearLayers();
    for(const p of j.points){const k=KIND[p.kind]||['punkt','#888'];const m=L.circleMarker([p.lat,p.lon],{radius:6,color:'#fff',weight:1.5,fillColor:k[1],fillOpacity:.95}).bindPopup(popupHtml(p,k)+'<br><a href="#" data-add="1">dodaj jako punkt trasy</a>');
      m.on('popupopen',e=>{const a=e.popup.getElement().querySelector('[data-add]');if(a)a.onclick=ev=>{ev.preventDefault();addPt({lat:p.lat,lon:p.lon,name:p.name||k[0]});m.closePopup()}});stationPrice(m,p);NV.poi.addLayer(m)}}catch(e){}}

/* ---- POI: wspólne */
const esc=t=>String(t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// ceny Pb95 stacji (1.5.34): Google przez dodatek, pamięć 1 h; bez klucza lub bez ceny – po cichu nic
async function fuelPrices(pts){try{const j=await post('api/nav/fuel_prices',{places:pts.slice(0,6).map(p=>({lat:p.lat,lon:p.lon,name:p.name||''}))});return j.prices||[]}catch(e){return[]}}
function popupHtml(p,k){k=k||KIND[p.kind]||['punkt','#888'];return '<b>'+esc(p.name||k[0])+'</b>'+(p.name?'<br>'+esc(k[0]):'')+(p.limit?' · '+p.limit+' km/h':'')}
const kmTxt=x=>(x<10?x.toFixed(1):Math.round(x))+' km';
function nearIdx(ll,lat,lon){let b=1e18,bi=0;for(let i=0;i<ll.length;i++){const a=ll[i],dy=a[0]-lat,dx=(a[1]-lon)*0.64,d=dy*dy+dx*dx;if(d<b){b=d;bi=i}}return bi}
function insertWaypoint(p,ll){if(NV.pts.length<2){addPt(p);return}const a=NV.pts.slice();const last=a.pop();const k=nearIdx(ll,p.lat,p.lon);let at=a.length;for(let i=1;i<a.length;i++){if(nearIdx(ll,a[i].lat,a[i].lon)>k){at=i;break}}a.splice(at,0,p);a.push(last);setPts(a);autoPlan()}
function stationPrice(m,p){if(p.kind!==10)return;m.on('popupopen',async e=>{const box=e.popup.getElement();const c=box&&box.querySelector('.leaflet-popup-content');if(!c)return;
  const show=()=>{if(p._price&&!c.querySelector('.fprice')){const d=el('div','fprice');d.append('⛽ Pb95 ');d.append(el('b',null,p._price.text));c.append(d)}};
  if(p._price===undefined){p._price=null;const r=await fuelPrices([p]);p._price=r[0]||null}show()})}
function poiMarker(layer,p,extra){const k=KIND[p.kind]||['punkt','#888'];const m=L.circleMarker([p.lat,p.lon],{radius:8,color:'#fff',weight:2,fillColor:k[1],fillOpacity:1}).bindPopup(popupHtml(p,k)+(extra?'<br>'+extra:''));stationPrice(m,p);layer.addLayer(m);return m}
// lista POI: wiersze z nazwą, odległością i przyciskami
function poiRows(box,points,opt){box.textContent='';if(!points.length){box.append(el('p','mut',opt.empty));return}
  for(const p of points){const k=KIND[p.kind]||['punkt','#888'];const r=el('div','npo');const dot=el('i');dot.style.background=k[1];const tx=el('div','tx');tx.append(el('span',null,p.name||k[0]));
    tx.append(el('small',null,(p.name?k[0]+' · ':'')+opt.dist(p)+(p.off_m!==null&&p.off_m!==undefined?' · '+(p.off_m<1000?p.off_m+' m':(p.off_m/1000).toFixed(1)+' km')+' od trasy':'')));
    const sh=el('button',null,'Pokaż');sh.onclick=()=>{if(!NV.map)return;sheet('mid');NV.map.setView([p.lat,p.lon],15);if(p._m)p._m.openPopup()};
    r.append(dot,tx,sh);for(const b of opt.buttons(p))r.append(b);box.append(r);p._row=tx}
  const st=points.filter(p=>p.kind===10).slice(0,6);
  if(st.length)fuelPrices(st).then(pr=>st.forEach((p,i)=>{const x=pr[i];if(x&&p._row)p._row.append(el('small','fprice','⛽ Pb95 '+x.text))}))}

/* ---- po drodze: POI wzdłuż wybranej trasy */
async function alongFor(q,label,ll){if(!P.along)return;NV.alongQ=q;NV.alongLL=ll;NV.alongLabel=label;if(NV.alongCat===undefined)NV.alongCat=0;P.along.hidden=false;renderAlong()}
async function renderAlong(){const A=P.along;A.textContent='';A.append(el('h2',null,'Po drodze: '+NV.alongLabel));
  const ch=el('div','chips');CATS.forEach((c,i)=>{const b=el('span','chip'+(i===NV.alongCat?' on':''),c[0]);b.onclick=()=>{NV.alongCat=i;renderAlong()};ch.append(b)});A.append(ch);
  const box=el('div','nlist');box.append(el('p','mut','szukanie...'));A.append(box);
  try{const j=await J('api/nav/along?'+NV.alongQ+'&kinds='+CATS[NV.alongCat][1]+'&max=2000');if(NV.alongL)NV.alongL.remove();NV.alongL=L.layerGroup().addTo(NV.map);
    for(const p of j.points)p._m=poiMarker(NV.alongL,p,'km '+p.km+' trasy');
    poiRows(box,j.points,{empty:j.no_map?'Brak mapy w dodatku – kliknij „Pobierz mapę z kontenera” na górze.':'Nic w tej kategorii do 2 km od trasy.',dist:p=>'km '+p.km+' trasy',
      buttons:p=>{const b=el('button',null,'Dodaj');b.title='dodaj jako punkt po drodze (potem policz trasy jeszcze raz)';b.onclick=()=>{insertWaypoint({lat:p.lat,lon:p.lon,name:p.name||(KIND[p.kind]||['punkt'])[0]},NV.alongLL||[]);toast('„'+(p.name||'punkt')+'” dodany jako przystanek')};return [b]}})}
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
  try{const j=await J('api/nav/nearby?'+q);T.last=j;if(P.trip){const p=j.pos;P.trip.hidden=!(p&&p.src==='ekran'&&p.age_s<1800&&((p.speed||0)>=5||p.home_m>2000))}
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
async function plan(){const vars=Object.keys(P.var).filter(v=>P.var[v]);const rt=NV.loop?(P.rt.value?+P.rt.value:(NV.rt&&NV.rt.km)||null):null;const rtm=NV.loop&&!P.rt.value&&NV.rt&&NV.rt.min||null;
  if(NV.loop&&!rt&&!rtm){msg(P.msg,'wybierz długość pętli','bad');return}
  if(!NV.pts.length){msg(P.msg,'wybierz start','bad');openSearch('start');return}if(NV.pts.length<2&&!rt&&!rtm){openSearch('cel');return}if(!vars.length){msg(P.msg,'zaznacz choć jeden wariant','bad');return}
  if(!NV.data.engine){msg(P.msg,'brak adresu silnika tras – wpisz go w Ustawienia → Ustawienia nawigacji (albo wczytaj GPX)','bad');return}
  const dv=NV.data.settings.go_variant||NV.data.settings.default_variant;let legs=null;
  if(!rt&&!rtm&&NV.pts.length>=2&&NV.legs.some(x=>x)){legs=NV.legs.map(x=>x||dv);if(new Set(legs).size<2){if(!vars.includes(legs[0]))vars.push(legs[0]);legs=null}}
  P.go.disabled=true;msg(P.msg,'liczę '+(vars.length+(legs?1:0))+(vars.length+(legs?1:0)===1?' wariant…':' warianty…'),'busy');clearPlan();
  try{const j=await post('api/nav/plan',{points:NV.loop?NV.pts.slice(0,1):NV.pts,variants:vars,legs,avoid:Object.keys(P.av).filter(v=>P.av[v]),name:P.name.value,round_trip_km:rt,round_trip_min:rtm,skip:NV.skip,weather:true});NV.plan=j;msg(P.msg,j.routes.length?'':'żaden wariant się nie policzył',j.routes.length?'':'bad');results(j)}catch(e){msg(P.msg,e.message,'bad')}P.go.disabled=false;renderModeBtn()}
function renderModeBtn(){if(P.go)P.go.textContent=NV.loop?'Policz pętlę':NV.plan?'Przelicz trasę':'Policz trasę'}
/* 1.5.31: „Mój plan” na mapie w kolorach odcinków (kręto pomarańczowo, szybko niebiesko…) z fioletową obwódką.
   Granice odcinków = punkty trasy najbliższe kolejnym przystankom (szukane po kolei, od poprzedniej granicy). */
function legCuts(r,ll){const w=(r.points||[]).slice(1,-1),cut=[0];let from=0;
  for(const q of w){const lat=q.lat!==undefined?q.lat:q[0],lon=q.lon!==undefined?q.lon:q[1];let best=from,bd=Infinity;
    for(let k=from;k<ll.length;k++){const d=(ll[k][0]-lat)**2+((ll[k][1]-lon)*Math.cos(lat*Math.PI/180))**2;if(d<bd){bd=d;best=k}}cut.push(best);from=best}
  cut.push(ll.length-1);return cut}
function legLine(r,ll){const cut=legCuts(r,ll);if(cut.length!==r.legs.length+1)return L.polyline(ll,{color:VCOL.mix,weight:4,opacity:.75});
  const cas=L.polyline(ll,{color:VCOL.mix,weight:8,opacity:.75});const parts=r.legs.map((v,k)=>L.polyline(ll.slice(cut[k],cut[k+1]+1),{color:VCOL[v]||'#888',weight:4,opacity:.9}));
  const g=L.featureGroup([cas].concat(parts));g.setStyle=o=>{cas.setStyle({opacity:o.opacity,weight:(o.weight||4)+4});parts.forEach(x=>x.setStyle({opacity:o.opacity,weight:o.weight}));return g};return g}
function results(j){P.out.textContent='';for(const v of Object.keys(j.errors||{}))P.out.append(el('p','nmsg bad',VN(v)+': '+j.errors[v]));
  const order=j.routes.map((r,i)=>i).sort((a,b)=>(j.routes[b].variant==='mix')-(j.routes[a].variant==='mix'));
  if(j.routes.length)P.out.append(el('small','mut','Dotknij wariantu, żeby go wybrać. Pogrubiona linia na mapie = wybrany.'));
  const bnds=[];const cards=[];
  j.routes.forEach((r,i)=>{const ll=r.pts.map(p=>[p[0],p[1]]);const l=(r.legs&&r.legs.length>1?legLine(r,ll):L.polyline(ll,{color:VCOL[r.variant]||'#888',weight:4,opacity:.75})).addTo(NV.map);l.on('click',()=>pick(i));NV.lines.push(l);bnds.push(...ll)});
  const pick=i=>{const r=j.routes[i];NV.sel=i;cards.forEach(c=>{const on=c._i===i;c.classList.toggle('on',on);c.style.borderColor=on?(VCOL[j.routes[c._i].variant]||''):'';c.querySelector('.ac').hidden=!on});NV.lines.forEach((x,k)=>x.setStyle({opacity:k===i?1:.35,weight:k===i?7:3}));NV.lines[i].bringToFront();alongFor('token='+j.token+'&variant='+r.variant,VN(r.variant),r.pts.map(p=>[p[0],p[1]]))};
  const seen=[];
  for(const i of order){const r=j.routes[i];const vn=VN(r.variant);
    // 1.5.28: dwa warianty tą samą drogą = jedna karta „Kręto = Bardzo kręto”
    const twin=seen.find(x=>Math.abs(x.r.km-r.km)<0.3&&Math.abs(x.r.min-r.min)<=1);if(twin){twin.t.append(' = '+vn);NV.lines[i].setStyle({opacity:0});continue}
    const d=el('div','ncard');d._i=i;
    const h=el('div','h');const t=el('b');const sw=el('i');sw.style.background=VCOL[r.variant]||'#888';t.append(sw,vn);seen.push({r,t});const tm=el('span','ntm');tm.append(el('b',null,dur(r.min)),el('small',null,r.km+' km'));h.append(t,tm);d.append(h);
    if(r.legs&&r.legs.length){const bar=el('div','lb');const lm=r.leg_m&&r.leg_m.length===r.legs.length?r.leg_m:r.legs.map(()=>1);r.legs.forEach((v,k)=>{const s=el('span');s.style.flex=String(Math.max(1,lm[k]));s.style.background=VCOL[v]||'#888';bar.append(s)});d.append(bar);
      const per={};r.legs.forEach((v,k)=>{per[v]=(per[v]||0)+(r.leg_m?r.leg_m[k]:0)});d.append(el('small','mut',Object.keys(per).map(v=>(SHORT[v]||v)+(r.leg_m?' '+km(per[v]):'')).join(' · ')))}
    const rain=r.weather&&r.weather.length?Math.max(...r.weather.map(w=>w.rain_prob||0)):null;const temps=r.weather&&r.weather.length?r.weather.map(w=>w.temp).filter(x=>x!==null&&x!==undefined):[];
    d.append(el('small','mut',[r.curvy?r.curvy.level+' ('+r.curvy.deg_km+'°/km)':'','fotoradary: '+(r.cameras||[]).length,rain!==null?'deszcz do '+rain+'%':'',temps.length?Math.min(...temps).toFixed(0)+'–'+Math.max(...temps).toFixed(0)+'°C':''].filter(x=>x).join(' · ')));
    const ac=el('div','ac');ac.hidden=true;
    const b=el('button','pri','Wyślij „'+vn+'” na ekran');b.onclick=async ev=>{ev.stopPropagation();b.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:true});msg(P.msg,'trasa „'+s.route.name+'” zapisana; ekran pobierze ją przy najbliższym połączeniu','ok');NV.data=await J('api/nav/routes');routesCard(null)}catch(e){msg(P.msg,e.message,'bad');b.disabled=false}};
    const sv=el('button',null,'Zapisz');sv.title='zapisz bez wysyłania na ekran';sv.onclick=async ev=>{ev.stopPropagation();sv.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});NV.data=await J('api/nav/routes');routesCard(null);msg(P.msg,'trasa „'+s.route.name+'” zapisana w „Moich trasach”','ok')}catch(e){msg(P.msg,e.message,'bad');sv.disabled=false}};
    const g=el('button',null,'GPX');g.title='zapisz i udostępnij plik GPX';g.onclick=async ev=>{ev.stopPropagation();g.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});NV.data=await J('api/nav/routes');routesCard(null);await shareGpx(s.id,s.route.name);msg(P.msg,'trasa „'+s.route.name+'” zapisana (bez wysyłania na ekran)','ok')}catch(e){msg(P.msg,e.message,'bad')}g.disabled=false};
    const dr=el('button',null,'🚗 Jadę (OsmAnd)');dr.title='zapas bez ekranu: zapisz, otwórz w OsmAnd i pilnuj korków po drodze';dr.onclick=async ev=>{ev.stopPropagation();dr.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:false});await startDrive(s.id,s.route.name)}catch(e){msg(P.msg,e.message,'bad')}dr.disabled=false};
    if(NV.data.settings.vehicle==='auto')ac.append(b,dr,sv,g);else ac.append(b,sv,g);d.append(ac);d.onclick=()=>pick(i);cards.push(d);P.out.append(d)}
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
  const dm=el('div','acts ndemo');const db=el('button','nlink','+ trasa demo (22 km) do wypróbowania symulacji');db.title='Przykładowa trasa z rondami, fotoradarem, odcinkowym pomiarem i postojem. Możesz ją puścić w „Symulacji” albo wysłać na ekran.';
  db.onclick=async()=>{db.disabled=true;try{const j=await post('api/nav/demo',{});NV.data=await J('api/nav/routes');routesCard(null);const r=NV.data.routes.find(x=>x.id===j.id);if(r)simulate(r)}catch(e){toast(e.message)}db.disabled=false};dm.append(db);
  if(!d.routes.length){const e=el('div','nempty');e.append(el('b',null,'Brak zapisanych tras'),el('small','mut','Zaplanuj trasę w „Planuj” i dotknij „Zapisz” albo „Wyślij na ekran”.'));RC.append(e,dm);return}
  for(const r of d.routes){const row=el('div','nrt');const tx=el('button','tx nrtb');tx.type='button';tx.title='pokaż na mapie';const t=el('b',null,r.name||('trasa '+r.id));tx.append(t);if(r.id===d.current)tx.append(' ',el('span','cur','na ekranie'));
    tx.append(el('small','mut',r.km+' km · '+dur(r.min)+(r.variant?' · '+VN(r.variant).toLowerCase():'')+' · '+when(r.created)));
    const show=async()=>{try{const full=await J('api/nav/route?id='+r.id);sheet('mid');showRoute(full)}catch(e){toast(e.message)}};tx.onclick=show;
    const a=el('div','acts');a.style.margin='0';const auto=NV.data.settings.vehicle==='auto';
    const setCur=async()=>{try{await post('api/nav/current',{id:r.id===d.current?0:r.id});NV.data=await J('api/nav/routes');routesCard(null);toast(r.id===d.current?'Zdjęto z ekranu':'Ekran pobierze trasę przy najbliższym połączeniu')}catch(e){toast(e.message)}};
    const cu=auto?el('button',null,'🚗 Jadę'):el('button',r.id===d.current?null:'pri',r.id===d.current?'Zdejmij':'Na ekran');cu.type='button';cu.onclick=auto?()=>startDrive(r.id,r.name).catch(e=>toast(e.message)):setCur;
    const mo=ib(ICO.more,'więcej');mo.onclick=()=>actSheet(r.name||('trasa '+r.id),[
      ['Pokaż na mapie',show],auto?['Na ekran / zdejmij z ekranu',setCur]:['Symulacja przejazdu',()=>simulate(r)],['Udostępnij GPX',()=>shareGpx(r.id,r.name).catch(e=>toast(e.message))],
      ['Usuń trasę',async()=>{if(!confirm('Usunąć trasę „'+(r.name||r.id)+'”?'))return;try{await post('api/nav/delete',{id:r.id});NV.data=await J('api/nav/routes');routesCard(null)}catch(e){toast(e.message)}},'warn']]);
    a.append(cu,mo);row.append(tx,a);RC.append(row)}
  RC.append(dm)}
// arkusz akcji (zamiast rzędu pięciu przycisków)
function actSheet(title,items){const o=el('div','npick');const d=el('div');o.append(d);const close=()=>o.remove();o.onclick=e=>{if(e.target===o)close()};d.append(el('h3',null,title));
  for(const [t,f,c] of items){const b=el('button','opt'+(c?' '+c:''),t);b.type='button';b.onclick=()=>{close();f()};d.append(b)}const x=el('button',null,'Anuluj');x.onclick=close;d.append(x);document.body.append(o)}
/* ---- jazda autem z OsmAnd: dodatek pilnuje korków i wysyła powiadomienie z objazdem */
async function startDrive(id,name){const j=await post('api/nav/drive',{id});NV.data.drive=j.drive;renderDrive();
  if(!j.phone)toast('Ustaw telefon w Ustawienia nawigacji → Jazda autem, żeby dodatek znał pozycję.');
  await shareGpx(id,name);msg(P.msg,'„'+name+'” w OsmAnd; pilnuję korków co '+NV.data.settings.traffic_min+' min i dam znać powiadomieniem','ok')}
function renderDrive(){if(!P.drv)return;const d=NV.data.drive;P.drv.hidden=!d;P.drv.textContent='';if(!d)return;
  const tx=el('div','tx');tx.append(el('b',null,'🚗 Trwa jazda w OsmAnd: '+d.name),el('small','mut','Dodatek pilnuje korków i prowadzi do tej trasy. Nowa trasa jej nie zastąpi, dopóki nie dotkniesz „Zakończ jazdę” albo „🚗 Jadę (OsmAnd)” przy nowej.'),el('small','mut',d.status||''));
  const a=el('div','acts');a.style.margin='0';const g=el('button',null,'GPX');g.onclick=()=>{const id=d.rids[d.rids.length-1];shareGpx(id,d.name).catch(e=>alert(e.message))};
  const x=el('button','warn','Zakończ jazdę');x.onclick=async()=>{try{await post('api/nav/drive',{stop:true});NV.data.drive=null;renderDrive()}catch(e){alert(e.message)}};a.append(g,x);P.drv.append(tx,a)}
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
  const k=el('div','card');SIM.card=k;paneTab('saved');const anchor=RC||document.getElementById('v-nav');anchor.after(k);sheet('max');
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
  if(!(await loadLeaflet())){mapFail(md)}
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
function goFav(f){applyPick('cel',{lat:f.lat,lon:f.lon,name:f.name})}
function renderFav(){if(!P.favBox)return;P.favBox.textContent='';const S=NV.data.settings,row=el('div','chips');row.append(el('small','mut nfl','Szybki cel:'));
  if(S.home){const c=el('span','chip','⌂ '+(S.home.name||'Dom'));c.onclick=()=>goFav({lat:S.home.lat,lon:S.home.lon,name:S.home.name||'Dom'});row.append(c)}
  for(const f of favs()){const c=el('span','chip','★ '+f.name);c.title='dodaj do trasy';c.onclick=()=>goFav(f);row.append(c)}
  const ad=el('span','chip nadd',NV.pts.length>=2&&!isFav(NV.pts[NV.pts.length-1])?'☆ zapisz cel':'+ ulubione');ad.title='zapisz miejsce w ulubionych';ad.onclick=()=>{if(NV.pts.length>=2){saveFav(NV.pts[NV.pts.length-1]);return}toast('Wyszukaj miejsce i dotknij ☆ przy wyniku.')};row.append(ad);
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
  const gk=field(k,'Klucz Google Places (ceny paliw na ekranie 5" i w panelu; puste = bez cen)','password',null,'',S.google_key);
  if(S.google_usage){const u=S.google_usage,w=u.n>=u.warn;k.append(el('p',w?'nmsg bad':'mut','Zapytania do Google w tym miesiącu ('+u.month+'): '+u.n+(w?' – to dużo, sprawdź alert budżetu w Google Cloud':' (ostrzegam od '+u.warn+')')))}
  const kp=grp('Planowanie i dom');const kc=grp('Jazda autem z OsmAnd (zapas bez ekranu): korki i objazdy');const ke=grp('Ekran w trasie');k=ke;
  kc.append(el('p','mut','W aucie najpierw „Wyślij na ekran” (ekran 5" ma własny GPS). Gdy ekranu nie ma: po „🚗 Jadę (OsmAnd)” dodatek co tyle minut, ile „Sprawdzanie korków”, patrzy na korki przed telefonem (TomTom). Gdy objazd jest szybszy, przychodzi powiadomienie z nową trasą do otwarcia w OsmAnd.'));
  const pt=field(kc,'Telefon (encja z pozycją; puste = z celu powiadomień: '+(NV.data.phone_entity||'brak')+')','text',null,S.phone_tracker);pt.placeholder='device_tracker.iphone';
  const ca=field(kc,'Powiadom od opóźnienia (min)','number',null,S.car_alert_min);
  const dv=field(kp,'Domyślny wariant (skrót „jedź do…” z iPhone’a)','select',NV.data.variants,S.default_variant);
  const ld=field(k,'Wynik zakrętu na ekranie od pochyłu (°)','number',null,S.lean_popup_deg);
  const tm=field(k,'Sprawdzanie korków co (min)','number',null,S.traffic_min);
  const om=field(k,'Zjazd z trasy od (m)','number',null,S.offroute_m);
  const fk=field(k,'„Jadę po swojemu” po (km) poza trasą','number',null,S.free_km);
  const ge=field(kp,'Brama (ekran 5\": przycisk blisko domu; encja cover/button/switch/lock)','text',null,S.gate_entity||'');ge.placeholder='cover.brama';
  const gr=field(kp,'Garaż (encja cover/button/switch/lock; puste = brak)','text',null,S.garage_entity||'');gr.placeholder='cover.garaz';
  const ce=field(kp,'Kalendarz na ekranie 5" (encja calendar.…; puste = brak)','text',null,S.calendar_entity||'');ce.placeholder='calendar.dom';
  const cs=curvySliders(kp,S);
  const hd=el('div','f');hd.append(el('label',null,'Dom (start, gdy ekran nie podał pozycji)'));SF.home=el('div',null,S.home?(S.home.name+' · '+S.home.lat.toFixed(4)+', '+S.home.lon.toFixed(4)):'nie ustawiony');const ha=el('div','acts');const hb=el('button',null,'Wskaż dom na mapie');hb.onclick=()=>{NV.mode='home';tab('nav');setTimeout(()=>{lockMap(false);toast('Dotknij na mapie miejsca domu.')},800)};
  const hs=el('button',null,'Dom = start z listy punktów');hs.onclick=()=>{if(!NV.pts.length){alert('Najpierw dodaj punkt startu w zakładce Trasy.');return}setHome({lat:NV.pts[0].lat,lon:NV.pts[0].lon,name:NV.pts[0].name||'Dom'})};ha.append(hb,hs);hd.append(SF.home,ha);kp.insertBefore(hd,kp.children[2]||null);const fd=el('div','f');fd.append(el('label',null,'Ulubione miejsca (szkoła, praca...): w zakładce Trasy jako przyciski; skrót iPhone’a rozumie też samą nazwę, np. text=Praca'));SF.fav=el('div');fd.append(SF.fav);kp.insertBefore(fd,hd.nextSibling);renderFavSet();k=k0;
  const a=el('div','acts');const sb=el('button','pri','Zapisz ustawienia');const m=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;const body={engine_url:eu.value,map_url:mu.value,default_variant:dv.value,lean_popup_deg:ld.value,traffic_min:tm.value,offroute_m:om.value,free_km:fk.value,phone_tracker:pt.value.trim(),gate_entity:ge.value.trim(),garage_entity:gr.value.trim(),calendar_entity:ce.value.trim(),car_alert_min:ca.value,avoid:P.av?Object.keys(P.av).filter(v=>P.av[v]):(NV.data.settings.avoid||[]),curvy:cs.curvy(),curvy_levels:cs.levels()};if(tk.value)body.tomtom_key=tk.value;if(gk.value)body.google_key=gk.value;
    try{const s=await post('api/nav/settings',body);NV.data.settings=s;NV.data.engine=!!s.engine_url;msg(m,'zapisano','ok');tk.value='';tk.placeholder=s.tomtom_key?'•••••• (bez zmian)':'';gk.value='';gk.placeholder=s.google_key?'•••••• (bez zmian)':''}catch(e){msg(m,e.message,'bad')}sb.disabled=false};a.append(sb,m);k.append(a);
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
