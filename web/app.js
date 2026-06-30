/* PROJECT PHOENIX — Command Center client
   Talks to the GEOS FastAPI backend and renders every page. */
const API = location.origin;
const C = { primary:'#00E5FF', secondary:'#6C63FF', success:'#00FF9C',
            warning:'#FFB800', danger:'#FF4D4D', sub:'#94A3B8' };
const state = { world:null, events:[], result:null, map:null, mapLayers:[], charts:{} };

const $ = (s,el=document)=>el.querySelector(s);
const $$ = (s,el=document)=>[...el.querySelectorAll(s)];
const fmt = (n,d=0)=>Number(n).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});

async function api(path, body){
  const opt = body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {};
  const r = await fetch(API+path, opt);
  if(!r.ok) throw new Error(path+' '+r.status);
  return r.json();
}

/* ---------- navigation ---------- */
function setupNav(){
  $$('.nav-item').forEach(b=>b.onclick=()=>{
    $$('.nav-item').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    const p=b.dataset.page;
    $$('.page').forEach(x=>x.classList.toggle('active', x.dataset.page===p));
    if(p==='map' && state.map) setTimeout(()=>state.map.invalidateSize(),120);
  });
}
function clock(){
  const t=new Date();
  $('#clock').textContent=t.toLocaleTimeString('en-GB');
}

/* ---------- init ---------- */
async function init(){
  setupNav(); clock(); setInterval(clock,1000);
  try{
    state.world = await api('/api/worldmodel');
    const ev = await api('/api/events'); state.events = ev.events;
    buildInjectBar(); buildSwanPicker(); buildChatSuggest();
    initMap(); renderVulnerability();
    $('#chatSend').onclick=sendChat;
    $('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter')sendChat();});
    $('#swanRun').onclick=runBlackSwan;
    $('#demoBtn').onclick=runDemo;
    // default active scenario so every page has data
    await runScenario('hormuz_partial');
    botMsg("PHOENIX online. 8 agents on watch. Ask me what happens if a corridor closes, or inject a scenario from the simulator.");
  }catch(e){ console.error(e); $('#sysStatus').innerHTML='<span class="dot" style="background:var(--danger)"></span> BACKEND OFFLINE'; }
}

/* ---------- Executive ---------- */
function renderExecutive(r){
  const c=r.causal, nb=r.neri_before, na=r.neri_after;
  const kpis=[
    {l:'NERI',v:fmt(na.score,1),d:`${r.neri_delta>0?'+':''}${r.neri_delta}`,cls:r.neri_delta<0?'up':'down',accent:true},
    {l:'Import Dependency',v:'88%',d:'structural',cls:'flat'},
    {l:'SPR Days Cover',v:'9.5',d:'national',cls:'flat'},
    {l:'Brent (USD/bbl)',v:'$'+fmt(c.brent_usd),d:`+${fmt(c.brent_change_pct)}%`,cls:'up'},
    {l:'Supply Shortfall',v:fmt(c.effective_shortfall_pct,1)+'%',d:'effective',cls:'up'},
    {l:'Inflation Δ',v:'+'+fmt(c.inflation_delta_pp,2)+'pp',d:'CPI',cls:'up'},
    {l:'GDP Drag',v:fmt(c.gdp_drag_pp,2)+'pp',d:'annualised',cls:'up'},
    {l:'Power Stress',v:fmt(c.power_sector_stress),d:'index',cls:'up'},
  ];
  $('#kpiGrid').innerHTML=kpis.map(k=>`<div class="kpi ${k.accent?'accent':''}">
    <div class="label">${k.l}</div><div class="value" data-target="${parseFloat(String(k.v).replace(/[^0-9.\-]/g,''))||0}">${k.v}</div>
    <div class="delta ${k.cls}">${k.d}</div></div>`).join('');
  drawNeriGauge(na.score, na.band);
  $('#neriVal').textContent=fmt(na.score,1);
  const bandColor={CRITICAL:C.danger,WATCH:C.warning,STABLE:C.primary,RESILIENT:C.success}[na.band]||C.sub;
  const be=$('#neriBand'); be.textContent=na.band; be.style.color=bandColor;
  $('#neriDrivers').innerHTML='<b>Weakest drivers:</b><br>'+na.drivers.map(d=>'• '+d).join('<br>');
  drawRadar(na.components);
}

