// The browser runs the release model in a worker so edits can cancel expensive renders.
let engineURL, worker=null, generation=0, debounce, deadline, lastDesign=null;
let previousUnit="in";
const byMode=Object.fromEntries([...document.querySelectorAll("[data-mode]")].map(b=>[b.dataset.mode,b]));
const b64=s=>Uint8Array.from(atob(s),ch=>ch.charCodeAt(0));
const font=b64(release.font);
function workerURL(){
  if(!engineURL)engineURL=(async()=>{
    const blob=new Blob([b64(el("runtime").textContent.trim())]);
    const js=await new Response(blob.stream().pipeThrough(new DecompressionStream("gzip"))).blob();
    return URL.createObjectURL(new Blob([js,"\n",el("cadWorker").textContent],{type:"text/javascript"}));
  })();
  return engineURL;
}
function stopRender(){
  generation++;clearTimeout(debounce);clearTimeout(deadline);
  worker?.terminate();worker=null;lastDesign=null;modelId++;
  el("customStl").disabled=el("customSettings").disabled=el("saveMakerWorld").disabled=true;
}
function status(text,bad=false){el("customStatus").textContent=text;el("customStatus").classList.toggle("error",bad);}
function enableFields(){
  const component = el("component").value;
  const smallPart = ["siding-shim","flat-clip","round-clip"].includes(component);
  el("small_part_copies").disabled = !smallPart;
  if (!smallPart) el("small_part_copies").value = "1";
  el("accessoryHint").textContent = component.startsWith("cable-")
    ? "Export one cable box base and one matching v2 lid per box."
    : component.startsWith("psu-")
      ? "Export one cradle and one v2 cover. Add up to two shims for uneven backing. The cover needs about 242 mm plus bed clearance."
      : "Choose the quantity for your route. Include clips already on your track plates when counting.";
  el("walls").hidden=el("structure_profile").value!=="custom";
  el("first_light_offset").disabled=el("light_placement").value!=="fixed";
  el("light_mm").disabled=!el("has_light").checked;
  el("mount_mm").disabled=!el("has_mount").checked;
  el("support_gap").disabled=!el("single_nozzle").checked;
}
function paramsFromForm(){
  const runFields=["length_unit","run_length","light_spacing","light_margin_min","bed_x","bed_y","light_placement","bracket_spacing_max","bracket_end_max","bracket_centres_mm","start_gate","end_gate","clips_flat","clips_round","spare_percent","engrave_numbers","group_supported_pieces"];
  const pieceFields=["piece_length","left_end","right_end","has_light","has_mount"];
  const keys=["structure_profile","fit_profile","single_nozzle",...(mode==="run"?runFields:pieceFields)];
  if(el("single_nozzle").checked)keys.push("support_gap");
  if(el("structure_profile").value==="custom")keys.push("side_wall","face_skin");
  if(mode==="run"&&el("light_placement").value==="fixed")keys.push("first_light_offset");
  const result={};
  function number(id){
    const field=el(id);
    if(!Number.isFinite(field.valueAsNumber)||!field.checkValidity())throw Error((field.labels[0]?.firstChild.textContent.trim()||id)+" · "+(field.validationMessage||"Enter a number."));
    return field.valueAsNumber;
  }
  if(mode==="accessories"){
    return {
      component:el("component").value,
      small_part_copies:el("small_part_copies").disabled ? 1 : number("small_part_copies"),
      bed_x:number("accessoryBedX"), bed_y:number("accessoryBedY")
    };
  }
  for(const key of keys){
    const field=el(key);
    result[key]=field.type==="checkbox"?field.checked:field.type==="number"?number(key):field.value.trim();
  }
  if(mode==="section"){
    for(const [key,on] of [["light","has_light"],["mount","has_mount"]]){
      if(!result[on])continue;
      const n=number(key+"_mm");
      result[key+"_offset"]=Math.abs(n);result[key+"_side"]=n<0?"left":"right";
    }
  }else{
    if(result.bracket_centres_mm&&!/^\d+(\.\d+)?(\s*,\s*\d+(\.\d+)?)*$/.test(result.bracket_centres_mm))throw Error("Enter bracket centres as comma-separated distances in mm.");
    if(result.light_spacing*(result.length_unit==="in"?25.4:1)<304.8-1e-6||result.light_spacing*(result.length_unit==="in"?25.4:1)>533.4+1e-6)throw Error("Puck spacing must be 12–21 in (304.8–533.4 mm).");
  }
  return result;
}
function updateUnits(){
  const next=el("length_unit").value;
  if(previousUnit===next)return;
  for(const key of ["run_length","light_spacing","light_margin_min","bracket_spacing_max","bracket_end_max","first_light_offset"]){
    const f=el(key);if(Number.isFinite(f.valueAsNumber))f.value=Number((f.valueAsNumber*(next==="mm"?25.4:1/25.4)).toFixed(9));
  }
  previousUnit=next;
}
function invalidate(text){
  document.querySelector(".viewer").classList.add("pending");el("modelTitle").textContent=text;
  el("bounds").textContent="—";el("bodies").textContent="";
}
function schedule(delay=240){
  stopRender();enableFields();
  if(mode==="examples")return;
  activePlan=null;el("layoutCard").hidden=true;
  const token=generation;let params;
  try{params=paramsFromForm();}catch(e){invalidate("Check dimensions");status(e.message,true);return;}
  invalidate("Updating geometry…");status("Calculating your "+(mode==="section"?"section":mode==="accessories"?"accessory":"layout")+"…");
  debounce=setTimeout(async()=>{
    function terminate(){clearTimeout(deadline);worker?.terminate();worker=null;}
    function fail(reason){if(token!==generation)return;terminate();invalidate("Check design");status(reason,true);}
    try{
      const url=await workerURL();if(token!==generation)return;
      worker=new Worker(url);
      worker.onerror=e=>fail(e.message||"The browser could not start the OpenSCAD worker.");
      worker.onmessage=({data})=>{
        if(token!==generation)return;
        if(data.error){fail(data.error);return;}
        if(data.plan){
          activePlan=data.plan;el("layoutCard").hidden=false;
          const select=el("target");select.replaceChildren();
          for(const [key,name] of data.choices)option(select,name,key);
          select.value=data.key;layout();status(activePlan.pieces.length+" sections · "+activePlan.plate_count+" plates. Rendering selected model…");
          return;
        }
        terminate();
        try{
          const filename=(mode==="section"?"custom-section":data.name.toLowerCase().replaceAll(" ","-"))+".stl";
          displayMesh(data.mesh,data.bounds,filename,data.name,fmt(data.volume/1000)+" cm³");
          lastDesign={params,overrides:data.overrides,filename,bytes:data.mesh};
          document.querySelector(".viewer").classList.remove("pending");
          el("customStl").disabled=el("customSettings").disabled=el("saveMakerWorld").disabled=false;
          status(mode==="accessories"?"Preview updated · "+params.small_part_copies+" on this plate":mode==="run"?activePlan.pieces.length+" sections · "+activePlan.plate_count+" plates · "+activePlan.lights_mm.length+" pucks":"Preview updated · "+fmt(params.piece_length)+" mm section");
        }catch(e){fail(e.message);}
      };
      deadline=setTimeout(()=>fail("This render timed out. Try a single section or a shorter run."),180000);
      worker.postMessage({mode,params,target:el("target").value,source:mode==="accessories"?release.makerworld.accessories:release.source,font});
    }catch(e){fail(e.message);}
  },delay);
}
function switchMode(next){
  stopRender();mode=next;activePlan=null;const examples=mode==="examples",run=mode==="run";
  for(const [key,b] of Object.entries(byMode))b.setAttribute("aria-pressed",String(key===mode));
  el("examplesPanel").hidden=el("examplesFiles").hidden=!examples;
  el("editor").hidden=el("outputs").hidden=examples;
  el("layoutCard").hidden=!examples;
  const accessories=mode==="accessories";
  el("accessoryInputs").hidden=!accessories;
  el("trackSettings").hidden=el("customSettings").hidden=accessories;
  el("sectionInputs").hidden=mode!=="section";el("runInputs").hidden=el("targetBox").hidden=!run;
  el("editorTitle").textContent=accessories?"Boxes and cable clips":run?"Run dimensions":"Section dimensions";
  el("customSettings").textContent=run?"Save run JSON ↓":"Save editable SCAD ↓";
  document.querySelector(".workspace").classList.toggle("editing",!examples);
  document.querySelector(".viewer").classList.remove("pending");homeView();
  if(examples)refreshKit();else {archiveState();schedule(0);}
}
for(const [key,b] of Object.entries(byMode))b.onclick=()=>switchMode(key);
el("params").onsubmit=e=>e.preventDefault();
el("params").oninput=e=>{
  if(e.target.id==="length_unit")updateUnits();
  if(e.target.id==="lengthSlider")el("piece_length").value=e.target.value;
  if(e.target.id==="piece_length"&&e.target.value)el("lengthSlider").value=e.target.value;
  schedule();
};
el("target").onchange=()=>schedule(0);
el("customStl").onclick=()=>{if(lastDesign)save(lastDesign.bytes,lastDesign.filename,"model/stl");};
el("customSettings").onclick=()=>{
  if(!lastDesign)return;
  if(mode==="run"){
    save(JSON.stringify({schema_version:1,name:"custom-run",parameters:lastDesign.params},null,2)+"\n","custom-run.json","application/json");return;
  }
  let source=release.source;
  for(const [key,value] of Object.entries({...lastDesign.params,...lastDesign.overrides})){
    const assignment=new RegExp("^"+key+" = [^;]+;","m");
    source=source.replace(assignment,()=>key+" = "+JSON.stringify(value)+";");
  }
  save(source,"custom-section.scad","text/plain");
};

