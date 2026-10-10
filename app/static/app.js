'use strict';
const $ = id => document.getElementById(id);
const FACILITY_CATEGORIES = [
  {id:'healthcare.hospital',label:'Hospitals',color:'#b42335',icon:'H'},
  {id:'service.police',label:'Police stations',color:'#3157a4',icon:'P'},
  {id:'healthcare.pharmacy',label:'Pharmacies',color:'#167a59',icon:'+'}
];
const state = {start:null,end:null,routes:[],selected:0,watch:null,navGeneration:0,position:null,lastHeading:null,lastMovement:null,lastArrowPosition:null,followMap:true,navIndex:0,layers:[],helpLayers:[],endpoints:[],marker:null,accuracy:null,requestId:0,facilityRequestId:0,lastFacilityPosition:null,lastFacilityRequestPosition:null,lastFacilityRefresh:0,facilityTimer:null,facilityVisible:new Set(FACILITY_CATEGORIES.map(category=>category.id))};
const token = document.querySelector('meta[name="csrf-token"]').content;
let map = null;
const themeToggle = $('theme-toggle');
function setTheme(theme, save = false) {
  document.documentElement.dataset.theme = theme;
  const nextTheme = theme === 'dark' ? 'light' : 'dark';
  $('theme-toggle-icon').textContent = nextTheme === 'dark' ? '🌙' : '☀️';
  $('theme-toggle-label').textContent = nextTheme === 'dark' ? 'Dark' : 'Light';
  themeToggle.setAttribute('aria-label', `Switch to ${nextTheme} theme`);
  themeToggle.setAttribute('aria-pressed', String(theme === 'dark'));
  if (save) {
    try {
      localStorage.setItem('safewalk-theme', theme);
    } catch (error) {
      console.warn('Theme preference could not be saved:', error);
    }
  }
}
setTheme(document.documentElement.dataset.theme || 'light');
themeToggle.addEventListener('click', () => {
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
});
if (typeof L !== 'undefined') {
  map = L.map('map',{zoomControl:false}).setView([22.5,79],5);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
  L.control.zoom({position:'bottomright'}).addTo(map);
  map.on('dragstart',()=>setMapFollow(false));
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
function choosePoint(id,place){state[id]=place;$(id).value=place.label;$(id+'-options').replaceChildren();invalidateJourney();}
function invalidateJourney(){
  stopNavigation();state.routes=[];state.requestId++;state.facilityRequestId++;state.lastFacilityPosition=null;state.lastFacilityRequestPosition=null;$('route-section').hidden=true;clearHelp();
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
  state.position=position;const {latitude:lat,longitude:lng,accuracy}=position.coords,point=[lat,lng];
  if(map){
    if(!state.accuracy)state.accuracy=L.circle(point,{radius:accuracy,color:'#166449',weight:1,fillOpacity:.08}).addTo(map);else state.accuracy.setLatLng(point).setRadius(accuracy);
    if(!state.marker){
      state.marker=L.marker(point,{icon:L.divIcon({className:'user-location-icon',html:'<span class="user-arrow heading-unknown"></span>',iconSize:[30,30],iconAnchor:[15,15]}),zIndexOffset:1200}).addTo(map);
      state.lastArrowPosition=[lng,lat];
    }else if(!state.lastArrowPosition||meters([state.lastArrowPosition[0],state.lastArrowPosition[1]],[lng,lat])>=Math.max(3,Math.min(accuracy*.25,12))){
      state.marker.setLatLng(point);state.lastArrowPosition=[lng,lat];
    }
    if(state.lastHeading!==null){
      const arrow=state.marker.getElement()?.querySelector('.user-arrow');
      if(arrow){arrow.classList.remove('heading-unknown');arrow.style.transform=`rotate(${state.lastHeading}deg)`;}
    }
  }
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
    if(mine!==state.requestId)return;state.routes=result.routes;state.selected=Math.max(0,result.routes.findIndex(route=>route.recommended));renderRoutes();$('route-section').hidden=false;$('route-count').textContent=`${result.routes.length} option${result.routes.length===1?'':'s'}`;
    status(result.warnings.join(' ')||(result.routes.length===1?'One distinct route returned.':'Choose a route below.'));fitRoute();loadFacilities(state.start.lat,state.start.lng);
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
    card.append(header,node('span','SYNTHETIC DEMO','demo-badge'));

    const demo = route.demo;
    function score(value) {
      return typeof value === 'number' &&
        Number.isFinite(value) &&
        value >= 0 &&
        value <= 100
          ? `${Math.round(value)}/100`
          : '—/100';
    }

    function statistic(value, label) {
      const box = node('div', undefined, 'demo-stat');
      box.append(
        node('strong', value),
        node('small', label)
      );
      return box;
    }

    const statistics = node('div', undefined, 'demo-statistics');
    const lighting = route.lighting || {};
    const lightingCard = node('div', undefined, 'demo-stat lighting-rating');
    const lightingHeading = node('div', undefined, 'lighting-rating-heading');
    lightingHeading.append(node('strong', score(lighting.lighting_score)));
    lightingCard.append(lightingHeading, node('small', 'Lighting . Demo'));
    statistics.append(
      statistic(score(demo?.demo_safety_score), 'Safety · DEMO'),
      statistic(score(demo?.demo_crime_index), 'Crime Risk · DEMO'),
      lightingCard
    );
    card.append(statistics);
    const facilities = node('div', undefined, 'route-facilities');
    const police = route.demo?.police_distance_meters;
    const hospital = route.demo?.hospital_distance_meters;
    facilities.append(node('small',
      `Police distance: ${typeof police === 'number' ? km(police) : '—'} · Hospital distance: ${typeof hospital === 'number' ? km(hospital) : '—'}`));
    card.append(facilities);
    if (route.recommended) {
      card.append(node('small',
        route.recommendation_basis === 'demo_balanced'
          ? '★ Demo Recommended'
          : '★ Fastest route · demo ratings unavailable',
        'route-recommendation'));
    }

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
function fitRoute(){if(map&&state.layers[state.selected])map.fitBounds(state.layers[state.selected].getBounds(),{padding:[50,50]});}
$('fit').addEventListener('click',()=>{if(state.routes.length)fitRoute();else if(state.position)map?.setView([state.position.coords.latitude,state.position.coords.longitude],16);});
function setMapFollow(enabled){state.followMap=enabled;$('follow').textContent=`Follow: ${enabled?'On':'Off'}`;$('follow').setAttribute('aria-pressed',String(enabled));$('follow').setAttribute('aria-label',`Map follow ${enabled?'on':'off'}`);}
$('follow').addEventListener('click',()=>setMapFollow(!state.followMap));
$('recenter').addEventListener('click',()=>{if(!state.position)return status('Current location is not available yet.',true);setMapFollow(true);map?.setView([state.position.coords.latitude,state.position.coords.longitude],17);});
function expand(force){const shell=$('map-shell');shell.classList.toggle('expanded',force??!shell.classList.contains('expanded'));$('expand').setAttribute('aria-label',shell.classList.contains('expanded')?'Close expanded map':'Expand map');setTimeout(()=>map?.invalidateSize(),50);}
$('expand').addEventListener('click',()=>expand());document.addEventListener('keydown',event=>{if(event.key==='Escape')expand(false);});
function meters(a,b){const rad=x=>x*Math.PI/180;const h=Math.sin(rad(b[1]-a[1])/2)**2+Math.cos(rad(a[1]))*Math.cos(rad(b[1]))*Math.sin(rad(b[0]-a[0])/2)**2;return 12742000*Math.asin(Math.min(1,Math.sqrt(h)));}
function routeParts(route){return route.geometry.type==='LineString'?[route.geometry.coordinates]:route.geometry.coordinates;}
function nearestProgress(p,route){
  let best={distance:Infinity,index:0,along:0,total:0},globalIndex=0,total=0;
  for(const part of routeParts(route))for(let i=0;i<part.length-1;i++){total+=meters(part[i],part[i+1]);}
  let traveled=0;
  for(const part of routeParts(route)){
    for(let i=0;i<part.length-1;i++){
      const a=part[i],b=part[i+1],scale=Math.cos(p[1]*Math.PI/180),ax=(a[0]-p[0])*scale*111320,ay=(a[1]-p[1])*111320,bx=(b[0]-p[0])*scale*111320,by=(b[1]-p[1])*111320,dx=bx-ax,dy=by-ay;
      const t=dx*dx+dy*dy?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))):0,dist=Math.hypot(ax+t*dx,ay+t*dy),length=meters(a,b);
      if(dist<best.distance)best={distance:dist,index:globalIndex+i+t,along:traveled+t*length,total};
      traveled+=length;
    }
    globalIndex+=part.length;
  }
  return best;
}
function distanceAtRouteIndex(route,index){
  let traveled=0,vertexIndex=0;
  for(const part of routeParts(route)){
    for(let i=0;i<part.length-1;i++){
      const length=meters(part[i],part[i+1]),segmentIndex=vertexIndex+i;
      if(index<=segmentIndex+1)return traveled+length*Math.max(0,Math.min(1,index-segmentIndex));
      traveled+=length;
    }
    vertexIndex+=part.length;
  }
  return traveled;
}
function bearing(a,b){
  const radians=value=>value*Math.PI/180,lat1=radians(a[1]),lat2=radians(b[1]),delta=radians(b[0]-a[0]);
  return (Math.atan2(Math.sin(delta)*Math.cos(lat2),Math.cos(lat1)*Math.sin(lat2)-Math.sin(lat1)*Math.cos(lat2)*Math.cos(delta))*180/Math.PI+360)%360;
}
function updateHeading(position){
  const {longitude,latitude,accuracy,heading,speed}=position.coords,point=[longitude,latitude];
  if(accuracy<=50&&Number.isFinite(heading)&&heading>=0&&Number.isFinite(speed)&&speed>=1.5){
    state.lastHeading=heading;
    state.lastMovement={point,accuracy};
    return;
  }
  if(accuracy>40)return;
  if(!state.lastMovement){state.lastMovement={point,accuracy};return;}
  const moved=meters(state.lastMovement.point,point),minimum=Math.max(8,Math.min(25,(accuracy+state.lastMovement.accuracy)*.75));
  if(moved>=minimum){
    state.lastHeading=bearing(state.lastMovement.point,point);
    state.lastMovement={point,accuracy};
  }
}
function setInstruction(text,icon){$('instruction').textContent=text;$('turn-icon').textContent=icon;}
function instructionIcon(text){
  if(/u[- ]?turn/i.test(text))return '↩';
  if(/left/i.test(text))return '↶';
  if(/right/i.test(text))return '↷';
  if(/roundabout/i.test(text))return '⟳';
  if(/straight|continue|head|destination/i.test(text))return '↑';
  return '•';
}
function updateNavigation(position){
  updateHeading(position);displayPosition(position);
  const route=state.routes[state.selected];if(!route)return;
  const accuracy=position.coords.accuracy,p=[position.coords.longitude,position.coords.latitude],progress=nearestProgress(p,route);
  maybeRefreshFacilities(position);
  if(state.followMap)map?.panTo([p[1],p[0]],{animate:false});
  if(accuracy>100){setInstruction('GPS accuracy is low','!');$('progress').textContent=`Wait for a better location fix (±${Math.round(accuracy)} m).`;return;}
  if(progress.distance>Math.max(60,accuracy*2)){
    setInstruction('You appear to be off this route','!');
    $('progress').textContent=`You are about ${km(progress.distance)} from the route. Stop safely and plan a new route; automatic rerouting is unavailable. GPS accuracy ±${Math.round(accuracy)} m.`;
    return;
  }
  state.navIndex=progress.index;
  const upcoming=(route.steps||[]).find(step=>distanceAtRouteIndex(route,step.index)>=progress.along-Math.max(10,accuracy));
  const remaining=Math.max(0,progress.total-progress.along),fraction=progress.total?remaining/progress.total:0;
  $('map-hint').textContent=`${km(remaining)} remaining · ${minutes(route.duration*fraction)} estimated`;
  const parts=routeParts(route),lastPart=parts[parts.length-1],endpoint=lastPart&&lastPart[lastPart.length-1];
  if(remaining<30&&endpoint&&meters(p,endpoint)<Math.max(40,accuracy*1.5)){
    setInstruction('Near your destination','✓');$('progress').textContent='Confirm your arrival when you reach your destination.';
  }else if(upcoming){
    const toManeuver=Math.max(0,distanceAtRouteIndex(route,upcoming.index)-progress.along);
    const action=upcoming.text.replace(/[.!?]+$/,'');
    setInstruction(`${action} in ${km(toManeuver)}`,instructionIcon(upcoming.text));
    $('progress').textContent=`${km(remaining)} remaining · ${minutes(route.duration*fraction)} estimated · GPS accuracy ±${Math.round(accuracy)} m`;
  }else if(route.steps?.length){
    setInstruction('Continue to your destination','↑');
    $('progress').textContent=`${km(remaining)} remaining · ${minutes(route.duration*fraction)} estimated · GPS accuracy ±${Math.round(accuracy)} m`;
  }else{
    setInstruction('Turn instructions unavailable','•');
    $('progress').textContent=`Follow the highlighted route. ${km(remaining)} remaining · ${minutes(route.duration*fraction)} estimated · GPS accuracy ±${Math.round(accuracy)} m`;
  }
}
function navigationError(error){
  const message=error.code===1?'Location permission denied. Allow location access in your browser settings.':error.code===2?'GPS location is unavailable. Check location services and retry.':'GPS timed out. Move to a clearer area or retry.';
  if(state.watch!==null){navigator.geolocation.clearWatch(state.watch);state.watch=null;}
  setInstruction('GPS unavailable','!');$('progress').textContent=message;
  $('retry-gps').hidden=false;
  status(message,true);
}
function startNavigation(){
  if(!state.routes.length)return;
  if(!navigator.geolocation)return status('Location is unavailable in this browser.',true);
  stopNavigation();state.navIndex=0;state.lastMovement=null;state.lastHeading=null;$('nav-panel').hidden=false;$('map-hint').hidden=false;
  $('retry-gps').hidden=true;
  setInstruction('Waiting for GPS…','•');$('progress').textContent='Allow location access to start turn-by-turn guidance.';
  setMapFollow(true);expand(true);map?.setZoom(17);
  const generation=state.navGeneration;
  try{state.watch=navigator.geolocation.watchPosition(
    position=>{if(state.watch!==null&&state.navGeneration===generation)updateNavigation(position);},
    error=>{if(state.watch!==null&&state.navGeneration===generation)navigationError(error);},
    {enableHighAccuracy:true,timeout:15000,maximumAge:0}
  );}
  catch(error){navigationError({code:2});}
}
$('navigate').addEventListener('click',startNavigation);
$('retry-gps').addEventListener('click',startNavigation);
function stopNavigation(){
  state.navGeneration++;
  if(state.watch!==null){navigator.geolocation.clearWatch(state.watch);state.watch=null;}
  if(state.facilityTimer!==null){clearTimeout(state.facilityTimer);state.facilityTimer=null;}
  state.lastMovement=null;state.lastHeading=null;state.lastFacilityPosition=null;
  state.lastFacilityRequestPosition=null;
  const arrow=state.marker?.getElement()?.querySelector('.user-arrow');
  if(arrow){arrow.classList.add('heading-unknown');arrow.style.transform='';}
  $('retry-gps').hidden=true;
  $('nav-panel').hidden=true;$('map-hint').hidden=false;
}
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
function setupFacilityToggles(){
  const toggles=$('facility-toggles');toggles.replaceChildren();
  FACILITY_CATEGORIES.forEach(category=>{
    const label=node('label',undefined,'facility-toggle'),checkbox=node('input');
    checkbox.type='checkbox';checkbox.checked=state.facilityVisible.has(category.id);
    checkbox.addEventListener('change',()=>{
      if(checkbox.checked)state.facilityVisible.add(category.id);else state.facilityVisible.delete(category.id);
      applyFacilityVisibility();
    });
    label.append(checkbox,node('span',category.label));toggles.append(label);
  });
}
function applyFacilityVisibility(){
  state.helpLayers.forEach(item=>{
    if(!map)return;
    if(state.facilityVisible.has(item.category)){if(!map.hasLayer(item.layer))item.layer.addTo(map);}
    else if(map.hasLayer(item.layer))map.removeLayer(item.layer);
  });
  document.querySelectorAll('.facility-list-item').forEach(item=>{
    item.hidden=!state.facilityVisible.has(item.dataset.category);
  });
}
function renderFacilities(places){
  const list=$('help-list');list.replaceChildren();
  state.helpLayers.forEach(item=>map?.removeLayer(item.layer));state.helpLayers=[];
  if(!places.length){list.append(node('p','No matching facilities were returned within 5 km. This does not mean help is unavailable.','muted small'));return;}
  places.forEach(place=>{
    const category=FACILITY_CATEGORIES.find(item=>item.id===place.category);
    if(!category)return;
    const row=node('div',undefined,'help-item facility-list-item');row.dataset.category=place.category;
    const button=node('button',place.name);button.type='button';
    button.addEventListener('click',()=>map?.setView([place.lat,place.lng],17));
    row.append(button,node('small',`${place.category_label} · ${km(place.distance)} straight-line distance`));
    list.append(row);
    if(map){
      const marker=L.marker([place.lat,place.lng],{
        icon:L.divIcon({className:`facility-marker facility-marker-${category.icon==='+'?'pharmacy':category.icon==='H'?'hospital':'police'}`,html:`<span>${category.icon}</span>`,iconSize:[30,30],iconAnchor:[15,15]}),
        title:`${place.name}; ${place.category_label}; ${km(place.distance)} straight-line distance`
      }).bindPopup(node('span',`${place.name} · ${place.category_label} · ${km(place.distance)} straight-line distance`));
      state.helpLayers.push({layer:marker,category:place.category});
    }
  });
  applyFacilityVisibility();
}
setupFacilityToggles();
async function loadFacilities(latitude,longitude,centerLabel='selected location'){
  const requestId=++state.facilityRequestId;
  state.lastFacilityRequestPosition=[longitude,latitude];state.lastFacilityRefresh=Date.now();
  $('help-section').hidden=false;$('facility-status').textContent='Loading nearby facility listings…';
  try{
    const result=await api(`/help?lat=${latitude}&lng=${longitude}`);
    if(requestId!==state.facilityRequestId)return false;
    renderFacilities(result.places);
    $('facility-status').textContent=`Showing facilities within 5 km of your ${centerLabel}. Straight-line distances; operational status is unverified.`;
    state.lastFacilityPosition=[longitude,latitude];
    return true;
  }catch(error){
    if(requestId===state.facilityRequestId)$('facility-status').textContent=`Nearby facility listings unavailable: ${error.message}`;
    return false;
  }
}
function maybeRefreshFacilities(position){
  if(position.coords.accuracy>50)return;
  const point=[position.coords.longitude,position.coords.latitude],last=state.lastFacilityPosition||state.lastFacilityRequestPosition;
  if(!last&&state.watch!==null){loadFacilities(point[1],point[0],'current location');return;}
  const moved=last?meters(last,point):Infinity,elapsed=Date.now()-state.lastFacilityRefresh;
  if(moved<300)return;
  if(elapsed>=60000){loadFacilities(point[1],point[0],'current location');return;}
  if(state.facilityTimer===null){
    state.facilityTimer=setTimeout(()=>{
      state.facilityTimer=null;
      if(state.watch!==null&&state.position?.coords.accuracy<=50){
        const latest=[state.position.coords.longitude,state.position.coords.latitude];
        if(!state.lastFacilityPosition||meters(state.lastFacilityPosition,latest)>=300)loadFacilities(latest[1],latest[0],'current location');
      }
    },60000-elapsed);
  }
}
$('nearby').addEventListener('click',async()=>{
  $('nearby').disabled=true;status('Looking for nearby help…');
  try{
    let loaded;
    if(state.watch!==null){
      const position=state.position;
      if(!position||position.coords.accuracy>50)throw new Error('Waiting for an accurate GPS location fix.');
      loaded=await loadFacilities(position.coords.latitude,position.coords.longitude,'current location');
    }else if(state.start)loaded=await loadFacilities(state.start.lat,state.start.lng,'starting point');
    else{const position=await gps();displayPosition(position);loaded=await loadFacilities(position.coords.latitude,position.coords.longitude,'current location');}
    if(loaded)status('Nearby facility listings updated.');
    else status($('facility-status').textContent,true);
  }catch(error){status(error.message,true);}finally{$('nearby').disabled=false;}
});
function clearHelp(){state.facilityRequestId++;if(state.facilityTimer!==null){clearTimeout(state.facilityTimer);state.facilityTimer=null;}state.helpLayers.forEach(item=>map?.removeLayer(item.layer));state.helpLayers=[];$('help-list').replaceChildren();$('help-section').hidden=true;}
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