function drawNeriGauge(score,band){
  const ctx=$('#neriGauge'); if(state.charts.neri)state.charts.neri.destroy();
  const col={CRITICAL:C.danger,WATCH:C.warning,STABLE:C.primary,RESILIENT:C.success}[band]||C.primary;
  state.charts.neri=new Chart(ctx,{type:'doughnut',
    data:{datasets:[{data:[score,100-score],backgroundColor:[col,'rgba(255,255,255,.06)'],
      borderWidth:0,circumference:180,rotation:270}]},
    options:{cutout:'78%',plugins:{legend:{display:false},tooltip:{enabled:false}},responsive:true,maintainAspectRatio:false}});
}
function drawRadar(comp){
  const ctx=$('#neriRadar'); if(state.charts.radar)state.charts.radar.destroy();
  const labels=Object.keys(comp).map(k=>k.replace(/_/g,' '));
  state.charts.radar=new Chart(ctx,{type:'radar',
    data:{labels,datasets:[{label:'Resilience',data:Object.values(comp),
      backgroundColor:'rgba(0,229,255,.15)',borderColor:C.primary,pointBackgroundColor:C.primary}]},
    options:{scales:{r:{min:0,max:100,grid:{color:'rgba(255,255,255,.08)'},
      angleLines:{color:'rgba(255,255,255,.08)'},pointLabels:{color:C.sub,font:{size:10}},
      ticks:{display:false}}},plugins:{legend:{display:false}}}});
}

/* ---------- Map ---------- */
function initMap(){
  const w=state.world;
  state.map=L.map('map',{zoomControl:true,attributionControl:false}).setView(w.center,3);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:8}).addTo(state.map);
  drawMap();
}
function clearMapLayers(){ state.mapLayers.forEach(l=>state.map.removeLayer(l)); state.mapLayers=[]; }
function drawMap(disrupted={suppliers:[],corridors:[]}){
  if(!state.map) return; clearMapLayers();
  const w=state.world, add=l=>{l.addTo(state.map);state.mapLayers.push(l);};
  // corridors
  w.corridors.forEach(c=>{
    const hi=c.base_risk>0.15 || disrupted.corridors.includes(c.id);
    add(L.polyline(c.waypoints,{color:hi?C.danger:C.sub,weight:hi?4:2,opacity:.8,dashArray:hi?null:'5,6'})
      .bindPopup(`<b>${c.name}</b><br>Base risk ${(c.base_risk*100).toFixed(0)}%`));
  });
  // supplier -> India flow lines
  w.suppliers.forEach(s=>{
    const cut=disrupted.suppliers.includes(s.id);
    add(L.polyline([s.coords,w.center],{color:cut?C.danger:'rgba(0,229,255,.25)',weight:Math.max(1,s.share*12),opacity:cut?.9:.5}));
    add(L.circleMarker(s.coords,{radius:5+s.share*20,color:cut?C.danger:C.primary,fillColor:cut?C.danger:C.primary,fillOpacity:.65,weight:1})
      .bindPopup(`<b>${s.name}</b><br>Share ${(s.share*100).toFixed(0)}%<br>Grade ${s.grade}<br>${s.via_hormuz?'⚠ via Hormuz':'non-Hormuz'}${cut?'<br><b style="color:#FF4D4D">DISRUPTED</b>':''}`));
  });
  w.refineries.forEach(r=>add(L.circleMarker(r.coords,{radius:6,color:C.secondary,fillColor:C.secondary,fillOpacity:.8,weight:1})
    .bindPopup(`<b>${r.name}</b><br>Capacity ${r.capacity} mbpd`)));
  w.reserves.forEach(r=>add(L.circleMarker(r.coords,{radius:7,color:C.success,fillColor:C.success,fillOpacity:.85,weight:1})
    .bindPopup(`<b>SPR ${r.name}</b><br>${r.capacity} mmbbl · ${(r.fill_pct*100).toFixed(0)}% full`)));
}

