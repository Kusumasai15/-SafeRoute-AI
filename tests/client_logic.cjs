// Node-based logic checks, not a substitute for real-browser/map/GPS testing.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
class Element {
  constructor(){this.value='';this.textContent='';this.hidden=false;this.children=[];this.listeners={};this.disabled=false;this.classList={toggle(){},contains(){return false;}};}
  addEventListener(event,callback){this.listeners[event]=callback;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(){}
  showModal(){}
  close(){}
  reset(){}
  querySelector(){return new Element();}
}
const elements = new Map();
const get = id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const storage = new Map();
let requests=0, gpsCleared=0;
const context=vm.createContext({
  document:{getElementById:get,querySelector:()=>({content:'test-token'}),createElement:()=>new Element(),querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener(){}},navigator:{geolocation:{clearWatch(){gpsCleared++;}}},
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  fetch:async(path)=>{if(path.startsWith('/api/help'))return{ok:true,json:async()=>({places:[]})};requests++;return{ok:true,json:async()=>({warnings:[],routes:[{id:0,recommended:true,recommendation_reason:'Shortest estimated travel time; distance breaks ties.',preference:'balanced',distance:1000,duration:600,geometry:{type:'LineString',coordinates:[[78,17],[78.01,17.01]]},steps:[]} ]})};},
  setTimeout,clearTimeout,AbortController,console,alert(){},confirm:()=>true,prompt:()=>null,
});
vm.runInContext(fs.readFileSync('app/static/app.js','utf8'),context);
const run=code=>vm.runInContext(code,context);
(async()=>{
  assert.equal(get('map-failure').hidden,false,'Missing Leaflet must show a map error');
  assert.equal(run('minutes(3600)'),'1 h 0 min');
  assert.equal(run('km(1500)'),'1.5 km');
  run("state.start={lat:17,lng:78,label:'Start'};state.end={lat:17.01,lng:78.01,label:'End'};");
  get('mode').value='walk';
  await get('plan-form').listeners.submit({preventDefault(){}});
  assert.equal(requests,1,'Valid planning sends one backend request');
  assert.equal(run('state.routes.length'),1);
  assert.equal(get('route-section').hidden,false);
  assert.equal(get('route-cards').children.length,1);
  assert.ok(get('route-cards').children[0].children.some(child=>child.textContent==='Recommended'));
  run('state.watch=4;');
  get('mode').listeners.change();
  assert.equal(gpsCleared,1,'Changing travel mode stops old GPS watch');
  assert.equal(run('state.routes.length'),0,'Changing mode invalidates the displayed journey');
  assert.equal(get('route-section').hidden,true);
  await get('plan-form').listeners.submit({preventDefault(){}});
  get('end').value='Different place';
  get('end').listeners.input();
  assert.equal(run('state.end'),null,'Editing address invalidates its old coordinates');
  assert.equal(get('route-section').hidden,true);
  get('end').value='';get('end').listeners.input();
  await get('plan-form').listeners.submit({preventDefault(){}});
  assert.equal(requests,2,'Unselected destination must not issue a route request');
  run("saveContacts([{name:'Primary',phone:'+919876543210'}]);renderContacts();");
  assert.equal(get('contact-list').children.length,1);
  assert.equal(get('emergency-contacts').children[0].href,'tel:+919876543210');
  storage.set('safewalk-contacts','broken JSON');assert.equal(run('contacts().length'),0);
  const progress=run('nearestProgress([78.005,17],[[78,17],[78.01,17]])');
  assert.ok(progress.distance<1,'Route projection should find a point on the route');
  assert.ok(progress.along/progress.total>.49&&progress.along/progress.total<.51,'Mid-route progress should be near half');
  run("state.routes=[{distance:1000,duration:600,geometry:{type:'LineString',coordinates:[[78,17],[78.01,17]]},steps:[{index:1,text:'Turn left',point:[78.005,17]}]}];state.selected=0;");
  run("updateNavigation({coords:{longitude:78.003,latitude:17,accuracy:5}})");
  assert.match(get('instruction').textContent,/^Turn left in \d+ m$/,'Navigation instruction should include distance to the next turn');
  assert.match(get('map-hint').textContent,/remaining Â· \d+ min estimated$/,'Bottom map summary should show remaining distance and ETA');
  console.log('Client logic checks passed: planning, stale-route invalidation, GPS cleanup, contacts, map-load failure and route progress.');
})().catch(error=>{console.error(error);process.exitCode=1;});
