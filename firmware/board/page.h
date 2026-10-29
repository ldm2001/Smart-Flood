// 관제 화면(HTML·CSS·JS 한 덩어리). 설계서 REV16 의 화면을 옮김
// 옮기며 고친 곳: 설계서 원문에서 잘린 scripts 끝(loaded 블록)을 복원, 없는 키 cfg.z2 를
// cfg.zs[2] 로 정정, PDF 줄바꿈으로 끊긴 문자열과 식을 이음
const char PAGE[] PROGMEM = R"HTML(<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART FLOOD</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#0f1b24;color:#e8f0f4}
main{max-width:760px;margin:auto;padding:14px}h1{font-size:18px;margin:4px 0 10px}
.card{background:#172a37;border-radius:10px;padding:12px;margin-bottom:10px}
.row{display:flex;gap:10px;flex-wrap:wrap}.kv{flex:1 1 120px}.kv span{font-size:12px;color:#9fb6c3;display:block}
.kv b{font-size:20px}.big{font-size:42px!important}
.zone{flex:1 1 200px;border-radius:8px;padding:10px}.zone h3{margin:0 0 4px;font-size:15px}
.s0{background:#1f6f43}.s1{background:#9a7a10}.s2{background:#c35a12}.s3{background:#b3202a}
#route{font-size:17px;font-weight:700;text-align:center}
button{font-size:15px;padding:9px 13px;border:0;border-radius:8px;background:#2d6f9a;color:#fff;margin:3px}
button.stop{background:#b3202a}input{width:72px;font-size:15px;padding:5px;border-radius:6px;border:0}
label{font-size:13px;margin:0 8px 6px 0;display:inline-block}small{color:#9fb6c3}
canvas{width:100%;height:200px;background:#0c161d;border-radius:8px}
table{width:100%;font-size:13px;border-collapse:collapse}td,th{padding:4px;border-bottom:1px solid #2a4252;text-align:left}
a{color:#8fd0ff}
</style></head><body><main>
<h1>SMART FLOOD 침수 예측 관제</h1>
<div class="card"><p id="route">-</p><p id="why" style="color:#ffb3b3;text-align:center;margin:4px 0 0"></p></div>
<div class="card"><div class="row">
<div class="kv"><span>현재 수위</span><b class="big" id="lv">-</b></div>
<div class="kv"><span>상승 속도</span><b id="rate">-</b><span id="rsrc"></span></div>
<div class="kv"><span>예측 +10초 / +20초 / +30초</span><b id="pred">-</b></div>
</div></div>
<div class="card"><canvas id="cv" width="700" height="200"></canvas>
<small>흰 선: 실측 수위 · 점선: 예측 · 가로선: 구역 침수 기준 높이</small></div>
<div class="card"><div class="row" id="zones"></div></div>
<div class="card"><b>예측 선행 시간 (이번 회차)</b>
<table><thead><tr><th>구역</th><th>첫 경보</th><th>실제 침수</th><th>미리 알린 시간</th></tr></thead><tbody id="lead"></tbody>
</table>
<small><a href="/log.csv">이번 회차 기록 CSV 내려받기</a></small></div>
<div class="card"><div class="row">
<div class="kv"><span>펌프</span><b id="pump">-</b></div><div class="kv"><span>모드</span><b id="mode">-</b></div>
<div class="kv"><span>경과</span><b id="el">-</b></div><div class="kv"><span>급수통</span><b id="flt">-</b></div></div>
<button onclick="c('start')">새 실험 + 강우 시작</button><button onclick="c('rain')">강우 재개</button>
<button onclick="c('manual')">펌프 수동 ON</button><button class="stop" onclick="c('stop')">정지</button></div>
<div class="card"><b>기준 높이와 경보 (mm, 어항 바닥 = 0)</b><br>
<label>A 낮은 도로 <input id="z0"></label><label>B 주택 골목 <input id="z1"></label><label>C 높은 광장 <input id="z2"></label>
<label>안전 최대 <input id="maxLevel"></label><br>
<label>주의(초 이내) <input id="cautionEta"></label><label>경계(초 이내) <input id="warningEta"></label><br>
<label>강우 ON(초) <input id="rainOnS"></label><label>강우 OFF(초) <input id="rainOffS"></label><br>
<button onclick="save()">저장</button></div>
<div class="card"><b>보정</b><br>
<small>① 수위: 자로 잰 실제 수위를 넣고 낮은 수위에서 1번, 높은 수위에서 2번. 센서 전압 <span id="mv">-</span> mV</small><br>
<label>실제 수위 <input id="calmm"> mm</label><button onclick="c('cal1','calmm')">보정점 1</button><button onclick="c('cal2','calmm')">보정점 2</button><button onclick="c('calreset')">초기화</button><br>
<small>② 유량: 호스 끝을 계량컵에 넣고 버튼 → 30초 뒤 받은 양 입력. 현재 <span id="flow">-</span> mL/s</small><br>
<button onclick="c('flowtest')">펌프 30초 돌리기</button><label>받은 양 <input id="flowml"> mL</label><button onclick="c('flowset','flowml')">유량 저장</button><br>
<small>③ 수면 면적: 현재 <span id="area">-</span> cm², 이번 회차 추정 <span id="areaEst">-</span> cm²</small> <button onclick="c('areaapply')">추정값 적용</button></div>
</main><script>
const MODES=['정지','수동','강우','유량측정'],ST=['정상','주의','경계','침수'],ZN=['A 낮은 도로','B 주택 골목','C 높은 광장'];
const q=i=>document.getElementById(i);let loaded=false,last=null;
async function c(cmd,id){let u='/api/cmd?c='+cmd;if(id)u+='&v='+encodeURIComponent(q(id).value);await fetch(u);loaded=false;tick()}
async function save(){const k=['z0','z1','z2','maxLevel','cautionEta','warningEta','rainOnS','rainOffS'];
 await fetch('/api/set?'+k.map(x=>x+'='+encodeURIComponent(q(x).value)).join('&'));loaded=false;tick()}
function fs(s){return s<0?'-':Math.round(s)+'초'}
function draw(d,h){const cv=q('cv'),g=cv.getContext('2d'),W=cv.width,H=cv.height;g.clearRect(0,0,W,H);
 const top=Math.max(d.cfg.zs[2]+10,d.level+10),y=v=>H-8-(v/top)*(H-16),n=120,x=i=>i/(n+30)*W;
 g.font='12px sans-serif';d.cfg.zs.forEach((z,i)=>{g.strokeStyle=['#ffb347','#ff7043','#ff4f6d'][i];g.beginPath();g.moveTo(0,y(z));g.lineTo(W,y(z));g.stroke();g.fillStyle=g.strokeStyle;g.fillText(ZN[i]+' '+z+'mm',4,y(z)-3)});
 g.strokeStyle='#fff';g.lineWidth=2;g.beginPath();const off=n-h.length;h.forEach((v,i)=>{i?g.lineTo(x(off+i),y(v)):g.moveTo(x(off+i),y(v))});g.stroke();
 g.setLineDash([5,4]);g.strokeStyle='#8fd0ff';g.beginPath();g.moveTo(x(n-1),y(d.level));g.lineTo(x(n+29),y(d.level+d.rate*30));g.stroke();g.setLineDash([]);g.lineWidth=1}
async function tick(){try{const d=await (await fetch('/api/status')).json();
 q('lv').textContent=d.level.toFixed(0)+' mm';q('rate').textContent=(d.rate*60).toFixed(1)+' mm/분';q('rsrc').textContent=d.rsrc;
 q('pred').textContent=d.pred.map(v=>v.toFixed(0)).join(' / ')+' mm';q('route').textContent=d.fault?'수위센서 이상: 12V와 배선을 확인하세요':d.route;
 q('why').textContent=d.why?('정지 사유: '+d.why):'';
 q('zones').innerHTML=d.zones.map((z,i)=>`<div class="zone s${z.stage}"><h3>${ZN[i]} · ${ST[z.stage]}</h3>기준 ${d.cfg.zs[i]} mm<br>${z.eta==0?'침수됨':(z.eta<0?'상승 없음':'침수까지 '+Math.round(z.eta)+'초')}</div>`).join('');
 q('lead').innerHTML=d.zones.map((z,i)=>`<tr><td>${ZN[i]}</td><td>${fs(z.alertT)}</td><td>${fs(z.floodT)}</td><td>${z.alertT>=0&&z.floodT>=0?Math.round(z.floodT-z.alertT)+'초 전':'-'}</td></tr>`).join('');
 q('pump').textContent=d.pump?'ON':'OFF';q('mode').textContent=MODES[d.mode];q('el').textContent=Math.round(d.elapsed)+'초';
 q('flt').textContent=d.floatLow?'물 부족':'정상';q('mv').textContent=d.mv.toFixed(0);q('flow').textContent=d.cfg.flow.toFixed(1);
 q('area').textContent=d.cfg.area.toFixed(0);q('areaEst').textContent=d.areaEst>0?d.areaEst.toFixed(0):'-';
 if(!loaded){['maxLevel','cautionEta','warningEta','rainOnS','rainOffS'].forEach(k=>q(k).value=d.cfg[k]);d.cfg.zs.forEach((z,i)=>q('z'+i).value=z);loaded=true}
 const h=await (await fetch('/api/hist')).json();draw(d,h);
}catch(e){q('route').textContent='ESP32 연결 끊김'}}
setInterval(tick,1000);tick();
</script></body></html>)HTML";