/* ---------- Scenario ---------- */
function buildInjectBar(){
  $('#injectBar').innerHTML=state.events.map(e=>`<button class="chip" data-id="${e.id}">${e.title}</button>`).join('');
  $$('#injectBar .chip').forEach(b=>b.onclick=()=>runScenario(b.dataset.id));
}
async function runScenario(id){
  $$('#injectBar .chip').forEach(c=>c.classList.toggle('active',c.dataset.id===id));
  $('#agentFeed').innerHTML='<div class="muted"><span class="spin"></span> Orchestrating agent swarm…</div>';
  const r = await api('/api/scenario',{event_id:id,sim_runs:4000});
  state.result=r;
  renderExecutive(r); renderCausal(r); renderDist(r); renderFeed(r);
  renderProcurement(r); renderReserves(r); renderEconomic(r);
  renderGeo(r); renderCascade(r); renderAlerts(r); renderRailRecs(r);
  renderPredictive(r); renderGNN(r);
  const dis = collectDisrupted(r);
  drawMap(dis);
}
function collectDisrupted(r){
  const proc=r.agent_reports.find(a=>a.agent==='procurement_orchestrator');
  const names=(proc&&proc.findings.disrupted_suppliers)||[];
  const ids=state.world.suppliers.filter(s=>names.includes(s.name)).map(s=>s.id);
  const cor=[]; if(r.event.id.includes('hormuz')||r.event.id.includes('war'))cor.push('cor_hormuz');
  if(r.event.id.includes('redsea')||r.event.id.includes('war'))cor.push('cor_redsea');
  return {suppliers:ids,corridors:cor};
}
function renderCausal(r){
  const c=r.causal;
  const cells=[['Effective Shortfall',fmt(c.effective_shortfall_pct,1)+'%',C.danger],
    ['Brent','$'+fmt(c.brent_usd),C.warning],['Retail Fuel','+'+fmt(c.retail_fuel_change_pct,1)+'%',C.warning],
    ['Inflation','+'+fmt(c.inflation_delta_pp,2)+'pp',C.danger],['GDP Drag',fmt(c.gdp_drag_pp,2)+'pp',C.danger],
    ['Risk Premium','+'+fmt(c.risk_premium_pct,1)+'%',C.secondary]];
  $('#causalPanel').innerHTML=cells.map(([k,v,col])=>`<div class="c"><div class="k">${k}</div><div class="v" style="color:${col}">${v}</div></div>`).join('')
    +`<div class="c" style="grid-column:1/3"><div class="k">Causal explanation</div><div class="muted small" style="margin-top:6px;line-height:1.6">${Object.values(c.explanation).join(' ')}</div></div>`;
}
function renderDist(r){
  if(!r.scenario)return; const h=r.scenario.histograms.brent_usd, m=r.scenario.metrics.brent_usd;
  const ctx=$('#distChart'); if(state.charts.dist)state.charts.dist.destroy();
  state.charts.dist=new Chart(ctx,{type:'bar',
    data:{labels:h.bins.map(b=>'$'+Math.round(b)),datasets:[{data:h.counts,backgroundColor:'rgba(0,229,255,.55)',borderRadius:3}]},
    options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:C.sub,maxTicksLimit:8},grid:{display:false}},
      y:{ticks:{color:C.sub},grid:{color:'rgba(255,255,255,.06)'}}}}});
  $('#distMeta').innerHTML=`${fmt(r.scenario.runs)} futures · p5 $${fmt(m.p5)} · p50 <b style="color:#fff">$${fmt(m.p50)}</b> · p95 $${fmt(m.p95)} · worst $${fmt(r.scenario.worst_case_brent)} · P(Brent&gt;$120)=${fmt(r.scenario.prob_brent_above_120*100)}%`;
}
function renderFeed(r){
  $('#agentFeed').innerHTML=r.agent_reports.map((a,i)=>`<div class="row" style="animation-delay:${i*70}ms">
    <div style="flex:1"><div style="display:flex;align-items:center"><span class="agent">⬢ ${a.agent.replace(/_/g,' ').toUpperCase()}</span>
    <span class="conf">${fmt(a.confidence*100)}% conf</span></div>
    <div class="head">${a.headline}</div>
    <div class="recs">${a.recommendations.map(x=>'↳ '+x).join('<br>')}</div></div></div>`).join('')
    +`<div class="muted small" style="text-align:right">Full national response in ${r.total_elapsed_ms} ms</div>`;
}

