/* Zakładka „Nawigacja” strony dodatku NT1100 Jazdy.
   Ładowany po index.html; korzysta z jego pomocników (el, api, fmt, loadLeaflet, isHA, tab, detail).
   Na stronie skrzynki ten plik nie jest serwowany (404) i zakładka się nie pojawia. */
(function(){
'use strict';
const NV={data:null,map:null,pts:[],mk:[],lines:[],plan:null,sel:null,mode:'add',poi:null,poiOn:false,shown:null,ready:false};
const VCOL={szybko:'#3d8bfd',lekko:'#40c057',kreto:'#f76707',bardzo:'#e03131'};
const AVN={gruntowe:'drogi gruntowe',platne:'drogi płatne',autostrady:'autostrady',promy:'promy'};
const KIND={1:['fotoradar','#e03131'],2:['odcinkowy pomiar – początek','#e03131'],3:['odcinkowy pomiar – koniec','#e03131'],10:['stacja paliw','#1c7ed6'],11:['restauracja','#f08c00'],12:['kawiarnia','#f08c00'],13:['punkt widokowy','#2f9e44'],14:['przełęcz','#2f9e44'],15:['nocleg','#7950f2'],16:['ładowarka','#1c7ed6'],17:['sklep/serwis moto','#7950f2'],18:['miejsce piknikowe','#2f9e44']};
const css=document.createElement('style');
css.textContent='#navmap{height:420px;border-radius:10px;background:var(--card2)}#navmap.add{cursor:crosshair}'+
'.npt{display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}.npt:last-child{border:0}.npt .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.npt .lb{flex:0 0 58px;font-size:12px;color:var(--mut)}.npt button{padding:4px 8px;font-size:13px}'+
'.nsr{position:relative}.nsr ul{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--card);max-height:220px;overflow:auto}.nsr li{padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--line)}.nsr li:hover{background:var(--card2)}.nsr li small{display:block}'+
'.chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.chip{font-size:13px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--card2);cursor:pointer}.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}'+
'.nres{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:10px;margin:6px 0;cursor:pointer}.nres.on{border-color:var(--acc)}.nres .sw{width:12px;height:12px;border-radius:50%;flex:0 0 12px}.nres .tx{flex:1;min-width:0}.nres small{display:block}'+
'.nrt{display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)}.nrt:last-child{border:0}.nrt .tx{flex:1;min-width:0}.nrt small{display:block}.nrt .cur{font-size:11px;padding:2px 7px;border-radius:8px;background:var(--ok);color:#fff}'+
'.nrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.nrow input{flex:1;min-width:160px;padding:9px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card2)}'+
'.nmsg{margin:6px 0;font-size:14px}.nmsg.bad{color:var(--bad)}.nmsg.ok{color:var(--ok)}.ndev{font-size:13px;color:var(--mut)}';
document.head.append(css);
const msg=(e,t,c)=>{e.className='nmsg'+(c?' '+c:'');e.textContent=t||''};
const km=m=>(m/1000).toFixed(m<10000?1:0)+' km';
const when=t=>t?new Date(t*1000).toLocaleString('pl-PL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'–';
const ago=t=>{if(!t)return 'nigdy';const s=Math.max(0,Date.now()/1000-t);if(s<90)return 'przed chwilą';if(s<3600)return Math.round(s/60)+' min temu';if(s<86400)return Math.round(s/3600)+' h temu';return Math.round(s/86400)+' dni temu'};
async function J(url,o){const r=await (o?api(url,o):fetch(url));let j=null;try{j=await r.json()}catch(e){}if(!r.ok)throw new Error((j&&j.error)||('błąd '+r.status));return j}
const post=(url,body)=>J(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});

/* ---- zakładka */
function inject(){
  const tabs=document.querySelector('nav.tabs');const ref=document.getElementById('t-stats');if(!tabs||!ref||document.getElementById('t-nav'))return;
  const b=el('button');b.id='t-nav';b.hidden=true;b.onclick=()=>tab('nav');
  b.innerHTML='<svg viewBox="0 0 24 24"><path d="M12 2l7 19-7-4-7 4z"/></svg>Nawigacja';ref.after(b);
  const sec=el('section');sec.id='v-nav';sec.hidden=true;document.getElementById('v-stats').after(sec);
  const t0=window.tab;window.tab=function(v){if(v==='nav'){if(STOP)STOP();for(const k of['rides','stats','scan','state','set','nav']){const s=document.getElementById('v-'+k),t=document.getElementById('t-'+k);if(s)s.hidden=k!==v;if(t)t.classList.toggle('on',k===v)}scrollTo(0,0);navView();return}
    const s=document.getElementById('v-nav'),t=document.getElementById('t-nav');if(s)s.hidden=true;if(t)t.classList.remove('on');return t0(v)};
  const d0=window.detail;window.detail=async function(r){await d0(r);try{await planCard(r)}catch(e){}};
}
async function probe(){for(let i=0;i<40&&!DATA;i++)await new Promise(r=>setTimeout(r,250));if(!isHA())return;try{const r=await fetch('api/nav/routes');if(!r.ok)return;NV.data=await r.json()}catch(e){return}document.getElementById('t-nav').hidden=false;NV.ready=true}

/* ---- widok */
async function navView(){const V=document.getElementById('v-nav');V.textContent='';V.append(el('p','mut','wczytywanie...'));
  try{NV.data=await J('api/nav/routes')}catch(e){V.textContent='';V.append(el('p','bad-msg','Nie udało się wczytać nawigacji: '+e.message));return}
  V.textContent='';statusCard(V);plannerCard(V);routesCard(V);settingsCard(V);
  const S=NV.data.settings;if(!NV.pts.length){const st=NV.data.screen,fresh=st&&st.t&&Date.now()/1000-st.t<3*3600;if(fresh)setPts([{lat:st.lat,lon:st.lon,name:'pozycja motocykla'}]);else if(S.home)setPts([{lat:S.home.lat,lon:S.home.lon,name:S.home.name||'Dom'}])}
  await initMap();}

function statusCard(V){const d=NV.data,k=el('div','card');k.append(el('b',null,'Ekran i mapa'));
  const add=(lv,t,n)=>{const r=el('div','row');const a=el('span');const dot=el('span','dot'+(lv?' '+lv:''));a.append(dot,' ',t);r.append(a,el('small',null,n||''));k.append(r)};
  const s=d.screen;if(s&&s.t){const fresh=Date.now()/1000-s.t<600;add(fresh?'ok':'',"Ekran: "+(fresh?'połączony':'ostatnio '+ago(s.t)),(s.fw?'wersja '+s.fw+' · ':'')+(s.battery!==undefined?'bateria '+s.battery+'% · ':'')+(s.map?'mapa '+s.map:''))}else add('','Ekran: jeszcze się nie zgłosił','klucz jak w skrzynce (zakładka Ustawienia)');
  const m=d.map;if(m.available)add('ok','Mapa na kartę: '+m.files+' plików, '+m.mb+' MB','zbudowana '+(m.built||'?')+(m.sync&&m.sync.t?' · sprawdzono '+ago(m.sync.t):''));else add('warn','Mapa na kartę: brak',m.source_url?'pobierz z kontenera (przycisk niżej)':'podaj adres kontenera w ustawieniach niżej');
  add(d.engine?'ok':'warn','Silnik tras: '+(d.engine?'skonfigurowany':'brak adresu'),d.engine?d.settings.engine_url:'bez niego działa tylko GPX i trasy proste');
  add(d.settings.tomtom_key?'ok':'','Korki: '+(d.settings.tomtom_key?'włączone (TomTom)':'wyłączone'),d.settings.tomtom_key?'':'klucz TomTom w ustawieniach niżej');
  const a=el('div','acts');const sb=el('button',null,'Pobierz mapę z kontenera');const sm=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;msg(sm,'sprawdzanie i pobieranie... (może potrwać kilka minut)');try{const j=await post('api/nav/map/sync',{});msg(sm,j.ok?(j.changed?'pobrano '+j.files+' plików, mapa z '+j.built:'mapa aktualna ('+j.built+')'):j.error,j.ok?'ok':'bad')}catch(e){msg(sm,e.message,'bad')}sb.disabled=false};a.append(sb,sm);k.append(a);V.append(k)}

/* ---- planer */
let P={};
function plannerCard(V){const k=el('div','card');k.append(el('b',null,'Zaplanuj trasę'));V.append(k);
  P.list=el('div');k.append(P.list);
  const sr=el('div','nsr');const row=el('div','nrow');P.q=el('input');P.q.placeholder='Miejsce, adres, link z Map Google/Apple albo „50.06, 19.94”';const sb=el('button',null,'Dodaj');row.append(P.q,sb);P.res=el('ul');P.res.hidden=true;sr.append(row,P.res);k.append(sr);
  P.q.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search()}};sb.onclick=search;
  const quick=el('div','acts');const b1=el('button',null,'Start: pozycja motocykla');b1.onclick=()=>{const s=NV.data.screen;if(!(s&&s.t)){alert('Ekran jeszcze nie przysłał pozycji.');return}setStart({lat:s.lat,lon:s.lon,name:'pozycja motocykla'})};
  const b2=el('button',null,'Start: dom');b2.onclick=()=>{const h=NV.data.settings.home;if(!h){alert('Ustaw dom w ustawieniach nawigacji niżej.');return}setStart({lat:h.lat,lon:h.lon,name:h.name||'Dom'})};
  const b3=el('button',null,'Wyczyść');b3.onclick=()=>{setPts([]);clearPlan()};quick.append(b1,b2,b3);k.append(quick);
  k.append(el('p','mut','Kliknięcie na mapie dodaje punkt na koniec; punkty można przeciągać. Pierwszy punkt to start, ostatni to cel, pozostałe to punkty po drodze.'));
  const mapDiv=el('div');mapDiv.id='navmap';k.append(mapDiv);
  const mo=el('div','acts');P.poiBtn=el('button',null,'Pokaż POI z mapy (fotoradary, stacje, widoki)');P.poiBtn.onclick=togglePoi;mo.append(P.poiBtn);k.append(mo);
  const S=NV.data.settings;
  k.append(el('h2',null,'Jak jechać'));
  P.var={};const vc=el('div','chips');for(const [v,t] of NV.data.variants){const c=el('span','chip on',t);c.onclick=()=>{c.classList.toggle('on');P.var[v]=c.classList.contains('on')};P.var[v]=true;vc.append(c)}k.append(el('small',null,'Warianty do policzenia (porównasz je obok siebie):'),vc);
  P.av={};const ac=el('div','chips');for(const v of NV.data.avoid_all){const on=(S.avoid||[]).includes(v);const c=el('span','chip'+(on?' on':''),'omijaj: '+AVN[v]);c.onclick=()=>{c.classList.toggle('on');P.av[v]=c.classList.contains('on')};P.av[v]=on;ac.append(c)}k.append(ac);
  const r2=el('div','nrow');P.rt=el('input');P.rt.type='number';P.rt.placeholder='trasa okrężna: ile km (puste = zwykła)';P.rt.min=10;P.rt.max=1500;P.name=el('input');P.name.placeholder='nazwa trasy (opcjonalnie)';P.name.maxLength=40;r2.append(P.rt,P.name);k.append(r2);
  const a=el('div','acts');P.go=el('button','pri','Policz trasy');P.go.onclick=plan;P.msg=el('span','nmsg');a.append(P.go,P.msg);k.append(a);
  P.out=el('div');k.append(P.out);
  k.append(el('h2',null,'Plik GPX'));const g=el('div','acts');const f=el('input');f.type='file';f.accept='.gpx,application/gpx+xml';f.hidden=true;const gb=el('button',null,'Wczytaj GPX (np. z Kurvigera) i wyślij na ekran');const gm=el('span','nmsg');gb.onclick=()=>f.click();
  f.onchange=async()=>{const file=f.files[0];if(!file)return;gb.disabled=true;msg(gm,'wczytywanie...');try{const body=await file.arrayBuffer();const r=await api('api/nav/gpx?name='+encodeURIComponent(file.name.replace(/\.gpx$/i,'')),{method:'POST',headers:{'Content-Type':'application/gpx+xml'},body});const j=await r.json();if(!r.ok)throw new Error(j.error||'błąd');msg(gm,'trasa „'+j.route.name+'” ('+j.route.km+' km) zapisana i ustawiona na ekran','ok');NV.data=await J('api/nav/routes');routesCard(null);showRoute(j.route)}catch(e){msg(gm,e.message,'bad')}gb.disabled=false;f.value=''};
  g.append(gb,f,gm);k.append(g);renderPts()}