// Preserve decimal spinbox precision in the MakerWorld editor even when the
// current measurement happens to be a whole number.
function makerWorldSource(mode, params) {
  const values = {...params};
  if (mode === "run") {
    const factor = values.length_unit === "in" ? 25.4 : 1;
    delete values.length_unit;
    for (const key of ["run_length", "light_spacing", "light_margin_min", "first_light_offset", "bracket_spacing_max", "bracket_end_max"]) {
      if (key in values) values[key] = Number((values[key] * factor).toFixed(9));
    }
  }
  const [controls, body] = release.makerworld[mode].split("/* [Hidden] */");
  let settings = controls;
  for (const [key, value] of Object.entries(values)) {
    const assignment = new RegExp("^" + key + " = ([^;]+);", "m");
    if (!assignment.test(settings)) throw Error("Missing MakerWorld setting: " + key);
    settings = settings.replace(assignment, (_, original) => {
      let literal = JSON.stringify(value);
      if (typeof value === "number" && original.includes(".") && !literal.includes("e")) {
        const places = (original.split(".")[1] || "").length;
        if ((literal.split(".")[1] || "").length < places) literal = value.toFixed(places);
      }
      return key + " = " + literal + ";";
    });
  }
  return settings + "/* [Hidden] */" + body;
}
el("saveMakerWorld").onclick = () => {
  if (!lastDesign) return;
  const name = {run:"Festavia-Run.scad",section:"Festavia-Section.scad",accessories:"Festavia-Accessories.scad"}[mode];
  save(makerWorldSource(mode, lastDesign.params), name, "text/plain");
};
switchMode("section");