/* ---------- Procurement ---------- */
function renderProcurement(r){
  const p=r.agent_reports.find(a=>a.agent==='procurement_orchestrator').findings;
  const nash=p.nash_equilibrium;
  $('#procSummary').innerHTML=`<b>Shortfall ${fmt(p.shortfall_share_pct,1)}%</b> of imports · disrupted: ${(p.disrupted_suppliers||[]).join(', ')||'none'} · plan covers <b style="color:${p.coverage_pct>=99?C.success:C.warning}">${fmt(p.coverage_pct,0)}%</b> · est. daily premium $${fmt(p.est_daily_premium_cost_usd/1e6,1)}M`
    +(nash?`<br><span style="color:${C.secondary}">⚖ Cournot–Nash equilibrium clearing price <b>$${fmt(nash.clearing_price_usd)}</b> (+$${fmt(nash.premium_over_baseline_usd)} vs baseline) · converged in ${nash.iterations} iterations</span>`:'');
  const rows=(p.ranked_plan||[]).map(x=>`<tr><td><span class="rank">${x.rank}</span></td><td>${x.supplier}</td>
    <td>${x.grade}</td><td>+${fmt(x.backfill_share_pct,1)}%</td><td>${fmt(x.volume_mbpd,3)} mbpd</td>
    <td>$${fmt(x.spot_premium_usd,1)}</td><td>${x.lead_time_days} d</td><td>${fmt(x.utility_score,3)}</td></tr>`).join('');
  $('#procTable').innerHTML=`<thead><tr><th>#</th><th>Supplier</th><th>Grade</th><th>Backfill</th><th>Volume</th><th>Premium</th><th>Lead</th><th>Utility</th></tr></thead><tbody>${rows||'<tr><td colspan=8 class=muted>No backfill required</td></tr>'}</tbody>`;
}

/* ---------- Reserves ---------- */
function renderReserves(r){
  const rv=r.agent_reports.find(a=>a.agent==='reserve_optimizer').findings;
  $('#reserveTanks').innerHTML=(rv.drawdown_schedule||[]).map(s=>{
    const site=state.world.reserves.find(x=>x.name===s.site)||{fill_pct:.9};
    return `<div class="tank"><div style="font-size:13px">${s.site}</div>
      <div class="glass"><div class="fill" style="height:${site.fill_pct*100}%"></div></div>
      <div class="muted small">${fmt(s.available_mmbbl,1)} mmbbl avail</div>
      <div style="color:${C.primary};font-size:13px;margin-top:4px">↓ ${fmt(s.daily_release_mmbbl,3)} mmbbl/d</div></div>`;
  }).join('');
  const cov=rv.days_cover_under_shock; 
  $('#reserveRecs').innerHTML=r.agent_reports.find(a=>a.agent==='reserve_optimizer').recommendations.map(x=>`<li>↳ ${x}</li>`).join('')
    +`<li>Days of cover under shock: <b style="color:${cov&&cov<30?C.warning:C.success}">${cov===null?'ample':cov+' days'}</b></li>`;
  // DP-optimal drawdown schedule
  const dp=rv.dp_optimal_policy;
  if(state.charts.dp)state.charts.dp.destroy();
  if(dp){
    state.charts.dp=new Chart($('#dpChart'),{type:'line',
      data:{labels:dp.optimal_release_schedule.map((_,i)=>'D'+(i+1)),
        datasets:[{label:'Optimal release (mmbbl/day)',data:dp.optimal_release_schedule,
          borderColor:C.warning,backgroundColor:'rgba(255,184,0,.15)',fill:true,tension:.3,pointRadius:0}]},
      options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:C.sub,maxTicksLimit:10},grid:{display:false}},
        y:{ticks:{color:C.sub},grid:{color:'rgba(255,255,255,.06)'}}}}});
    $('#dpMeta').innerHTML=`Horizon ${dp.horizon_days}d · day-1 release <b style="color:#fff">${fmt(dp.schedule_summary.day1_release_mmbbl,2)}</b> mmbbl · total released ${fmt(dp.schedule_summary.total_released_mmbbl,1)} mmbbl · final reserve ${fmt(dp.final_reserve_mmbbl,1)} mmbbl · unmet gap ${fmt(dp.total_unmet_gap_mmbbl,2)} mmbbl`;
  } else {
    $('#dpMeta').innerHTML='<span class="muted">No drawdown required — procurement covers the shortfall. (DP engages when a residual gap exists, e.g. Black Swan.)</span>';
  }
}