function setPts(p){NV.pts=p;renderPts();drawMarkers()}
function setStart(p){const rest=NV.pts.slice(1);setPts([p].concat(rest))}
function addPt(p){setPts(NV.pts.concat([p]))}
function renderPts(){if(!P.list)return;P.list.textContent='';if(!NV.pts.length){P.list.append(el('p','mut','Brak punktów. Dodaj start i cel: wyszukaj, wklej link albo kliknij na mapie.'));return}
  NV.pts.forEach((p,i)=>{const r=el('div','npt');const lb=i===0?'start':i===NV.pts.length-1?'cel':'punkt '+i;r.append(el('span','lb',lb));const nm=el('span','nm',p.name||(p.lat.toFixed(5)+', '+p.lon.toFixed(5)));nm.title=p.lat.toFixed(5)+', '+p.lon.toFixed(5);r.append(nm);
    const up=el('button',null,'↑');up.disabled=i===0;up.onclick=()=>{const a=NV.pts.slice();[a[i-1],a[i]]=[a[i],a[i-1]];setPts(a)};const dn=el('button',null,'↓');dn.disabled=i===NV.pts.length-1;dn.onclick=()=>{const a=NV.pts.slice();[a[i+1],a[i]]=[a[i],a[i+1]];setPts(a)};const x=el('button',null,'✕');x.onclick=()=>{const a=NV.pts.slice();a.splice(i,1);setPts(a)};r.append(up,dn,x);P.list.append(r)})}
