// Browser/Leaflet/GPS stand-ins exercise client logic; coordinates below are simulated, not device GPS.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');

class Element {
  constructor(){
    this.value='';this.textContent='';this.hidden=false;this.children=[];this.listeners={};
    this.disabled=false;this.checked=false;this.type='';this.dataset={};this.attributes={};this.style={};
    const classes=new Set();
    this.classList={
      add:value=>classes.add(value),remove:value=>classes.delete(value),
      contains:value=>classes.has(value),toggle:(value,force)=>force===undefined?(classes.has(value)?classes.delete(value):classes.add(value)):(force?classes.add(value):classes.delete(value)),
    };
  }
  addEventListener(event,callback){this.listeners[event]=callback;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(key,value){this.attributes[key]=value;}
  showModal(){}
  close(){}
  reset(){}
  select(){}
  querySelector(selector){return selector==='.user-arrow'?arrow:new Element();}
}

const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
get('map-failure').hidden=true;
const arrow=new Element();
const storage=new Map(),timers=new Map();
let nextTimer=0,routeRequests=0,facilityRequests=0,gpsCleared=0,watchCallback=null,watchError=null;
const fakeMap={
  layers:new Set(),listeners:{},panCount:0,view:null,
  setView(point,zoom){this.view={point,zoom};return this;},
  on(event,callback){this.listeners[event]=callback;return this;},
  panTo(point){this.panCount++;this.view={point};return this;},
  fitBounds(){},setZoom(){},invalidateSize(){},
  addLayer(layer){this.layers.add(layer);layer.map=this;return this;},
  removeLayer(layer){this.layers.delete(layer);return this;},
  hasLayer(layer){return this.layers.has(layer);},
};
function layer(){
  return {
    addTo(target){target.addLayer(this);return this;},
    setLatLng(point){this.point=point;return this;},
    setRadius(radius){this.radius=radius;return this;},
    bindPopup(){return this;},on(){return this;},bringToFront(){},
    getBounds(){return {};},getElement(){return arrow;},
  };
}
const leaflet={
  map:()=>fakeMap,tileLayer:()=>layer(),control:{zoom:()=>({addTo(){}})},
  circle:()=>layer(),circleMarker:()=>layer(),marker:()=>layer(),divIcon:options=>options,
  geoJSON:()=>layer(),
};
const facilities=[
  {name:'Central Hospital',lat:17.4,lng:78.4,category:'healthcare.hospital',category_label:'Hospital',distance:420,distance_label:'straight-line distance'},
  {name:'City Police',lat:17.401,lng:78.401,category:'service.police',category_label:'Police station',distance:530,distance_label:'straight-line distance'},
  {name:'Local Pharmacy',lat:17.402,lng:78.402,category:'healthcare.pharmacy',category_label:'Pharmacy',distance:690,distance_label:'straight-line distance'},
];
const context=vm.createContext({
  document:{
    getElementById:get,querySelector:()=>({content:'test-token'}),createElement:()=>new Element(),
    querySelectorAll:selector=>selector==='.facility-list-item'?get('help-list').children:[],
    addEventListener(){},
  },
  window:{addEventListener(){}},
  navigator:{
    geolocation:{
      clearWatch(){gpsCleared++;},
      watchPosition(success,error,options){watchCallback=success;watchError=error;context.watchOptions=options;return 4;},
      getCurrentPosition(success,error){error({code:1});},
    },
  },
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  L:leaflet,
  fetch:async(path)=>{
    if(path.startsWith('/api/help')){facilityRequests++;return{ok:true,json:async()=>({places:facilities})};}
    if(path.startsWith('/api/routes')){
      routeRequests++;
      const line=[[78,17],[78.005,17],[78.01,17]];
      return{ok:true,json:async()=>({warnings:[],routes:[
        {id:0,recommended:false,recommendation_basis:'travel_time',preference:'balanced',distance:1113,duration:600,geometry:{type:'LineString',coordinates:line},steps:[{index:1,text:'Turn left',point:line[1],maneuver_point:line[1]}],demo:{demo_safety_score:0,demo_crime_index:0,status:'DEMO_RECORDS_FOUND'}},
        {id:1,recommended:true,recommendation_basis:'travel_time',preference:'short',distance:1200,duration:300,geometry:{type:'LineString',coordinates:line},steps:[],demo:{demo_safety_score:null,demo_crime_index:null,status:'NO_DEMO_RECORDS_NEAR_ROUTE'}},
      ]})};
    }
    return{ok:true,json:async()=>({places:[]})};
  },
  setTimeout:(callback,delay)=>{const id=++nextTimer;timers.set(id,{callback,delay});return id;},
  clearTimeout:id=>timers.delete(id),
  AbortController,console,alert(){},confirm:()=>true,prompt:()=>null,
  Date,Math,Set,Number,String,Array,JSON,Promise,
});
vm.runInContext(fs.readFileSync('app/static/app.js','utf8'),context);
const run=code=>vm.runInContext(code,context);
const textContent=element=>element.textContent+element.children.map(textContent).join(' ');
const position=(longitude,latitude=17,accuracy=8,heading=null,speed=0)=>({coords:{longitude,latitude,accuracy,heading,speed},timestamp:Date.now()});

(async()=>{
  assert.equal(get('map-failure').hidden,true,'Available Leaflet must not show a map-load error');
  assert.equal(run('minutes(3600)'),'1 h 0 min');
  assert.equal(run('km(1500)'),'1.5 km');
  run("state.start={lat:17,lng:78,label:'Start'};state.end={lat:17.01,lng:78.01,label:'End'};");
  get('mode').value='walk';
  await get('plan-form').listeners.submit({preventDefault(){}});
  for(let i=0;i<12;i++)await Promise.resolve();
  assert.equal(routeRequests,1,'Planning makes one route request');
  assert.equal(run('state.selected'),1,'The fastest route is preselected from the API travel-time choice');
  assert.equal(get('route-section').hidden,false);
  assert.equal(get('route-cards').children.length,2);
  const cards=get('route-cards').children,firstStats=cards[0].children[2].children,secondStats=cards[1].children[2].children;
  assert.equal(firstStats[0].children[0].textContent,'0/100','Valid zero safety score must render');
  assert.equal(firstStats[1].children[0].textContent,'0/100','Valid zero crime index must render');
  assert.doesNotMatch(textContent(cards[0]),/Sample incidents/,'Incidents are not displayed in route cards');
  assert.equal(secondStats[0].children[0].textContent,'—','Missing safety metric must render as an em dash');
  assert.equal(secondStats[1].children[0].textContent,'—','Missing crime metric must render as an em dash');
  assert.equal(facilityRequests,1,'Route planning loads facilities around the selected start');
  assert.equal(get('help-list').children.length,3,get('facility-status').textContent);
  assert.ok(textContent(get('help-list')).includes('straight-line distance'));
  assert.equal(run('state.helpLayers.length'),3,'Distinct facility category markers are created');
  const pharmacyToggle=get('facility-toggles').children[2].children[0];
  pharmacyToggle.checked=false;pharmacyToggle.listeners.change();
  assert.equal(get('help-list').children[2].hidden,true,'Category toggle hides its facility row');
  assert.equal(run('map.hasLayer(state.helpLayers[2].layer)'),false,'Category toggle hides its map marker');
  pharmacyToggle.checked=true;pharmacyToggle.listeners.change();
  assert.equal(run('map.hasLayer(state.helpLayers[2].layer)'),true);

  get('route-cards').children[0].listeners.click();
  assert.equal(run('state.selected'),0,'The user can select a different route');
  get('navigate').listeners.click();
  assert.equal(run('state.watch'),4,'Navigation starts a geolocation watch');
  assert.equal(context.watchOptions.enableHighAccuracy,true);
  assert.equal(get('map-hint').hidden,false,'Distance and ETA remain visible during navigation');
  watchCallback(position(78.001));
  assert.match(get('instruction').textContent,/Turn left in \d+ m/,'Turn distance is measured along the selected route');
  assert.match(get('progress').textContent,/GPS accuracy ±8 m/);
  const stationaryArrowPosition=run('state.lastArrowPosition');
  watchCallback(position(78.00101));
  assert.deepEqual(Array.from(run('state.lastArrowPosition')),Array.from(stationaryArrowPosition),'Small stationary GPS jitter does not move the arrow');
  watchCallback(position(78.0013,17,8,90,2));
  assert.match(arrow.style.transform,/rotate\(90/,'Reliable moving GPS heading rotates the user arrow');
  assert.ok(fakeMap.panCount>0,'Map follow pans to the GPS position');
  get('follow').listeners.click();
  const pansBefore= fakeMap.panCount;
  watchCallback(position(78.002));
  assert.equal(fakeMap.panCount,pansBefore,'Map follow can be disabled');
  get('recenter').listeners.click();
  assert.equal(run('state.followMap'),true,'Recenter enables map follow');
  watchCallback(position(78.006));
  assert.equal(get('instruction').textContent,'Continue to your destination','Passed maneuver advances using route progress');
  watchCallback(position(78.00995));
  assert.equal(get('instruction').textContent,'Near your destination','Arrival proximity is identified');
  watchCallback(position(78.02));
  assert.match(get('instruction').textContent,/off this route/,'Off-route GPS is reported clearly');
  watchCallback(position(78.006,17,120));
  assert.equal(get('instruction').textContent,'GPS accuracy is low','Poor accuracy is reported without advancing turns');
  assert.ok(facilityRequests<=3,'GPS updates do not trigger a Places request on every fix');

  get('stop').listeners.click();
  assert.equal(run('state.watch'),null,'Stopping navigation clears the GPS watch');
  assert.ok(gpsCleared>=1);
  get('route-cards').children[1].listeners.click();
  get('navigate').listeners.click();
  watchCallback(position(78.001));
  assert.equal(get('instruction').textContent,'Turn instructions unavailable','Missing provider instructions do not create a turn');
  get('stop').listeners.click();
  get('navigate').listeners.click();
  watchError({code:1});
  assert.match(get('progress').textContent,/permission denied/i,'Permission denial is explained');
  assert.equal(run('state.watch'),null,'GPS errors clear the active watch');
  assert.equal(get('retry-gps').hidden,false,'GPS failures offer a retry action');
  get('retry-gps').listeners.click();
  get('route-cards').children[1].listeners.click();
  assert.equal(run('state.watch'),null,'Changing routes stops active GPS tracking');
  get('mode').listeners.change();
  assert.equal(run('state.routes.length'),0,'Changing travel mode invalidates routes');
  assert.equal(get('route-section').hidden,true);

  const progress=run("nearestProgress([78.0025,17],{geometry:{type:'LineString',coordinates:[[78,17],[78.005,17],[78.01,17]]}})");
  assert.ok(progress.distance<1,'Route projection finds a point on route geometry');
  assert.ok(progress.along/progress.total>.2&&progress.along/progress.total<.3);
  const html=fs.readFileSync('app/templates/home.html','utf8');
  const css=fs.readFileSync('app/static/style.css','utf8');
  assert.match(html,/id="map-hint"[\s\S]*?id="nav-panel"/,'Navigation overlays are map children for fullscreen use');
  assert.match(css,/\.map-shell\.expanded/,'Fullscreen map overlay styles exist');
  assert.match(css,/@media\(max-width:800px\)/,'Mobile overlay styles exist');
  console.log('Client checks passed: route selection and scores, synthetic GPS heading/progress/errors/cleanup, facility filtering/throttling, fullscreen/mobile overlay contracts.');
})().catch(error=>{console.error(error);process.exitCode=1;});
