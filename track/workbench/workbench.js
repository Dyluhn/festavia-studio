"use strict";
const release = JSON.parse(document.getElementById("release").textContent);
const el = id => document.getElementById(id);
const labels = {
  "garage-15ft-256":"Garage · 15 ft",
  "small-bed-10ft":"Small bed · 10 ft",
  "reinforced-15ft":"Reinforced · 15 ft",
  "metric-5m":"Metric · 5 m",
  "large-bed-25ft":"Large bed · 25 ft"
};
let archive = null, importId = 0, modelId = 0;
let mode="section", activePlan=null;
let kitName = Object.keys(labels)[0], model = null;
const kit = () => release.examples[kitName];
const prefix = () => "printable-examples/" + kitName + "/";
const option = (select, title, value) => select.add(new Option(title,value));
const fmt = n => Number(n.toFixed(1)).toLocaleString("en-US");
function message(text, bad=false) {
  const node=el("feedback");
  node.hidden=!text;
  node.classList.toggle("error",bad);
  node.textContent=text;
}
function modelLabel(path) {
  const name=path.split("/").pop().replace(".stl","");
  if(name==="joint-test") return "Joint fit test";
  if(name==="nozzle-test") return "Single-nozzle fit test";
  if(name.startsWith("track-")) return "Track section "+Number(name.slice(6));
  if(name.startsWith("plate-")) return "Print plate "+Number(name.slice(6));
  return (name[0].toUpperCase()+name.slice(1)).replaceAll("_"," ");
}
function updateParts() {
  const select=el("part"), previous=select.value;
  select.replaceChildren();
  const groups={};
  for(const path of Object.keys(kit().models)) {
    if(!archive && !release.samples[release.files[prefix()+path][3]]) continue;
    const group=path.startsWith("fit-first/")?"Fit tests":path.startsWith("plates/")?"Packed plates":path.startsWith("parts/track-")?"Track sections":"Hardware";
    if(!groups[group]) {groups[group]=document.createElement("optgroup"); groups[group].label=group; select.append(groups[group]);}
    groups[group].append(new Option(modelLabel(path),path));
  }
  select.value=Array.from(select.options).some(o=>o.value===previous)?previous:kit().sample;
  loadModel();
}
async function inflate(bytes) {
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
async function readMember(path, source=archive) {
  const [offset,count,length,digest]=release.files[path];
  let compressed;
  if(source) compressed=source.subarray(offset,offset+count);
  else {
    const sample=release.samples[digest];
    if(!sample) throw Error("Open the community ZIP to use this file.");
    compressed=Uint8Array.from(atob(sample),c=>c.charCodeAt(0));
  }
  const bytes=await inflate(compressed);
  if(bytes.length!==length) throw Error("Unexpected file length for "+path);
  return bytes;
}
async function hash(bytes) {
  const value=await crypto.subtle.digest("SHA-256",bytes);
  return Array.from(new Uint8Array(value), b=>b.toString(16).padStart(2,"0")).join("");
}
function archiveState() {
  el("source").textContent=archive?"Verified release":mode==="examples"?"Built-in examples":"Offline CAD engine";
  el("source").classList.toggle("ok",!!archive);
  el("openLabel").textContent=archive?"Open another ZIP":"Open desktop example ZIP";
  el("resource").disabled=el("extract").disabled=!archive;
  el("availability").textContent=archive?"All "+Object.keys(kit().models).length+" models are available from your ZIP.":"Open the ZIP to browse every part and packed plate.";
  el("checkText").textContent=archive?"Archive fingerprint and all 630 file checksums match the v0.1.0 release. Extract a file to try it in your own tools.":"Open the desktop example ZIP to verify and extract files for the selected kit. Everything runs on this device.";
}
async function verify(file) {
  if(!file) return;
  const id=++importId;
  archive=null;
  archiveState(); if(mode==="examples")updateParts();
  try {
    if(file.size!==release.size) throw Error("This file has a different size from the v0.1.0 community ZIP. Select the original community download.");
    message("Checking "+file.name+"…");
    const bytes=new Uint8Array(await file.arrayBuffer());
    if(await hash(bytes)!==release.sha) throw Error("The archive fingerprint differs from the v0.1.0 community download.");
    const paths=Object.keys(release.files);
    for(let start=0;start<paths.length;start+=12) {
      if(id!==importId) return;
      await Promise.all(paths.slice(start,start+12).map(async path=>{
        if(await hash(await readMember(path,bytes))!==release.files[path][3]) throw Error("File checksum differs for "+path);
      }));
      if(id!==importId) return;
      message("Checking files · "+Math.min(start+12,paths.length)+" / "+paths.length);
    }
    archive=bytes; switchMode("examples");
    message("Verified "+file.name+" · "+paths.length+" files checked. All five print kits are ready to inspect.");
  } catch(e) {if(id===importId) message(e.message,true);}
}
function save(bytes,name,type="application/octet-stream") {
  const url=URL.createObjectURL(new Blob([bytes],{type}));
  const a=document.createElement("a"); a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
}
function layout() {
  const p=mode==="examples"?kit().plan:activePlan;
  if(!p || mode==="section")return;
  el("lights").textContent=p.lights_mm.length;el("pieces").textContent=p.pieces.length;el("plates").textContent=p.plate_count;
  el("runTitle").textContent=mode==="run"?"Your run · "+p.lights_mm.length+" pucks · "+p.brackets_mm.length+" brackets":labels[kitName];
  el("dimensions").textContent=fmt(p.run_mm)+" mm run  /  "+fmt(p.parameters.light_spacing*(p.parameters.length_unit==="in"?25.4:1))+" mm puck spacing";
  el("material").textContent=p.parameters.bed_x+" × "+p.parameters.bed_y+" mm bed";
  const width=Math.max(210,el("drawing").clientWidth-2), x=n=>8+n/p.run_mm*(width-16);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  function shape(tag,attrs) {
    const node=document.createElementNS(svg.namespaceURI,tag);
    for(const [k,v] of Object.entries(attrs)) node.setAttribute(k,v);
    svg.append(node);return node;
  }
  svg.setAttribute("viewBox","0 0 "+width+" 52");svg.setAttribute("role","img");svg.setAttribute("aria-label",p.lights_mm.length+" pucks, "+p.brackets_mm.length+" brackets and "+p.joints_mm.length+" joints");
  shape("rect",{x:8,y:21,width:width-16,height:12,rx:3,fill:"#dbe4d5"});
  if(mode==="run"){
    const key=el("target").value;
    const selected=key==="auto"?p.pieces.findIndex(q=>q[3].length):key.startsWith("piece-")?Number(key.slice(6))-1:-1;
    if(selected>=0 && p.pieces[selected]) {
      const [start,len]=p.pieces[selected];
      shape("rect",{x:x(start),y:19,width:x(start+len)-x(start),height:16,rx:2,fill:"#b5dc85",stroke:"#427e53"});
    }
    svg.setAttribute("aria-label",svg.getAttribute("aria-label")+". Select a section using the Preview model menu.");
    svg.style.cursor="pointer";
    svg.onclick=e=>{
      const local=(e.clientX-svg.getBoundingClientRect().left)/svg.getBoundingClientRect().width*width;
      const pos=(local-8)/(width-16)*p.run_mm;
      const index=p.pieces.findIndex(q=>pos>=q[0] && pos<=q[0]+q[1]);
      if(index>=0){el("target").value="piece-"+(index+1);schedule(0);}
    };
  }
  for(const n of p.joints_mm) shape("line",{x1:x(n),x2:x(n),y1:21,y2:33,stroke:"#839a88"});
  for(const n of p.brackets_mm) shape("path",{d:"M "+(x(n)-4)+" 9 h 8 l -4 7 z",fill:"#28776b"});
  for(const n of p.lights_mm) shape("circle",{cx:x(n),cy:28,r:Math.min(4,(width-16)/p.lights_mm.length/4),fill:"#d27123"});
  el("drawing").replaceChildren(svg);
}
function refreshKit() {layout();archiveState();updateParts();}
const canvas=el("canvas");
let yaw=-.42,pitch=.68,zoom=1,frame=0;
const redraw=()=>{if(!frame) frame=requestAnimationFrame(()=>{frame=0;draw();});};
function homeView(){yaw=-.42;pitch=.68;zoom=1;redraw();}
function decodeMesh(bytes,bounds) {
  const d=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const count=d.getUint32(80,true);
  if(bytes.length!==84+count*50||!count) throw Error("Invalid binary STL.");
  const centre=bounds[0].map((n,i)=>(n+bounds[1][i])/2);
  const vertices=new Float32Array(count*18);
  const radius=Math.hypot(...bounds[0].map((n,i)=>bounds[1][i]-n))/2;
  for(let t=0;t<count;t++){
    const start=84+t*50, base=t*18;
    for(let v=0;v<3;v++)for(let axis=0;axis<3;axis++){
      vertices[base+v*6+axis]=(d.getFloat32(start+12+v*12+axis*4,true)-centre[axis])/radius;
      vertices[base+v*6+3+axis]=d.getFloat32(start+axis*4,true);
    }
  }
  return {vertices,count};
}
function gpuRenderer(){
  const gl=canvas.getContext("webgl",{alpha:true,antialias:true});
  if(!gl) return null;
  const prog=gl.createProgram();
  for(const [kind,src] of [[gl.VERTEX_SHADER,`attribute vec3 pos,normal; uniform vec3 right,up,eye;uniform vec2 scale;varying float light;
    void main(){gl_Position=vec4(dot(pos,right)*scale.x,dot(pos,up)*scale.y,-dot(pos,eye)*0.5,1.);
    light=.50+.50*max(0.,dot(normalize(normal),normalize(vec3(-.35,-.32,.86))));}`],
    [gl.FRAGMENT_SHADER,`precision mediump float; varying float light;void main(){gl_FragColor=vec4(vec3(.77,.91,.58)*light,1.);}`]]){
    const shader=gl.createShader(kind);gl.shaderSource(shader,src);gl.compileShader(shader);gl.attachShader(prog,shader);
  }
  gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS)) throw Error("3D renderer could not initialize.");
  gl.useProgram(prog);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  for(const [key,offset] of [["pos",0],["normal",12]]){
    const a=gl.getAttribLocation(prog,key);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,3,gl.FLOAT,false,24,offset);
  }
  gl.enable(gl.DEPTH_TEST);const u=Object.fromEntries(["right","up","eye","scale"].map(k=>[k,gl.getUniformLocation(prog,k)]));
  return {load(m){gl.bufferData(gl.ARRAY_BUFFER,m.vertices,gl.STATIC_DRAW);},render(m,r,v,e,s){
    gl.viewport(0,0,canvas.width,canvas.height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.uniform3fv(u.right,r);gl.uniform3fv(u.up,v);gl.uniform3fv(u.eye,e);gl.uniform2fv(u.scale,s);gl.drawArrays(gl.TRIANGLES,0,m.count*3);
  }};
}
const gpu=gpuRenderer();
const context=gpu?null:canvas.getContext("2d");
function draw(){
  const ratio=Math.min(devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*ratio),h=Math.round(canvas.clientHeight*ratio);
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  if(!model||!w||!h)return;
  const c=Math.cos(yaw),s=Math.sin(yaw),a=Math.cos(pitch),b=Math.sin(pitch);
  const right=[c,-s,0],up=[-s*b,-c*b,a],eye=[s*a,c*a,b];
  const ext=model.referenceExtents||model.extents,projected=axis=>axis.reduce((total,n,i)=>total+Math.abs(n)*ext[i],0);
  const fit=.84*Math.min(w/projected(right),h/projected(up))*zoom;
  const scale=[fit/w,fit/h];
  if(gpu){gpu.render(model,right,up,eye,scale);return;}
  context.clearRect(0,0,w,h);
  const verts=model.vertices,faces=[];
  const dot=(i,axis)=>verts[i]*axis[0]+verts[i+1]*axis[1]+verts[i+2]*axis[2];
  for(let i=0;i<verts.length;i+=18){
    if(dot(i+3,eye)<-.001)continue;
    faces.push([dot(i,eye)+dot(i+6,eye)+dot(i+12,eye),i]);
  }
  faces.sort((l,r)=>l[0]-r[0]);
  for(const [,i] of faces){
    const l=.50+.50*Math.max(0,dot(i+3,[-.35,-.32,.86]));
    context.fillStyle="rgb("+[196,232,148].map(k=>Math.round(k*l)).join(",")+")";
    context.beginPath();
    for(let k=0;k<3;k++){const n=i+k*6,x=w/2+dot(n,right)*fit/2,y=h/2-dot(n,up)*fit/2;k?context.lineTo(x,y):context.moveTo(x,y);}
    context.closePath();context.fill();
  }
}
function displayMesh(bytes,bounds,path,title,detail){
    model=decodeMesh(bytes,bounds);
    const dims=bounds[1].map((n,i)=>n-bounds[0][i]);
    model.extents=dims.map(n=>n/Math.hypot(...dims));
    model.bytes=bytes;model.path=path;
    if(mode==="section")model.referenceExtents=[252,56,28].map(n=>n/Math.hypot(...dims));
    if(gpu)gpu.load(model);
    if(mode==="examples")homeView();else redraw();
    el("modelTitle").textContent=title;
    el("bounds").textContent=dims.map(fmt).join(" × ")+" mm";
    el("bodies").textContent=detail;
}
async function loadModel(){
  const id=++modelId,path=el("part").value,meta=kit().models[path]; if(!meta)return;
  el("saveModel").disabled=true;
  try{
    const bytes=await readMember(prefix()+path);
    if(id!==modelId) return;
    displayMesh(bytes,meta.bounds_mm,path,modelLabel(path),meta.bodies+(meta.bodies===1?" body":" bodies"));
    el("saveModel").disabled=false;
  }catch(e){if(id===modelId) message(e.message,true);}
}
let pointer=null;
canvas.onpointerdown=e=>{pointer={id:e.pointerId,x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(pointer?.id===e.pointerId){yaw+=(e.clientX-pointer.x)*.01;pitch=Math.max(-1.5,Math.min(1.5,pitch+(e.clientY-pointer.y)*.01));pointer.x=e.clientX;pointer.y=e.clientY;redraw();}};
canvas.onpointerup=canvas.onpointercancel=()=>{pointer=null;};
canvas.onkeydown=e=>{const dx={ArrowLeft:-.14,ArrowRight:.14},dy={ArrowUp:.14,ArrowDown:-.14};if(e.key in dx||e.key in dy){e.preventDefault();yaw+=dx[e.key]||0;pitch=Math.max(-1.5,Math.min(1.5,pitch+(dy[e.key]||0)));redraw();}};
el("zoomIn").onclick=()=>{zoom=Math.min(3,zoom*1.2);redraw();};
el("zoomOut").onclick=()=>{zoom=Math.max(.35,zoom/1.2);redraw();};
el("reset").onclick=homeView;
el("saveModel").onclick=()=>{if(model)save(model.bytes,kitName+"-"+model.path.split("/").pop(),"model/stl");};
el("archive").onchange=e=>{verify(e.target.files[0]);e.target.value="";};
document.addEventListener("dragover",e=>{e.preventDefault();document.body.classList.add("drop");});
document.addEventListener("dragleave",e=>{if(!e.relatedTarget)document.body.classList.remove("drop");});
document.addEventListener("drop",e=>{e.preventDefault();document.body.classList.remove("drop");verify(e.dataTransfer.files[0]);});
el("extract").onclick=async()=>{
  const value=el("resource").value;
  const path=value==="pdf"?"docs/Festavia-Track-Guide.pdf":prefix()+(value==="3mf"?el("part").value.replace(/\.stl$/,".3mf"):value);
  const name=(value==="pdf"?"":kitName+"-")+path.split("/").pop();
  try{save(await readMember(path),name);}catch(e){message(e.message,true);}
};
for(const [key,title] of Object.entries(labels))option(el("example"),title,key);
el("example").onchange=e=>{kitName=e.target.value;refreshKit();};
el("part").onchange=loadModel;
for(const bed of [...new Set(release.cases.map(r=>r[0]+" × "+r[1]))])option(el("bed"),bed,bed);
for(const [id,index] of [["length",2],["spacing",3]])for(const n of [...new Set(release.cases.map(r=>r[index]))].sort((a,b)=>a-b))option(el(id),n,n);
el("bed").value="256 × 256";el("length").value="180";el("spacing").value="16";
function chosenCase(){return release.cases.find(r=>r[0]+" × "+r[1]===el("bed").value&&r[2]===Number(el("length").value)&&r[3]===Number(el("spacing").value));}
function customConfig(){
  const [bx,by,length,spacing]=chosenCase(),name="run-"+length+"in-"+spacing+"in-"+bx+"x"+by;
  return {schema_version:1,name,parameters:{length_unit:"in",run_length:length,light_spacing:spacing,bed_x:bx,bed_y:by}};
}
function updateCase(){
  const r=chosenCase();el("result").textContent=r[4]+" pucks · "+r[5]+" brackets · "+r[6]+" track sections";
  el("command").textContent="python make_track.py --config "+customConfig().name+".json --output "+customConfig().name+"-output";
}
for(const id of ["bed","length","spacing"])el(id).onchange=updateCase;
el("saveConfig").onclick=()=>{const c=customConfig();save(JSON.stringify(c,null,2)+"\n",c.name+".json","application/json");};
new ResizeObserver(()=>{redraw();layout();}).observe(el("canvas"));
if(typeof DecompressionStream==="undefined"||!globalThis.crypto?.subtle)message("Use a current browser with local file decompression and SHA-256 support.",true);
updateCase();