const isLink=t=>/https?:\/\//i.test(t)||/^geo:/i.test(t)||/^-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+$/.test(t.trim());
async function search(){const q=P.q.value.trim();if(!q)return;P.res.hidden=true;P.res.textContent='';P.q.disabled=true;
  try{if(isLink(q)){const j=await J('api/nav/resolve?text='+encodeURIComponent(q));addPt({lat:j.place.lat,lon:j.place.lon,name:j.place.name||q.slice(0,40)});P.q.value='';fitAll()}
    else{const c=NV.pts.length?NV.pts[0]:(NV.map?{lat:NV.map.getCenter().lat,lon:NV.map.getCenter().lng}:{});const j=await J('api/nav/search?q='+encodeURIComponent(q)+(c.lat?'&lat='+c.lat+'&lon='+c.lon:''));
      if(!j.results.length){P.res.append(el('li','mut','nic nie znaleziono'));P.res.hidden=false}else{for(const r of j.results){const li=el('li');li.append(r.name,el('small','mut',r.label));li.onclick=()=>{addPt({lat:r.lat,lon:r.lon,name:r.name});P.res.hidden=true;P.q.value='';fitAll()};P.res.append(li)}P.res.hidden=false}}}
  catch(e){P.res.append(el('li','bad-msg',e.message));P.res.hidden=false}P.q.disabled=false}