/* ---------- Economic ---------- */
function renderEconomic(r){
  const c=r.causal;
  const k=[['Brent','$'+fmt(c.brent_usd),'+'+fmt(c.brent_change_pct)+'%'],
    ['Retail Fuel','+'+fmt(c.retail_fuel_change_pct,1)+'%','pass-through'],
    ['Inflation','+'+fmt(c.inflation_delta_pp,2)+'pp','CPI'],
    ['GDP Drag',fmt(c.gdp_drag_pp,2)+'pp','annualised']];
  $('#econKpis').innerHTML=k.map(x=>`<div class="kpi"><div class="label">${x[0]}</div><div class="value">${x[1]}</div><div class="delta up">${x[2]}</div></div>`).join('');
  const chain=[['Supply Shortfall',fmt(c.effective_shortfall_pct,1)+'%'],['Brent','$'+fmt(c.brent_usd)],
    ['Retail Fuel','+'+fmt(c.retail_fuel_change_pct,0)+'%'],['Inflation','+'+fmt(c.inflation_delta_pp,2)+'pp'],['GDP',fmt(c.gdp_drag_pp,2)+'pp']];
  $('#econChain').innerHTML=chain.map((n,i)=>`<div class="node"><div class="k">${n[0]}</div><div class="v">${n[1]}</div></div>${i<chain.length-1?'<span class="arrow">→</span>':''}`).join('');
}

/* ---------- Geopolitical ---------- */
function renderGeo(r){
  const g=r.agent_reports.find(a=>a.agent==='geopolitical_intel').findings;
  const s=r.agent_reports.find(a=>a.agent==='sanctions_intel').findings;
  const m=r.agent_reports.find(a=>a.agent==='maritime_intel').findings;
  const k=[['Hormuz Risk',fmt(g.hormuz_risk),C.danger],['Red Sea Risk',fmt(g.redsea_risk),C.warning],
    ['Maritime Threat',fmt(g.maritime_threat),C.danger],['Sanctions Exposure',fmt(s.exposed_import_share_pct)+'%',C.secondary],
    ['Freight Premium','+'+fmt(m.freight_premium_pct,1)+'%',C.warning],['Added Voyage',m.added_voyage_days+' d',C.primary]];
  $('#geoKpis').innerHTML=k.map(x=>`<div class="kpi"><div class="label">${x[0]}</div><div class="value" style="color:${x[2]}">${x[1]}</div></div>`).join('');
  $('#supplierMatrix').innerHTML=Object.entries(g.supplier_stability).map(([n,v])=>{
    const col=v>70?C.success:v>45?C.warning:C.danger;
    return `<div class="cellm"><div class="n">${n}</div><div class="bar"><i style="width:${v}%;background:${col}"></i></div>
      <div class="muted small" style="margin-top:5px">stability ${v}</div></div>`;}).join('');
}

