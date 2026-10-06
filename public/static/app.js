'use strict';
const $ = id => document.getElementById(id);
const state = {start:null,end:null,routes:[],selected:0,watch:null,position:null,navIndex:0,layers:[],helpLayers:[],endpoints:[],marker:null,accuracy:null,requestId:0};
const token = document.querySelector('meta[name="csrf-token"]').content;
let map = null;
if (typeof L !== 'undefined') {
  map = L.map('map',{zoomControl:false}).setView([22.5,79],5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  L.control.zoom({position:'topleft'}).addTo(map);
  map.on('click',event=>{ $('report-lat').value=event.latlng.lat.toFixed(6);$('report-lng').value=event.latlng.lng.toFixed(6); });
} else $('map-failure').hidden=false;
async function api(path,options={}) {
  const response=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':token,...options.headers}});
  const result=await response.json().catch(()=>({error:'Server returned an unexpected response.'}));
  if(!response.ok) throw new Error(result.error||'Request failed. Please retry.');
  return result;
}
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function status(message,error=false){$('status').textContent=message;$('status').className=error?'error':'';}
function km(distance){return distance<1000?`${Math.round(distance)} m`:`${(distance/1000).toFixed(1)} km`;}
function minutes(seconds){const m=Math.max(1,Math.round(seconds/60));return m<60?`${m} min`:`${Math.floor(m/60)} h ${m%60} min`;}
function flat(route){return route.geometry.type==='LineString'?route.geometry.coordinates:route.geometry.coordinates.flat();}
function choosePoint(id,place){state[id]=place;$(id).value=place.label;$(id+'-options').replaceChildren();invalidateJourney();}
function invalidateJourney(){
  stopNavigation();state.routes=[];state.requestId++;$('route-section').hidden=true;
  state.layers.forEach(layer=>map?.removeLayer(layer));state.layers=[];
  state.endpoints.forEach(layer=>map?.removeLayer(layer));state.endpoints=[];
  $('map-hint').hidden=false;$('map-hint').textContent='Your next journey starts here';
}
for(const id of ['start','end']){
  let timer,controller,sequence=0;
  $(id).addEventListener('input',()=>{
    state[id]=null;invalidateJourney();clearTimeout(timer);controller?.abort();sequence++;
    const mine=sequence,q=$(id).value.trim();$(id+'-options').replaceChildren();if(q.length<3)return;
    timer=setTimeout(async()=>{
      controller=new AbortController();
      try{
        const result=await api('/search?q='+encodeURIComponent(q),{signal:controller.signal});if(mine!==sequence)return;
        const box=$(id+'-options');box.replaceChildren();
        if(!result.places.length)box.append(node('p','No matches. Try a nearby landmark or city.'));
        result.places.forEach(place=>{const button=node('button',place.label);button.type='button';button.addEventListener('click',()=>{sequence++;controller?.abort();choosePoint(id,place);});box.append(button);});
      }catch(error){if(error.name!=='AbortError'&&mine===sequence)$(id+'-options').replaceChildren(node('p',error.message));}
    },400);
  });
}
document.addEventListener('click',event=>{if(!event.target.closest('.field'))for(const id of ['start','end'])$(id+'-options').replaceChildren();});
$('mode').addEventListener('change',invalidateJourney);
function gps(){return new Promise((resolve,reject)=>{
  if(!navigator.geolocation)return reject(new Error('This browser does not support location.'));
  navigator.geolocation.getCurrentPosition(resolve,()=>reject(new Error('Location unavailable. Allow location access and use HTTPS or localhost.')),{enableHighAccuracy:true,timeout:15000,maximumAge:0});
});}
function displayPosition(position){
  state.position=position;const {latitude:lat,longitude:lng,accuracy}=position.coords;
  if(map){if(!state.marker)state.marker=L.circleMarker([lat,lng],{radius:8,color:'white',weight:3,fillColor:'#166449',fillOpacity:1}).addTo(map);else state.marker.setLatLng([lat,lng]);
    if(!state.accuracy)state.accuracy=L.circle([lat,lng],{radius:accuracy,color:'#166449',weight:1,fillOpacity:.08}).addTo(map);else state.accuracy.setLatLng([lat,lng]).setRadius(accuracy);}
}
$('locate').addEventListener('click',async()=>{
  $('locate').disabled=true;status('Finding your location…');
  try{const position=await gps();displayPosition(position);const lat=position.coords.latitude,lng=position.coords.longitude;
    let label='Current location';try{label=(await api(`/reverse?lat=${lat}&lng=${lng}`)).label;}catch{}choosePoint('start',{lat,lng,label});map?.setView([lat,lng],15);status('Current location selected.');
  }catch(error){status(error.message,true);}finally{$('locate').disabled=false;}
});
$('plan-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!state.start||!state.end)return status('Choose both locations from the search suggestions, or use current location.',true);
  invalidateJourney();const mine=state.requestId;$('find').disabled=true;status('Finding your routes…');
  try{const result=await api('/routes',{method:'POST',body:JSON.stringify({start:[state.start.lat,state.start.lng],end:[state.end.lat,state.end.lng],mode:$('mode').value})});
    if(mine!==state.requestId)return;state.routes=result.routes;state.selected=0;renderRoutes();$('route-section').hidden=false;$('route-count').textContent=`${result.routes.length} option${result.routes.length===1?'':'s'}`;
    status(result.warnings.join(' ')||(result.routes.length===1?'One distinct route returned.':'Choose a route below.'));fitRoute();
  }catch(error){if(mine===state.requestId)status(error.message,true);}finally{$('find').disabled=false;}
});
function renderRoutes() {
  $('route-cards').replaceChildren();
  state.layers.forEach(layer => map?.removeLayer(layer));
  state.endpoints.forEach(layer => map?.removeLayer(layer));
  state.layers = [];
  state.endpoints = [];

  if (!state.routes.length) return;

  state.routes.forEach((route, index) => {
    const selected = index === state.selected;
    const card = node(
      'button',
      undefined,
      'route-card' + (selected ? ' selected' : '')
    );

    card.type = 'button';
    card.setAttribute('aria-pressed', String(selected));

    const header = node('div', undefined, 'route-header');
    const title = node('div', undefined, 'route-title');

    title.append(
      node('strong', `Route ${index + 1}`),
      node(
        'small',
        route.preference === 'short'
          ? 'Distance-focused'
          : 'Balanced route'
      )
    );

    const travel = node('div', undefined, 'route-travel');
    travel.append(
      node('strong', minutes(route.duration)),
      node('small', km(route.distance))
    );

    header.append(title, travel);
    card.append(
      header,
      node('span', 'DEMO COMPARISON', 'demo-badge')
    );

    const demo = route.demo;
    const available =
      demo && demo.status !== 'DEMO_DATA_UNAVAILABLE';

    function score(value) {
      return available &&
        typeof value === 'number' &&
        Number.isFinite(value) &&
        value >= 0 &&
        value <= 100
          ? `${Math.round(value)}/100`
          : '—';
    }

    function statistic(value, label) {
      const box = node('div', undefined, 'demo-stat');
      box.append(
        node('strong', value),
        node('small', label)
      );
      return box;
    }

    const statistics = node(
      'div',
      undefined,
      'demo-statistics'
    );

    statistics.append(
      statistic(
        available && Number.isInteger(demo.incident_count)
          ? String(demo.incident_count)
          : '—',
        'Sample incidents'
      ),
      statistic(
        score(demo?.demo_safety_score),
        'Demo safety score'
      ),
      statistic(
        score(demo?.demo_crime_index),
        'Demo crime index'
      )
    );

    card.append(statistics);

    const note = !available
      ? 'Demo data unavailable.'
      : demo.status === 'NO_DEMO_RECORDS_NEAR_ROUTE'
        ? 'No demo records within 250 m. Safety is unknown.'
        : 'Synthetic demo only. These indices are not real safety or crime rates.';

    card.append(node('p', note, 'demo-card-note'));

    function selectRoute() {
      stopNavigation();
      state.selected = index;
      renderRoutes();
      fitRoute();
    }

    card.addEventListener('click', selectRoute);
    $('route-cards').append(card);

    if (map) {
      const layer = L.geoJSON(
        {
          type: 'Feature',
          geometry: route.geometry,
          properties: {}
        },
        {
          style: {
            color: selected ? '#166449' : '#8096b2',
            weight: selected ? 7 : 4,
            opacity: selected ? 1 : 0.6
          }
        }
      ).addTo(map);

      layer.on('click', selectRoute);
      state.layers.push(layer);
    }
  });

  state.layers[state.selected]?.bringToFront();

  const chosen = state.routes[state.selected];
  $('map-hint').hidden = false;
  $('map-hint').textContent =
    `${km(chosen.distance)} · ${minutes(chosen.duration)} estimated`;

  if (map) {
    for (const [key, color] of [
      ['start', '#166449'],
      ['end', '#a92e42']
    ]) {
      const place = state[key];
      if (!place) continue;

      const marker = L.circleMarker(
        [place.lat, place.lng],
        {
          radius: 9,
          color: 'white',
          weight: 3,
          fillColor: color,
          fillOpacity: 1
        }
      )
        .bindPopup(
          node(
            'span',
            `${key === 'start' ? 'Start' : 'Destination'}: ${place.label}`
          )
        )
        .addTo(map);

      state.endpoints.push(marker);
    }
  }
}
function fitRoute(){if(map&&state.layers[state.selected])map.fitBounds(state.layers[state.selected].getBounds(),{padding:[35,35]});}
$('fit').addEventListener('click',()=>{if(state.routes.length)fitRoute();else if(state.position)map?.setView([state.position.coords.latitude,state.position.coords.longitude],16);});
function expand(force){const shell=$('map-shell');shell.classList.toggle('expanded',force??!shell.classList.contains('expanded'));$('expand').setAttribute('aria-label',shell.classList.contains('expanded')?'Close expanded map':'Expand map');setTimeout(()=>map?.invalidateSize(),50);}
$('expand').addEventListener('click',()=>expand());document.addEventListener('keydown',event=>{if(event.key==='Escape')expand(false);});
function meters(a,b){const rad=x=>x*Math.PI/180;const h=Math.sin(rad(b[1]-a[1])/2)**2+Math.cos(rad(a[1]))*Math.cos(rad(b[1]))*Math.sin(rad(b[0]-a[0])/2)**2;return 12742000*Math.asin(Math.min(1,Math.sqrt(h)));}
function nearestProgress(p,line){
  let best={distance:Infinity,index:0,along:0},traveled=0;
  for(let i=0;i<line.length-1;i++){
    const a=line[i],b=line[i+1],scale=Math.cos(p[1]*Math.PI/180),ax=(a[0]-p[0])*scale*111320,ay=(a[1]-p[1])*111320,bx=(b[0]-p[0])*scale*111320,by=(b[1]-p[1])*111320,dx=bx-ax,dy=by-ay;
    const t=dx*dx+dy*dy?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))):0,dist=Math.hypot(ax+t*dx,ay+t*dy),length=meters(a,b);
    if(dist<best.distance)best={distance:dist,index:i+t,along:traveled+t*length};traveled+=length;
  }return {...best,total:traveled};
}
function updateNavigation(position){
  displayPosition(position);const route=state.routes[state.selected];if(!route)return;
  const p=[position.coords.longitude,position.coords.latitude],line=flat(route),progress=nearestProgress(p,line);
  map?.panTo([p[1],p[0]],{animate:false});
  if(position.coords.accuracy>100){$('instruction').textContent='GPS accuracy is low';$('progress').textContent='Wait for a better location fix. Route progress may be inaccurate.';return;}
  if(progress.distance>Math.max(60,position.coords.accuracy*2)){$('instruction').textContent='You appear to be off this route';$('progress').textContent='Stop safely and plan a new route if needed. Automatic rerouting is unavailable.';return;}
  state.navIndex=progress.index;
  const step=route.steps.find(s=>s.index>progress.index+.3);
  $('instruction').textContent=step?step.text:'Continue to your destination';
  const remaining=Math.max(0,progress.total-progress.along),fraction=progress.total?remaining/progress.total:0;
  const ahead=step?meters(p,step.point):0;
  $('progress').textContent=`${step?`Next turn about ${km(ahead)} away · `:''}${km(remaining)} remaining · ${minutes(route.duration*fraction)} estimated`;
  if(remaining<30&&meters(p,line[line.length-1])<40){$('instruction').textContent='Near your destination';$('progress').textContent='Confirm your arrival when you reach your destination.';}
}
$('navigate').addEventListener('click',()=>{
  if(!state.routes.length)return;if(!navigator.geolocation)return status('Location is unavailable in this browser.',true);
  stopNavigation();state.navIndex=0;$('nav-panel').hidden=false;$('map-hint').hidden=true;$('instruction').textContent='Waiting for GPS…';$('progress').textContent='Allow location access to start guidance.';expand(true);map?.setZoom(17);
  state.watch=navigator.geolocation.watchPosition(updateNavigation,()=>{$('instruction').textContent='GPS unavailable';$('progress').textContent='Allow location access or end navigation and retry.';},{enableHighAccuracy:true,timeout:15000,maximumAge:0});
});
function stopNavigation(){if(state.watch!==null){navigator.geolocation.clearWatch(state.watch);state.watch=null;}$('nav-panel').hidden=true;$('map-hint').hidden=false;}
$('stop').addEventListener('click',()=>{stopNavigation();expand(false);fitRoute();});window.addEventListener('pagehide',stopNavigation);
function openDialog(id){if(id==='contacts-dialog'||id==='emergency-dialog')renderContacts();if(id==='reports-dialog')loadReports();$(id).showModal();}
document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>openDialog(button.dataset.open)));
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
function contacts(){try{const data=JSON.parse(localStorage.getItem('safewalk-contacts')||'[]');return Array.isArray(data)?data.filter(c=>typeof c.name==='string'&&typeof c.phone==='string'&&/^\+?[0-9]{7,15}$/.test(c.phone)).slice(0,5):[];}catch{return [];}}
function saveContacts(data){try{localStorage.setItem('safewalk-contacts',JSON.stringify(data));return true;}catch{status('Browser storage is unavailable. Contacts could not be saved.',true);return false;}}
$('contact-form').addEventListener('submit',event=>{
  event.preventDefault();const name=$('contact-name').value.trim(),phone=$('contact-phone').value.replace(/[\s()-]/g,'');let rows=contacts();
  if(!name||!/^\+?[0-9]{7,15}$/.test(phone))return alert('Enter a name and a valid phone number.');
  if(rows.length>=5)return alert('You can save up to five contacts.');if(rows.some(c=>c.phone===phone))return alert('This number is already saved.');
  if(saveContacts([...rows,{name,phone}])){$('contact-form').reset();renderContacts();}
});
function renderContacts(){
  const list=$('contact-list'),emergency=$('emergency-contacts');list.replaceChildren();emergency.replaceChildren();
  const rows=contacts();if(!rows.length)list.append(node('p','No contacts saved yet.','muted'));
  rows.forEach((contact,index)=>{
    const row=node('div',undefined,'contact-item'),detail=node('div');detail.append(node('p',contact.name+(index===0?' · Primary':'')),node('small',contact.phone));const actions=node('div');
    if(index>0){const primary=node('button','Make primary');primary.addEventListener('click',()=>{const next=contacts(),[item]=next.splice(index,1);next.unshift(item);saveContacts(next);renderContacts();});actions.append(primary);}
    const edit=node('button','Edit');edit.addEventListener('click',()=>{const name=prompt('Contact name',contact.name);if(name===null)return;const input=prompt('Phone number',contact.phone);if(input===null)return;const phone=input.replace(/[\s()-]/g,'');if(!name.trim()||name.length>60||!/^\+?[0-9]{7,15}$/.test(phone))return alert('Invalid contact.');const next=contacts();next[index]={name:name.trim(),phone};saveContacts(next);renderContacts();});
    const remove=node('button','Delete');remove.addEventListener('click',()=>{if(!confirm('Delete this contact?'))return;saveContacts(contacts().filter((_,i)=>i!==index));renderContacts();});actions.append(edit,remove);row.append(detail,actions);list.append(row);
    const call=node('a',`Call ${contact.name}`,'button full');call.href='tel:'+contact.phone;emergency.append(call);
  });
}
$('delete-contacts').addEventListener('click',()=>{if(confirm('Delete all contacts saved in this browser?')){saveContacts([]);renderContacts();}});
async function shareText(text){
  if(navigator.share){try{await navigator.share({title:'SafeWalk journey',text});return;}catch(error){if(error.name==='AbortError')return;}}
  $('share-message').value=text;$('copy-status').textContent='';$('share-dialog').showModal();
}
$('copy-message').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('share-message').value);$('copy-status').textContent='Copied. Send it through your preferred app.';}catch{$('share-message').select();$('copy-status').textContent='Select and copy this message manually.';}});
function locationLink(position){return `https://www.openstreetmap.org/?mlat=${position.coords.latitude}&mlon=${position.coords.longitude}#map=17/${position.coords.latitude}/${position.coords.longitude}`;}
$('share').addEventListener('click',()=>{
  const route=state.routes[state.selected];if(!route)return;
  shareText(`I’m planning a journey with SafeWalk.\nFrom: ${state.start.label}\nTo: ${state.end.label}\nDistance: ${km(route.distance)}\nEstimated travel time: ${minutes(route.duration)}\nDestination: https://www.openstreetmap.org/?mlat=${state.end.lat}&mlon=${state.end.lng}#map=16/${state.end.lat}/${state.end.lng}\nThis is a journey summary, not live tracking.`);
});
$('share-location').addEventListener('click',async()=>{try{const position=await gps();displayPosition(position);$('emergency-dialog').close();await shareText(`Please check in with me. My location at ${new Date(position.timestamp).toLocaleString()} is:\n${locationLink(position)}\nGPS accuracy: about ${Math.round(position.coords.accuracy)} m. This is a location snapshot, not live tracking.`);}catch(error){alert(error.message);}});
$('arrival').addEventListener('click',()=>{if(!confirm('Confirm that you have arrived at your destination?'))return;stopNavigation();expand(false);shareText(`I’ve arrived at ${state.end?.label||'my destination'}. Checked in at ${new Date().toLocaleString()}.`);});
$('nearby').addEventListener('click',async()=>{
  $('nearby').disabled=true;status('Looking for nearby help…');
  try{
    let lat,lng;if(state.watch!==null){const p=await gps();displayPosition(p);lat=p.coords.latitude;lng=p.coords.longitude;}else if(state.start){lat=state.start.lat;lng=state.start.lng;}else{const p=await gps();displayPosition(p);lat=p.coords.latitude;lng=p.coords.longitude;}
    const result=await api(`/help?lat=${lat}&lng=${lng}`);clearHelp();$('help-section').hidden=false;
    if(!result.places.length)$('help-list').append(node('p','No facilities returned here. This does not mean help is unavailable.'));
    result.places.forEach(place=>{const box=node('div',undefined,'help-item'),button=node('button',`${place.name} · ${km(place.distance)}`);button.addEventListener('click',()=>map?.setView([place.lat,place.lng],17));box.append(button);$('help-list').append(box);if(map){const marker=L.circleMarker([place.lat,place.lng],{color:'#496ca2',radius:7}).bindPopup(node('span',place.name)).addTo(map);state.helpLayers.push(marker);}});
    status('Nearby help loaded around your '+(state.watch!==null?'current location.':state.start?'starting point.':'current location.'));
  }catch(error){status(error.message,true);}finally{$('nearby').disabled=false;}
});
function clearHelp(){state.helpLayers.forEach(layer=>map?.removeLayer(layer));state.helpLayers=[];$('help-list').replaceChildren();$('help-section').hidden=true;}
$('clear-help').addEventListener('click',clearHelp);
$('report-location').addEventListener('click',async()=>{try{const p=await gps();$('report-lat').value=p.coords.latitude.toFixed(6);$('report-lng').value=p.coords.longitude.toFixed(6);}catch(error){$('report-feedback').textContent=error.message;}});
$('report-form').addEventListener('submit',async event=>{
  event.preventDefault();const submit=event.target.querySelector('[type="submit"]')||event.target.querySelector('.primary');submit.disabled=true;
  try{await api('/reports',{method:'POST',body:JSON.stringify({category:$('category').value,description:$('description').value,lat:Number($('report-lat').value),lng:Number($('report-lng').value)})});event.target.reset();$('report-feedback').textContent='Report submitted for review. See My reports for its status.';}catch(error){$('report-feedback').textContent=error.message;}finally{submit.disabled=false;}
});
async function loadReports(){
  $('my-reports').replaceChildren(node('p','Loading…'));
  try{const result=await api('/reports');$('my-reports').replaceChildren();if(!result.reports.length)$('my-reports').append(node('p','No reports submitted by this browser.'));
    result.reports.forEach(report=>{const row=node('div',undefined,'report-item');row.append(node('span',report.status,'badge'),node('h3',report.category.replaceAll('_',' ')),node('p',report.description),node('small',`${report.lat}, ${report.lng}`));const remove=node('button','Delete report');remove.addEventListener('click',async()=>{if(!confirm('Delete your report?'))return;try{await api('/reports/'+report.id,{method:'DELETE'});loadReports();}catch(error){alert(error.message);}});row.append(remove);$('my-reports').append(row);});
  }catch(error){$('my-reports').replaceChildren(node('p',error.message,'error'));}
}