/* ---- mapa */
async function initMap(){const div=document.getElementById('navmap');if(!div)return;const ok=await loadLeaflet();if(!ok){div.replaceWith(el('p','mut','Mapa wymaga internetu (OpenStreetMap).'));return}
  try{NV.map=L.map(div,{zoomControl:true});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(NV.map);
    const S=NV.data.settings,c=NV.pts[0]||S.home||{lat:52.1,lon:19.4};NV.map.setView([c.lat,c.lon],NV.pts.length?10:6);div.classList.add('add');
    NV.map.on('click',async e=>{if(NV.mode==='home'){await setHome({lat:e.latlng.lat,lon:e.latlng.lng,name:'Dom'});NV.mode='add';return}addPt({lat:e.latlng.lat,lon:e.latlng.lng,name:''});nameLater(NV.pts.length-1)});
    NV.map.on('moveend',()=>{if(NV.poiOn)loadPoi()});drawMarkers();if(NV.data.current){const r=NV.data.routes.find(x=>x.id===NV.data.current);if(r&&!NV.pts.length)try{showRoute(await J('api/nav/route?id='+r.id))}catch(e){}}}catch(e){div.replaceWith(el('p','mut','Nie udało się uruchomić mapy.'))}}
async function nameLater(i){try{const p=NV.pts[i];const j=await J('api/nav/search?q='+encodeURIComponent(p.lat.toFixed(4)+' '+p.lon.toFixed(4)));if(j.results&&j.results[0]&&NV.pts[i]===p){p.name=j.results[0].label||j.results[0].name;renderPts()}}catch(e){}}
function drawMarkers(){if(!NV.map)return;for(const m of NV.mk)m.remove();NV.mk=[];NV.pts.forEach((p,i)=>{const last=i===NV.pts.length-1;const m=L.marker([p.lat,p.lon],{draggable:true,title:p.name||''}).addTo(NV.map);m.bindTooltip(i===0?'start':last?'cel':String(i),{permanent:true,direction:'top',offset:[-15,-10],className:'lab'});
  m.on('dragend',()=>{const ll=m.getLatLng();NV.pts[i]={lat:ll.lat,lon:ll.lng,name:''};renderPts();nameLater(i)});NV.mk.push(m)})}