/* ---------- Twin ---------- */
async function renderVulnerability(){
  const v=await api('/api/graph/vulnerability');
  const max=v.vulnerability[0].score||1;
  $('#vulnList').innerHTML=v.vulnerability.map(x=>`<div class="vrow"><span style="width:150px">${x.node}</span>
    <span class="vbar"><i style="width:${(x.score/max)*100}%"></i></span><span class="muted">${fmt(x.score,2)}</span></div>`).join('');
}
function renderCascade(r){
  const ctx=$('#cascadeChart'); if(state.charts.casc)state.charts.casc.destroy();
  const labels=Object.keys(r.cascade), data=Object.values(r.cascade);
  state.charts.casc=new Chart(ctx,{type:'bar',
    data:{labels,datasets:[{data,backgroundColor:data.map(d=>d>50?C.danger:d>25?C.warning:C.primary),borderRadius:4}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.x+'% feedstock at risk'}}},
      scales:{x:{max:100,ticks:{color:C.sub},grid:{color:'rgba(255,255,255,.06)'}},y:{ticks:{color:C.sub,font:{size:11}},grid:{display:false}}}}});
}

/* ---------- Alerts / rail ---------- */
function renderAlerts(r){
  const na=r.neri_after, items=[];
  items.push({cls:na.band==='CRITICAL'?'danger':na.band==='WATCH'?'':'ok',
    t:`NERI ${fmt(na.score,1)} · ${na.band}`,b:`Resilience shifted ${r.neri_delta} pts on "${r.event.title}"`});
  if(r.scenario&&r.scenario.prob_brent_above_120>0.5)
    items.push({cls:'danger',t:'Brent tail risk',b:`P(>$120) = ${fmt(r.scenario.prob_brent_above_120*100)}%`});
  const proc=r.agent_reports.find(a=>a.agent==='procurement_orchestrator').findings;
  items.push({cls:proc.coverage_pct>=99?'ok':'',t:'Procurement plan ready',b:`${fmt(proc.coverage_pct,0)}% of shortfall covered by ${(proc.ranked_plan||[]).length} sources`});
  $('#alerts').innerHTML=items.map(a=>`<div class="a ${a.cls}"><b>${a.t}</b><div class="t">${a.b}</div></div>`).join('');
}
function renderRailRecs(r){
  const acts=(r.decision_brief.top_actions||[]);
  $('#railRecs').innerHTML=(acts.length?acts:[{priority:'LOW',action:'Maintain monitoring',domain:'Ops'}])
    .map(a=>`<div class="r"><b>[${a.priority}] ${a.domain}</b><br>${a.action}</div>`).join('');
}

/* ---------- Predictive Foundation Model + GNN ---------- */
function renderPredictive(r){
  const pa=r.agent_reports.find(a=>a.agent==='predictive_risk'); if(!pa)return;
  const f=pa.findings;
  $('#aucBadge').textContent='AUC '+fmt(f.model_auc,3);
  const rows=(f.corridor_forecast||[]).map(c=>{
    const p=c.disruption_probability*100, col=p>70?C.danger:p>40?C.warning:C.success;
    return `<tr><td>${c.corridor_name}</td>
      <td class="fc-prob" style="color:${col}">${fmt(p)}%</td>
      <td>${fmt(c.lead_time_days,1)} days</td>
      <td class="muted small">${Object.keys(c.top_drivers||{}).join(', ')}</td></tr>`;}).join('');
  $('#forecastTable').innerHTML=`<thead><tr><th>Corridor</th><th>P(disruption)</th><th>Lead Time</th><th>Top Drivers</th></tr></thead><tbody>${rows}</tbody>`;
}
function renderGNN(r){
  const pa=r.agent_reports.find(a=>a.agent==='predictive_risk'); if(!pa)return;
  const f=pa.findings;
  $('#gnnBadge').textContent='mean risk '+fmt(f.gnn_mean_network_risk,1)+'%';
  $('#gnnRanking').innerHTML=(f.gnn_systemic_ranking||[]).map(n=>{
    const col=n.risk>70?C.danger:n.risk>40?C.warning:C.primary;
    return `<div class="cellm"><div class="n">${n.node}</div>
      <div class="bar"><i style="width:${n.risk}%;background:${col}"></i></div>
      <div class="muted small" style="margin-top:5px">risk ${fmt(n.risk,1)}%</div></div>`;}).join('');
}

