// Appended to the bundled OpenSCAD runtime in an isolated worker.
self.onmessage = async ({data}) => {
  try {
    const {source, font, mode, params, target} = data;
    async function generate(params, planOnly) {
      const logs = [];
      const record = line => logs.push(String(line));
      const cad = (await createOpenSCAD({print:record, printErr:record})).getInstance();
      for (const path of ["/fonts","/etc","/etc/fonts","/usr","/usr/local","/usr/local/etc","/usr/local/etc/fonts"]) {
        try {cad.FS.stat(path);} catch {cad.FS.mkdir(path);}
      }
      const fc = '<fontconfig><dir>/fonts</dir><cachedir>/tmp</cachedir></fontconfig>';
      for(const path of ["/etc/fonts/fonts.conf","/usr/local/etc/fonts/fonts.conf","/fonts/fonts.conf"])cad.FS.writeFile(path,fc);
      cad.FS.writeFile("/fonts/LiberationSans-Bold.ttf",font);
      cad.FS.writeFile("/track.scad",source);
      const output = planOnly ? "/track.echo" : "/track.stl";
      const args = ["--backend=manifold","--export-format",planOnly?"echo":"binstl","-o",output];
      for (const [k,v] of Object.entries(params)) args.push("-D",k+"="+JSON.stringify(v));
      const exit = cad.callMain([...args,"/track.scad"]);
      if (planOnly) {
        try {logs.push(...cad.FS.readFile(output,{encoding:"utf8"}).split(/\r?\n/));} catch {}
      }
      const failure = logs.find(s=>/^(ERROR|WARNING):/.test(s));
      if(exit || failure) {
        const assertion=failure?.match(/failed: "([^"]+)"/);
        throw Error(assertion?.[1] || failure || "OpenSCAD could not generate this design.");
      }
      if (!planOnly) return cad.FS.readFile(output,{encoding:"binary"}).slice();
      function echo(key) {
        const marker='ECHO: "'+key+' ';
        const text=logs.find(s=>s.startsWith(marker));
        if(!text)throw Error("OpenSCAD did not return a layout.");
        return JSON.parse(text.slice(marker.length,-1));
      }
      const [run_mm,lights_mm,brackets_mm,joints_mm,,sections,plate_count]=echo("PLAN_JSON");
      const [hardware,,,,,face,wall]=echo("KIT_JSON");
      const unit=params.length_unit==="in"?25.4:1;
      const first=params.light_placement==="fixed"?params.first_light_offset:params.light_margin_min;
      const requested=Math.floor((params.run_length-first-params.light_margin_min)/params.light_spacing+1e-9)+1;
      if(lights_mm.length!==requested) throw Error("These measurements cannot retain all "+requested+" pucks. Change the spacing, margins or bed size.");
      if(sections.some(s=>s[1]>Math.min(240,Math.max(params.bed_x,params.bed_y)-16)+.011))throw Error("A generated section exceeds the bed limit.");
      if(run_mm<=0 || Math.abs(run_mm-params.run_length*unit)>.11)throw Error("Run length differs from the requested measurement.");
      return {run_mm,lights_mm,brackets_mm,joints_mm,pieces:sections,plate_count,hardware,face,wall,parameters:params};
    }
    let overrides={part:"custom_piece"}, name="Custom section";
    if(mode==="accessories"){
      overrides={};name=params.component.replaceAll("-"," ");
    }
    if(mode==="run"){
      const plan=await generate({...params,part:"plan"},true);
      const firstHolder=plan.pieces.findIndex(s=>s[3].length)+1;
      const choices=[["auto","First puck section"]];
      for(let i=1;i<=plan.pieces.length;i++)choices.push(["piece-"+i,"Section "+i+" · "+plan.pieces[i-1][1]+" mm"]);
      for(let i=1;i<=plan.plate_count;i++)choices.push(["plate-"+i,"Packed plate "+i]);
      for(const [part,n,spares] of plan.hardware)if(n+spares>0)choices.push([part,part.replaceAll("_"," ")]);
      const key=choices.some(c=>c[0]===target)?target:"auto";
      if(key==="auto"||key.startsWith("piece-")){
        const i=key==="auto"?firstHolder:Number(key.slice(6));
        overrides={part:"piece",piece_number:i};name="Track section "+i;
      }else if(key.startsWith("plate-")){
        const i=Number(key.slice(6));
        overrides={part:"plate",plate_number:i};name="Packed plate "+i;
      }else{overrides={part:key};name=key.replaceAll("_"," ");}
      self.postMessage({plan,choices,key});
    }
    const mesh=await generate({...params,...overrides},false);
    const stl=new DataView(mesh.buffer,mesh.byteOffset,mesh.byteLength);
    const n=stl.getUint32(80,true);
    if(!n||mesh.length!==84+n*50)throw Error("OpenSCAD returned an empty or incomplete STL.");
    const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    let volume=0;
    for(let i=0;i<n;i++){
      const start=84+i*50+12,xyz=[];
      for(let v=0;v<9;v++){const x=stl.getFloat32(start+4*v,true),j=v%3;xyz.push(x);lo[j]=Math.min(lo[j],x);hi[j]=Math.max(hi[j],x);}
      const [ax,ay,az,bx,by,bz,cx,cy,cz]=xyz;
      volume+=(ax*(by*cz-bz*cy)+ay*(bz*cx-bx*cz)+az*(bx*cy-by*cx))/6;
    }
    if(!Number.isFinite(volume)||volume<=0)throw Error("Generated mesh has invalid volume.");
    self.postMessage({mesh,bounds:[lo,hi],volume,name,overrides},[mesh.buffer]);
  }catch(e){self.postMessage({error:e?.message||"OpenSCAD stopped while generating this geometry."});}
};