function fitAll(){if(!NV.map||!NV.pts.length)return;if(NV.pts.length===1){NV.map.setView([NV.pts[0].lat,NV.pts[0].lon],11);return}NV.map.fitBounds(L.latLngBounds(NV.pts.map(p=>[p.lat,p.lon])),{padding:[30,30]})}
function clearPlan(){for(const l of NV.lines)l.remove();NV.lines=[];NV.plan=null;NV.sel=null;if(P.out)P.out.textContent=''}
function showRoute(r){clearPlan();if(!NV.map||!r.pts)return;const ll=r.pts.map(p=>[p[0],p[1]]);const l=L.polyline(ll,{color:VCOL[r.variant]||'#3d8bfd',weight:5,opacity:.85}).addTo(NV.map);NV.lines.push(l);NV.map.fitBounds(l.getBounds(),{padding:[30,30]});
  if(r.waypoints)for(const w of r.waypoints){if(!w.name||w.name==='cel'||w.name==='start')continue}NV.shown=r.id}
async function togglePoi(){NV.poiOn=!NV.poiOn;P.poiBtn.textContent=NV.poiOn?'Ukryj POI':'Pokaż POI z mapy (fotoradary, stacje, widoki)';if(NV.poiOn)await loadPoi();else if(NV.poi){NV.poi.remove();NV.poi=null}}
async function loadPoi(){if(!NV.map)return;const b=NV.map.getBounds();if(NV.map.getZoom()<9){if(NV.poi)NV.poi.clearLayers();return}
  try{const j=await J('api/nav/poi?bbox='+[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].map(x=>x.toFixed(4)).join(','));if(!NV.poi)NV.poi=L.layerGroup().addTo(NV.map);NV.poi.clearLayers();
    for(const p of j.points){const k=KIND[p.kind]||['punkt','#888'];const m=L.circleMarker([p.lat,p.lon],{radius:6,color:'#fff',weight:1.5,fillColor:k[1],fillOpacity:.95}).bindPopup(k[0]+(p.limit?' · '+p.limit+' km/h':'')+(p.name?'<br>'+p.name:'')+'<br><a href="#" data-add="1">dodaj jako punkt trasy</a>');
      m.on('popupopen',e=>{const a=e.popup.getElement().querySelector('[data-add]');if(a)a.onclick=ev=>{ev.preventDefault();addPt({lat:p.lat,lon:p.lon,name:p.name||k[0]});m.closePopup()}});NV.poi.addLayer(m)}}catch(e){}}