/* ---------- Auto-play demo mode ---------- */
let demoRunning=false;
function toast(html){
  let t=$('#demoToast'); if(!t){t=document.createElement('div');t.id='demoToast';t.className='demo-toast';document.body.appendChild(t);}
  t.innerHTML=html; t.style.display='block';
}
function hideToast(){const t=$('#demoToast'); if(t)t.style.display='none';}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function gotoPage(p){const b=$(`.nav-item[data-page="${p}"]`); if(b)b.click();}
async function runDemo(){
  if(demoRunning)return; demoRunning=true;
  const btn=$('#demoBtn'); btn.classList.add('running'); btn.textContent='■ DEMO RUNNING';
  const steps=[
    {p:'executive',msg:'<b>PHOENIX</b> baseline — India at NERI ~64 (STABLE). 88% import-dependent, 9.5 days SPR cover.',ms:3200},
    {p:'geopolitical',ev:'hormuz_partial',msg:'⚠ INJECT: <b>Strait of Hormuz partial closure</b> — Foundation Model forecasts 97% disruption, ~2-day lead time.',ms:4200},
    {p:'scenario',msg:'9 agents orchestrate a national response in milliseconds — war-gaming thousands of futures…',ms:4200},
    {p:'twin',msg:'GNN propagates systemic risk — the network reveals single points of failure.',ms:3600},
    {p:'procurement',msg:'Autonomous Procurement Orchestrator generates a ranked backfill plan at the <b>Nash equilibrium</b> clearing price.',ms:4200},
    {p:'reserves',msg:'DP solver computes the <b>optimal SPR drawdown</b> schedule to bridge the gap.',ms:3600},
    {p:'economic',msg:'Economic twin transmits the shock: Brent → fuel → inflation → GDP.',ms:3600},
    {p:'blackswan',msg:'Now the tail: compounding shocks into a <b>Black Swan</b>. This is what resilience planning must survive.',ms:3000},
  ];
  for(const s of steps){
    if(!demoRunning)break;
    gotoPage(s.p); toast(s.msg);
    if(s.ev) await runScenario(s.ev);
    await sleep(s.ms);
  }
  if(demoRunning){
    // black swan finale
    $$('#swanPicker input').forEach(i=>{i.checked=['hormuz_partial','russia_secondary_sanctions','redsea_suspension'].includes(i.value);i.dispatchEvent(new Event('change'));});
    await runBlackSwan(); toast('🦢 <b>Black Swan</b> simulated — PHOENIX delivered a coordinated national response end-to-end. Demo complete.');
    await sleep(4000);
  }
  hideToast(); btn.classList.remove('running'); btn.textContent='▶ RUN DEMO'; demoRunning=false;
}