/* ---- liczenie i wysyłka */
async function plan(){const vars=Object.keys(P.var).filter(v=>P.var[v]);const rt=P.rt.value?+P.rt.value:null;
  if(!NV.pts.length){msg(P.msg,'dodaj przynajmniej start i cel','bad');return}if(NV.pts.length<2&&!rt){msg(P.msg,'dodaj cel albo podaj długość trasy okrężnej','bad');return}if(!vars.length){msg(P.msg,'zaznacz choć jeden wariant','bad');return}
  if(!NV.data.engine){msg(P.msg,'brak adresu silnika tras – wpisz go w ustawieniach niżej (albo wczytaj GPX)','bad');return}
  P.go.disabled=true;msg(P.msg,'liczenie '+vars.length+' wariantów...');clearPlan();
  try{const j=await post('api/nav/plan',{points:NV.pts,variants:vars,avoid:Object.keys(P.av).filter(v=>P.av[v]),name:P.name.value,round_trip_km:rt,weather:true});NV.plan=j;msg(P.msg,j.routes.length?'':'żaden wariant się nie policzył',j.routes.length?'':'bad');results(j)}catch(e){msg(P.msg,e.message,'bad')}P.go.disabled=false}
function results(j){P.out.textContent='';for(const v of Object.keys(j.errors||{}))P.out.append(el('p','nmsg bad',(NV.data.variants.find(x=>x[0]===v)||[v,v])[1]+': '+j.errors[v]));
  const bnds=[];j.routes.forEach((r,i)=>{const ll=r.pts.map(p=>[p[0],p[1]]);const l=L.polyline(ll,{color:VCOL[r.variant]||'#888',weight:4,opacity:.75}).addTo(NV.map);NV.lines.push(l);bnds.push(...ll);
    const d=el('div','nres');const sw=el('span','sw');sw.style.background=VCOL[r.variant]||'#888';const tx=el('div','tx');const vn=(NV.data.variants.find(x=>x[0]===r.variant)||[r.variant,r.variant])[1];tx.append(el('b',null,vn+' · '+r.km+' km · '+dur(r.min)));
    const rain=r.weather&&r.weather.length?Math.max(...r.weather.map(w=>w.rain_prob||0)):null;const temps=r.weather&&r.weather.length?r.weather.map(w=>w.temp).filter(x=>x!==null&&x!==undefined):[];
    tx.append(el('small','mut',(r.curvy?r.curvy.level+' ('+r.curvy.deg_km+'°/km)':'')+' · fotoradary: '+(r.cameras||[]).length+' · manewry: '+(r.turns||[]).length+(rain!==null?' · deszcz do '+rain+'%':'')+(temps.length?' · '+Math.min(...temps).toFixed(0)+'–'+Math.max(...temps).toFixed(0)+'°C':'')));
    const b=el('button','pri','Wyślij na ekran');b.onclick=async ev=>{ev.stopPropagation();b.disabled=true;try{const s=await post('api/nav/send',{token:j.token,variant:r.variant,name:P.name.value||r.name,current:true});msg(P.msg,'trasa „'+s.route.name+'” zapisana; ekran pobierze ją przy najbliższym połączeniu','ok');NV.data=await J('api/nav/routes');routesCard(null)}catch(e){msg(P.msg,e.message,'bad');b.disabled=false}};
    d.append(sw,tx,b);d.onclick=()=>{NV.sel=i;document.querySelectorAll('.nres').forEach((x,k)=>x.classList.toggle('on',k===i));NV.lines.forEach((x,k)=>x.setStyle({opacity:k===i?1:.35,weight:k===i?6:3}));NV.lines[i].bringToFront()};P.out.append(d)});
  if(bnds.length)NV.map.fitBounds(L.latLngBounds(bnds),{padding:[30,30]})}