/* ---------- Copilot ---------- */
function buildChatSuggest(){
  const qs=['What happens if Hormuz closes tomorrow?','How long can India sustain imports?','Which refiners are affected?','What if Russia is sanctioned?'];
  $('#chatSuggest').innerHTML=qs.map(q=>`<span class="s">${q}</span>`).join('');
  $$('#chatSuggest .s').forEach(s=>s.onclick=()=>{$('#chatInput').value=s.textContent;sendChat();});
}
function botMsg(html,meta){ $('#chatLog').insertAdjacentHTML('beforeend',`<div class="msg bot">${html}${meta?`<div class="meta">${meta}</div>`:''}</div>`); $('#chatLog').scrollTop=1e9; }
function userMsg(t){ $('#chatLog').insertAdjacentHTML('beforeend',`<div class="msg user">${t}</div>`); $('#chatLog').scrollTop=1e9; }
async function sendChat(){
  const q=$('#chatInput').value.trim(); if(!q)return; $('#chatInput').value='';
  userMsg(q); botMsg('<span class="spin"></span> reasoning…');
  try{
    const r=await api('/api/copilot',{question:q});
    $('#chatLog').lastChild.remove();
    let html=r.answer;
    if(r.supporting) html+='<br><br>'+Object.entries(r.supporting).slice(0,6).map(([k,v])=>`<span class="muted small">${k.replace(/_/g,' ')}: <b style="color:#fff">${typeof v==='number'?fmt(v,2):v}</b></span>`).join('<br>');
    if(r.top_actions&&r.top_actions.length) html+='<br><br><b>Recommended:</b><br>'+r.top_actions.map(a=>`• [${a.priority}] ${a.action}`).join('<br>');
    botMsg(html, `intent: ${r.intent} · confidence ${fmt((r.confidence||0)*100)}%`);
  }catch(e){ $('#chatLog').lastChild.remove(); botMsg('Backend error — try again.'); }
}

/* ---------- Black Swan ---------- */
function buildSwanPicker(){
  $('#swanPicker').innerHTML=state.events.map(e=>`<label class="swan-opt"><input type="checkbox" value="${e.id}"/> ${e.title}</label>`).join('');
  $$('#swanPicker .swan-opt').forEach(o=>o.querySelector('input').onchange=e=>o.classList.toggle('sel',e.target.checked));
}
async function runBlackSwan(){
  const ids=$$('#swanPicker input:checked').map(i=>i.value);
  if(ids.length<2){ $('#swanResult').innerHTML='<div class="banner">Select at least 2 shocks.</div>'; return; }
  $('#swanResult').innerHTML='<div class="card"><span class="spin"></span> Compounding crises & war-gaming…</div>';
  const r=await api('/api/blackswan',{event_ids:ids,sim_runs:4000});
  const c=r.causal, na=r.neri_after, proc=r.agent_reports.find(a=>a.agent==='procurement_orchestrator').findings;
  $('#swanResult').innerHTML=`<div class="banner" style="border-color:var(--danger);background:rgba(255,77,77,.12)">
    🦢 <b>${r.event.title}</b></div>
    <div class="kpi-grid">
      <div class="kpi accent"><div class="label">NERI</div><div class="value" style="color:${na.band==='CRITICAL'?C.danger:C.warning}">${fmt(na.score,1)}</div><div class="delta up">${r.neri_delta} · ${na.band}</div></div>
      <div class="kpi"><div class="label">Brent</div><div class="value">$${fmt(c.brent_usd)}</div><div class="delta up">+${fmt(c.brent_change_pct)}%</div></div>
      <div class="kpi"><div class="label">Worst-case Brent</div><div class="value" style="color:${C.danger}">$${fmt(r.scenario.worst_case_brent)}</div><div class="delta up">p95 tail</div></div>
      <div class="kpi"><div class="label">Inflation Δ</div><div class="value">+${fmt(c.inflation_delta_pp,2)}pp</div></div>
      <div class="kpi"><div class="label">GDP Drag</div><div class="value" style="color:${C.danger}">${fmt(c.gdp_drag_pp,2)}pp</div></div>
      <div class="kpi"><div class="label">Procurement Coverage</div><div class="value" style="color:${proc.coverage_pct>=99?C.success:C.warning}">${fmt(proc.coverage_pct,0)}%</div></div>
    </div>
    <div class="card"><div class="card-title">RESPONSE — AGENT FEED</div><div class="feed">${r.agent_reports.map(a=>`<div class="row"><div style="flex:1"><span class="agent">⬢ ${a.agent.replace(/_/g,' ').toUpperCase()}</span><div class="head">${a.headline}</div></div></div>`).join('')}</div></div>`;
}

init();