/* ---- zapisane trasy */
let RC=null;
function routesCard(V){if(!RC){RC=el('div','card');V.append(RC)}RC.textContent='';RC.append(el('b',null,'Zapisane trasy'));const d=NV.data;
  if(!d.routes.length){RC.append(el('p','mut','Jeszcze nic nie zaplanowano.'));return}
  for(const r of d.routes){const row=el('div','nrt');const tx=el('div','tx');const t=el('span',null,r.name||('trasa '+r.id));tx.append(t);if(r.id===d.current)tx.append(' ',el('span','cur','na ekranie'));
    tx.append(el('small','mut',r.km+' km · '+dur(r.min)+(r.variant?' · '+((d.variants.find(x=>x[0]===r.variant)||[0,r.variant])[1]).toLowerCase():'')+(r.source?' · '+r.source:'')+' · '+when(r.created)));
    const a=el('div','acts');a.style.margin='0';const sh=el('button',null,'Pokaż');sh.onclick=async()=>{try{const full=await J('api/nav/route?id='+r.id);showRoute(full);document.getElementById('navmap').scrollIntoView({behavior:'smooth',block:'center'})}catch(e){alert(e.message)}};
    const cu=el('button',null,r.id===d.current?'Zdejmij z ekranu':'Na ekran');cu.onclick=async()=>{try{await post('api/nav/current',{id:r.id===d.current?0:r.id});NV.data=await J('api/nav/routes');routesCard(null)}catch(e){alert(e.message)}};
    const gx=el('a');gx.href='api/nav/gpx?id='+r.id;gx.textContent='GPX';gx.className='chip';gx.download='';
    const rm=el('button','warn','Usuń');rm.onclick=async()=>{if(!confirm('Usunąć trasę „'+(r.name||r.id)+'”?'))return;try{await post('api/nav/delete',{id:r.id});NV.data=await J('api/nav/routes');routesCard(null)}catch(e){alert(e.message)}};
    a.append(sh,cu,gx,rm);row.append(tx,a);RC.append(row)}}

/* ---- ustawienia */
async function setHome(h){try{const j=await post('api/nav/home',{home:h});NV.data.settings.home=j.home;if(SF.home)SF.home.textContent=j.home?(j.home.name+' · '+j.home.lat.toFixed(4)+', '+j.home.lon.toFixed(4)):'nie ustawiony';if(NV.map&&j.home){if(NV.homeMk)NV.homeMk.remove();NV.homeMk=L.circleMarker([j.home.lat,j.home.lon],{radius:7,color:'#fff',fillColor:'#7950f2',fillOpacity:1}).bindTooltip('dom').addTo(NV.map)}}catch(e){alert(e.message)}}
let SF={};
function settingsCard(V){const S=NV.data.settings;const k=el('div','card');k.append(el('b',null,'Ustawienia nawigacji'));V.append(k);
  const eu=field(k,'Silnik tras (kontener Proxmox, np. http://192.168.1.50:8989)','url',null,S.engine_url);
  const mu=field(k,'Mapa na kartę (ten sam kontener, np. http://192.168.1.50:8988)','url',null,S.map_url);
  const tk=field(k,'Klucz TomTom (korki; puste = wyłączone)','password',null,'',S.tomtom_key);
  const dv=field(k,'Domyślny wariant (skrót „jedź do…” z iPhone’a)','select',NV.data.variants,S.default_variant);
  const ld=field(k,'Wynik zakrętu na ekranie od pochyłu (°)','number',null,S.lean_popup_deg);
  const tm=field(k,'Sprawdzanie korków co (min)','number',null,S.traffic_min);
  const om=field(k,'Zjazd z trasy od (m)','number',null,S.offroute_m);
  const fk=field(k,'„Jadę po swojemu” po (km) poza trasą','number',null,S.free_km);
  const hd=el('div','f');hd.append(el('label',null,'Dom (start, gdy ekran nie podał pozycji)'));SF.home=el('div',null,S.home?(S.home.name+' · '+S.home.lat.toFixed(4)+', '+S.home.lon.toFixed(4)):'nie ustawiony');const ha=el('div','acts');const hb=el('button',null,'Wskaż dom na mapie');hb.onclick=()=>{NV.mode='home';alert('Kliknij na mapie miejsce domu.');document.getElementById('navmap').scrollIntoView({behavior:'smooth',block:'center'})};
  const hs=el('button',null,'Dom = start z listy punktów');hs.onclick=()=>{if(!NV.pts.length){alert('Najpierw dodaj punkt startu.');return}setHome({lat:NV.pts[0].lat,lon:NV.pts[0].lon,name:NV.pts[0].name||'Dom'})};ha.append(hb,hs);hd.append(SF.home,ha);k.append(hd);
  const a=el('div','acts');const sb=el('button','pri','Zapisz ustawienia');const m=el('span','nmsg');sb.onclick=async()=>{sb.disabled=true;const body={engine_url:eu.value,map_url:mu.value,default_variant:dv.value,lean_popup_deg:ld.value,traffic_min:tm.value,offroute_m:om.value,free_km:fk.value,avoid:Object.keys(P.av).filter(v=>P.av[v])};if(tk.value)body.tomtom_key=tk.value;
    try{const s=await post('api/nav/settings',body);NV.data.settings=s;NV.data.engine=!!s.engine_url;msg(m,'zapisano','ok');tk.value='';tk.placeholder=s.tomtom_key?'•••••• (bez zmian)':''}catch(e){msg(m,e.message,'bad')}sb.disabled=false};a.append(sb,m);k.append(a);
  k.append(el('p','mut','Omijanie zaznaczone wyżej („omijaj: …”) zapisuje się razem z ustawieniami jako domyślne. Skrót iPhone’a „Wyślij na motocykl”: adres z zakładki Ustawienia → Połączenie, ścieżka /api/nav/goto?klucz=KLUCZ&text=LINK.'));
  const SH=NV.data.settings.home;if(SH&&NV.map&&!NV.homeMk)NV.homeMk=L.circleMarker([SH.lat,SH.lon],{radius:7,color:'#fff',fillColor:'#7950f2',fillOpacity:1}).bindTooltip('dom').addTo(NV.map)}

/* ---- zgodność jazdy z planem (w szczegółach jazdy) */
async function planCard(r){if(!isHA())return;const D=document.getElementById('detail');if(!D||D.hidden)return;
  let j;try{j=await J('api/nav/plan?n='+r.n)}catch(e){return}const c=j.plan;if(!c)return;
  const k=el('div','card');k.append(el('b',null,'Trasa planowana'));const pct=c.pct;const lv=pct>=90?'ok':pct>=60?'warn':'bad';const row=el('div','row');const a=el('span');a.append(el('span','dot '+lv),' „'+(c.name||'trasa')+'”: zgodność '+fmt(pct)+'%');row.append(a);k.append(row);
  if(c.deviations&&c.deviations.length){k.append(el('p','ndev','Odstępstwa od planu: '+c.deviations.map(d=>(d.from/1000).toFixed(1)+'–'+(d.to/1000).toFixed(1)+' km').join(', ')))}
  const ev=(c.events||[]).filter(e=>['reroute','skip','detour','offroute','free'].includes(e.what));if(ev.length){const N={reroute:'przeliczenie trasy',skip:'pominięty punkt',detour:'objazd',offroute:'zjazd z trasy',free:'jadę po swojemu'};k.append(el('p','ndev','Zdarzenia na ekranie: '+ev.map(e=>N[e.what]+' '+new Date(e.t*1000).toLocaleTimeString('pl-PL',{hour:'2-digit',minute:'2-digit'})).join(', ')))}
  const md=el('div');md.style.cssText='height:300px;border-radius:10px;background:var(--card2);margin-top:8px';k.append(md);D.append(k);
  if(await loadLeaflet()){try{const map=L.map(md,{zoomControl:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);const pl=L.polyline(c.pts.map(p=>[p[0],p[1]]),{color:'#3d8bfd',weight:5,opacity:.6}).addTo(map);
    try{const tr=parse(await text('dl?view=1&f=/rides/'+pad(r.n)+'.trk')).map(p=>[p[0],p[1]]);if(tr.length)L.polyline(tr,{color:'#e8590c',weight:3,opacity:.9}).addTo(map)}catch(e){}map.fitBounds(pl.getBounds(),{padding:[20,20]});
    const lg=el('div','ndev');lg.textContent='niebieska: plan · pomarańczowa: przejechana';k.append(lg)}catch(e){md.remove()}}else md.remove()}

inject();probe();
})();
