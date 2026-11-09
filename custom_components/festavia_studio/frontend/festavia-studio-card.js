/* Festavia Studio 0.9.0 — dependency-free native Lovelace card. */
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clone = value => JSON.parse(JSON.stringify(value));
function hsv(hex) {
  const [r,g,b] = hex.match(/[a-f0-9]{2}/gi).map(v => parseInt(v,16)/255), max=Math.max(r,g,b), min=Math.min(r,g,b), d=max-min;
  let h=0;
  if(d) h=(max===r ? (g-b)/d+(g<b?6:0) : max===g ? (b-r)/d+2 : (r-g)/d+4)*60;
  return [h, max ? d/max : 0, max];
}
function hex([h,s,v]) {
  const f=n=>{const k=(n+h/60)%6;return Math.round(255*(v-v*s*Math.max(0,Math.min(k,4-k,1)))).toString(16).padStart(2,"0");};
  return `#${f(5)}${f(3)}${f(1)}`;
}
class FestaviaStudioCard extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this.selected=0; this.editing=false; this.dirty=false; this.busy=false; this.saving=null; this.revision=0; }
  static getConfigElement() { return document.createElement("festavia-studio-card-editor"); }
  static getStubConfig(hass) {
    return {entity:Object.keys(hass.states).find(k=>hass.states[k].attributes.entry_id && hass.states[k].attributes.palette_limit)};
  }
  setConfig(config) { this.config=config; this.render(); }
  getCardSize() { return this.editing ? 12 : 7; }
  getGridOptions() { return {columns:12, min_columns:6, rows:"auto"}; }
  set hass(value) {
    this._hass=value;
    const id=this.config?.entity || Object.keys(value.states).find(k=>value.states[k].attributes.entry_id && value.states[k].attributes.palette_limit);
    const state=value.states[id];
    if (!state) { this.state=null; this.render(); return; }
    const changed=JSON.stringify(state.attributes.scene)!==JSON.stringify(this.state?.attributes.scene);
    const metadata = s => s && [s.state === "unavailable", s.attributes.presets, s.attributes.preset, s.attributes.palettes, s.attributes.palette, s.attributes.effects, s.attributes.positions, s.attributes.palette_limit, s.attributes.brightness_limit, s.attributes.mode];
    const metadataChanged=JSON.stringify(metadata(state))!==JSON.stringify(metadata(this.state));
    this.state=state;
    if (!this.dirty && (!this.scene || changed)) { this.scene=clone(state.attributes.scene); this.selected=Math.min(this.selected,this.scene.colors.length-1); this.render(); }
    else if (!this.dirty && metadataChanged) this.render();
    else if (!this.shadowRoot.querySelector(".studio")) this.render();
    this.updateStatus();
  }
  connectedCallback() { if(!this.frame) this.animate(); }
  disconnectedCallback() { cancelAnimationFrame(this.frame); this.frame=0; clearTimeout(this.saveTimer); if(this.dirty && !this.busy)this.flush(); }
  updateStatus() {
    const label=this.shadowRoot.querySelector("#status");
    const body=this.shadowRoot.querySelector(".studio");if(body)body.inert=this.busy;
    const power=this.shadowRoot.querySelector("#power");
    if(power){power.checked=!!this.state?.attributes.playing;power.disabled=this.busy || this.state?.state==="unavailable";}
    if(label) label.textContent=this.state?.state === "unavailable" ? "Unavailable" : this.state ? `${this.state.attributes.playing?"Studio running":this.state.attributes.reason==="hue_takeover"||this.state.attributes.last_hue_takeover?"Hue control":"Studio stopped"}${this.dirty?(this.saveError?" · Could not save":" · Saving…"):""}` : "Unavailable";
  }
  render() {
    if(!this.config) return;
    if(!this.state || !this.scene) { this.shadowRoot.innerHTML='<ha-card><div style="padding:24px">Festavia is unavailable. Check its integration in Settings → Devices & services.</div></ha-card>'; return; }
    const openDetails=[...this.shadowRoot.querySelectorAll("details[id]")].filter(e=>e.open).map(e=>e.id);
    const a=this.state.attributes,s=this.scene,selected=s.colors[this.selected],v=hsv(selected);
    this.shadowRoot.innerHTML=`
    <style>
      :host{display:block}*{box-sizing:border-box}ha-card{overflow:hidden;background:var(--ha-card-background,var(--card-background-color));color:var(--primary-text-color)}
      .studio{padding:20px;display:grid;gap:16px;font:14px var(--paper-font-body1_-_font-family,system-ui)}header{display:flex;align-items:center;justify-content:space-between}h2{margin:0;font-size:22px;font-weight:600}.muted{color:var(--secondary-text-color);font-size:12px;margin-top:5px}label{display:block;font-weight:500;margin-bottom:7px}.row{display:flex;gap:10px;align-items:center}.row>*{min-width:0;flex:1}.controls{display:grid;grid-template-columns:1fr 1fr;gap:14px}
      button,select,input{font:inherit;color:inherit;border:1px solid var(--divider-color,#6665);background:var(--secondary-background-color,#8881);border-radius:12px;padding:12px;min-height:46px}button{cursor:pointer;touch-action:manipulation}button:disabled{opacity:.45;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary-color)}select{width:100%}input[type=range]{width:100%;padding:0;accent-color:var(--primary-color);min-height:34px}input[type=checkbox]{min-height:20px;accent-color:var(--primary-color)}input[type=text]{width:100%;text-transform:uppercase}.pill{border:0;background:var(--primary-color);color:var(--text-primary-color,#fff);font-weight:600}.off{color:var(--error-color,#e56672)}.palette{display:flex;flex-wrap:wrap;gap:10px}.swatch{flex:none;width:44px;height:44px;min-height:44px;border:3px solid transparent;border-radius:50%;padding:0;position:relative}.swatch[aria-pressed=true]{border-color:var(--primary-text-color);box-shadow:0 0 0 2px var(--primary-color)}.swatch span{color:#fff;text-shadow:0 1px 3px #000;font-size:12px}.tools button{padding:10px 6px;font-size:13px}.picker{border:1px solid var(--divider-color,#6665);border-radius:16px;padding:14px;display:grid;gap:12px}.wheel{width:min(100%,260px);aspect-ratio:1;border-radius:50%;position:relative;touch-action:none;justify-self:center;background:radial-gradient(closest-side,white,transparent),conic-gradient(from 90deg,red,#ff0,#0f0,#0ff,#00f,#f0f,red)}.quick-colors{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.quick{border-radius:50%;width:44px;height:44px;min-height:44px;padding:0;justify-self:center;border:2px solid var(--divider-color)}.advanced-color{width:100%}.cursor{position:absolute;width:22px;height:22px;border:2px solid #fff;box-shadow:0 0 2px 1px #000;border-radius:50%;transform:translate(-50%,-50%);pointer-events:none}.hue{background:linear-gradient(to right,red,#ff0,#0f0,#0ff,#00f,#f0f,red)!important;border:0!important;height:20px;appearance:none;min-height:20px!important}.hue::-webkit-slider-thumb{appearance:none;width:24px;height:24px;border:2px solid white;border-radius:50%;background:transparent;box-shadow:0 0 2px #000}.preview{display:flex;gap:4px;overflow:hidden;padding:12px 0;min-height:37px}.dot{flex:1;min-width:4px;height:12px;border-radius:50%;box-shadow:0 0 9px currentColor}.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.actions .pill{grid-column:1/-1}.error{color:var(--error-color);white-space:pre-wrap;font-size:13px}.notice{font-size:12px;color:var(--secondary-text-color)}[hidden]{display:none!important}.power{display:flex;align-items:center;gap:10px}.editor{display:grid;gap:12px}.editor-head{display:flex;align-items:center;justify-content:space-between}.editor-head label{margin:0}.add{width:44px;height:44px;min-height:44px;border-radius:50%;padding:0;font-size:24px}.foot{display:flex;align-items:center;justify-content:space-between}.foot button{border:0;padding:8px;background:transparent;font-size:13px}details summary{cursor:pointer}details .row{margin-top:12px}a{color:var(--primary-color)}@media(max-width:370px){.studio{padding:14px;gap:14px}.tools{flex-wrap:wrap}.tools button{flex:1 0 25%}}
    </style>
    <ha-card><div class="studio">
      <header><div><h2>${esc(this.config.title||"Festavia")}</h2><div id="status" class="muted"></div></div><div class="power"><span>Studio</span><ha-switch id="power" aria-label="Festavia Studio playback"></ha-switch></div></header>
      <div><label for="palette">Color palette</label><select id="palette" aria-label="Color palette"><option value="">Custom colors</option>${(a.palettes||[]).map(p=>`<option ${a.palette===p?"selected":""}>${esc(p)}</option>`).join("")}</select></div>
      <div><div class="row"><label>Colors <span class="muted">· tap to edit</span></label><span style="text-align:right" class="muted">${s.colors.length} / ${a.palette_limit}</span></div><div class="palette">${s.colors.map((c,i)=>`<button class="swatch" style="background:${c}" aria-label="Color ${i+1}" aria-pressed="${this.editing && i===this.selected}" data-color="${i}"><span>${i+1}</span></button>`).join("")}<button id="add" class="add" aria-label="Add color" ${s.colors.length>=a.palette_limit?"disabled":""}>+</button></div></div>
      <div class="editor" ${this.editing?"":"hidden"}><div class="editor-head"><label>Edit color ${this.selected+1}</label><button id="done">Done</button></div><div class="row tools"><button id="left" ${this.selected===0?"disabled":""}>← Move</button><button id="right" ${this.selected===s.colors.length-1?"disabled":""}>Move →</button><button id="remove" ${s.colors.length===1?"disabled":""}>Remove</button></div>
      <div class="picker"><label>Choose a color</label><div class="wheel" role="group" aria-label="Color wheel"><span class="cursor" style="left:${50+Math.cos(v[0]*Math.PI/180)*v[1]*50}%;top:${50+Math.sin(v[0]*Math.PI/180)*v[1]*50}%"></span></div>
      <div class="quick-colors" aria-label="Quick colors">${[["Red","#ff2020"],["Orange","#ff8000"],["Yellow","#ffff00"],["Green","#00ff00"],["Cyan","#00ffff"],["Blue","#2040ff"],["Purple","#9900ff"],["Pink","#ff20a0"],["Warm white","#ffdda0"],["White","#ffffff"]].map(([name,c])=>`<button class="quick" style="background:${c}" data-quick="${c}" aria-label="Choose ${name}"></button>`).join("")}</div>
      <label for="hue">Hue</label><input aria-label="Hue" id="hue" class="hue" type="range" min="0" max="360" value="${v[0]}"><label for="saturation">Saturation</label><input id="saturation" aria-label="Saturation" type="range" min="0" max="100" value="${Math.round(v[1]*100)}">
      <details id="advanced-color" class="advanced-color"><summary>Advanced color</summary><div class="row"><input id="hex" type="text" aria-label="Hex color" maxlength="7" value="${selected}"><span class="muted">#RRGGBB</span></div><label for="tone">${a.mode==="native"?"Shared palette tone":"Color tone"}</label><input id="tone" type="range" min="1" max="100" value="${Math.round(v[2]*100)}"><div class="notice">${a.mode==="native"?"Colors share brightness. Use the main Brightness control for the lights.":""}</div></details></div></div>
      <div class="controls"><div><label for="effect">Animation</label><select id="effect">${a.effects.map(e=>`<option value="${esc(e)}" ${s.effect===e?"selected":""}>${({static:"Static repeat",flow:"Smooth flow",chase:"Step chase",bounce:"Bounce",color_fade:"Color fade",wave:"Color wave",breathe:"Breathing",heartbeat:"Heartbeat"})[e]||esc(e)}</option>`).join("")}</select></div><div><label for="direction">Direction</label><select id="direction"><option value="false" ${!s.reverse?"selected":""}>← Left</option><option value="true" ${s.reverse?"selected":""}>Right →</option></select></div><div><label for="brightness">Brightness <output id="brightness-value">${s.brightness}%</output></label><input id="brightness" type="range" min="1" max="${a.brightness_limit}" value="${s.brightness}"></div><div><label for="speed">Speed <output id="speed-value">${s.speed}×</output></label><input id="speed" type="range" min="0" max="100" step="1" value="${100*Math.log(s.speed/.1)/Math.log(200)}"></div></div>
      <div><div class="muted">Preview · ${a.positions} positions · repeats in your chosen order</div><div class="preview">${Array.from({length:Math.min(100,a.positions)},()=>'<span class="dot"></span>').join("")}</div></div>
      <div class="foot"><span class="muted">Changes save automatically</span><button id="stop">Restore previous scene</button></div>
      <button id="release" ${a.mode==="native"?"":"hidden"}>Return control to Hue</button>
      <div class="error" role="alert"></div>
      <details id="palette-save"><summary>Save these colors</summary><div class="notice">A palette saves colors only. Your animation stays as it is.</div><div class="row"><input id="palette-name" type="text" maxlength="60" aria-label="Palette name" placeholder="Palette name"><button id="save-palette">Save palette</button></div><button id="delete-palette" ${!a.palette||a.palette==="Custom"?"disabled":""}>Delete selected palette</button></details>
      <details id="scenes"><summary>Scenes · colors and animation</summary><div class="notice">A scene saves colors, animation, speed, direction and brightness.</div><label for="preset">Saved scene</label><select id="preset"><option value="">Current settings</option>${a.presets.map(p=>`<option ${a.preset===p?"selected":""}>${esc(p)}</option>`).join("")}</select><div class="row"><input id="name" type="text" maxlength="60" aria-label="Scene name" placeholder="Scene name"><button id="save">Save scene</button></div><button id="delete-scene" ${a.preset==="Custom"?"disabled":""}>Delete selected scene</button></details>
    </div></ha-card>`;
    for(const id of openDetails){const detail=this.shadowRoot.getElementById(id);if(detail)detail.open=true;}
    const $=id=>this.shadowRoot.querySelector(id);
    this.shadowRoot.querySelectorAll("[data-color]").forEach(b=>b.onclick=()=>{this.selected=Number(b.dataset.color);this.editing=true;this.render();});
    $("#add").onclick=()=>{s.colors.push(selected);this.selected=s.colors.length-1;this.editing=true;this.change();this.render();};
    $("#done").onclick=()=>{this.editing=false;this.render();};
    $("#remove").onclick=()=>{s.colors.splice(this.selected,1);this.selected=Math.max(0,this.selected-1);this.change();this.render();};
    for(const [id,delta] of [["left",-1],["right",1]]) $("#"+id).onclick=()=>{[s.colors[this.selected],s.colors[this.selected+delta]]=[s.colors[this.selected+delta],s.colors[this.selected]];this.selected+=delta;this.change();this.render();};
    const updateColor=()=>{
      if(a.mode==="native") {
        v[2]=Math.max(1/255,v[2]);
        s.colors=s.colors.map(c=>{const parts=hsv(c);parts[2]=v[2];return hex(parts);});
      }
      s.colors[this.selected]=hex(v);this.change();
      $("#hex").value=s.colors[this.selected];$("#hue").value=v[0];$("#saturation").value=Math.round(v[1]*100);$("#tone").value=Math.round(v[2]*100);
      $(".cursor").style.left=`${50+Math.cos(v[0]*Math.PI/180)*v[1]*50}%`;$(".cursor").style.top=`${50+Math.sin(v[0]*Math.PI/180)*v[1]*50}%`;
      this.shadowRoot.querySelectorAll("[data-color]").forEach(b=>b.style.background=s.colors[Number(b.dataset.color)]);
    };
    $("#hue").oninput=e=>{v[0]=Number(e.target.value);updateColor();};
    $("#saturation").oninput=e=>{v[1]=Number(e.target.value)/100;updateColor();};
    $("#tone").oninput=e=>{v[2]=Number(e.target.value)/100;updateColor();};
    $("#hex").onchange=e=>{if(/^#[a-f0-9]{6}$/i.test(e.target.value)){const value=hsv(e.target.value);if(a.mode==="native" && value[2]===0){const message="Black gaps are unavailable in puck mode. Use Power to turn the lights off.";e.target.setCustomValidity(message);e.target.reportValidity();e.target.value=s.colors[this.selected];$(".error").textContent=message;return;}e.target.setCustomValidity("");if(a.mode==="native")value[2]=v[2];v.splice(0,3,...value);updateColor();}else e.target.value=s.colors[this.selected];};
    this.shadowRoot.querySelectorAll("[data-quick]").forEach(button=>button.onclick=()=>{const pick=hsv(button.dataset.quick);pick[2]=v[2];v.splice(0,3,...pick);updateColor();});
    const point=e=>{const r=$(".wheel").getBoundingClientRect(),x=e.clientX-r.left-r.width/2,y=e.clientY-r.top-r.height/2;v[0]=(Math.atan2(y,x)*180/Math.PI+360)%360;v[1]=Math.min(1,Math.hypot(x,y)/(r.width/2));updateColor();};
    $(".wheel").onpointerdown=e=>{e.currentTarget.setPointerCapture(e.pointerId);point(e);};
    $(".wheel").onpointermove=e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))point(e);};
    for(const key of ["brightness","speed"]) $("#"+key).oninput=e=>{s[key]=key==="speed"?Math.round(.1*Math.pow(200,Number(e.target.value)/100)*10)/10:Number(e.target.value);$("#"+key+"-value").textContent=s[key]+(key==="brightness"?"%":"×");this.change();};
    $("#effect").onchange=e=>{s.effect=e.target.value;this.change();};
    $("#direction").onchange=e=>{s.reverse=e.target.value==="true";this.change();};
    $("#power").onchange=e=>{const on=e.target.checked;return this.perform(async()=>{
      if(on)await this.service("play",this.changes());
      else {await this.service("off");await this.service("configure",{...this.changes(),apply:false});}
      this.dirty=false;
    });};
    $("#release").onclick=()=>this.perform(async()=>{await this.service("release");if(this.dirty)await this.service("configure",{...this.changes(),apply:false});this.dirty=false;});
    $("#stop").onclick=()=>this.perform(async()=>{await this.service("stop");if(this.dirty)await this.service("configure",{...this.changes(),apply:false});this.dirty=false;});
    $("#preset").onchange=e=>{const name=e.target.value||"Custom";this.perform(async()=>{if(name==="Custom" && this.dirty)await this.service("configure",this.changes());await this.service("load_scene",{preset:name});this.dirty=false;this.scene=null;this.hass=this._hass;});};
    $("#save").onclick=()=>this.perform(async()=>{const name=$("#name").value.trim();if(!name)throw Error("Enter a scene name");await this.service("configure",this.changes());await this.service("save_scene",{name});this.dirty=false;});
    $("#palette").onchange=e=>{const name=e.target.value||"Custom";this.perform(async()=>{if(this.dirty)await this.service("configure",this.changes());await this.service("load_palette",{palette:name});this.dirty=false;this.scene=null;this.hass=this._hass;});};
    $("#save-palette").onclick=()=>this.perform(async()=>{const name=$("#palette-name").value.trim();if(!name)throw Error("Enter a palette name");await this.service("configure",this.changes());await this.service("save_palette",{name});this.dirty=false;});
    $("#delete-palette").onclick=()=>this.perform(async()=>{if(this.dirty)await this.service("configure",this.changes());await this.service("delete_palette",{name:a.palette});this.dirty=false;});
    $("#delete-scene").onclick=()=>this.perform(async()=>{if(this.dirty)await this.service("configure",this.changes());await this.service("delete_scene",{name:a.preset});this.dirty=false;});
    this.updateStatus();
  }
  changes() { const {colors,effect,brightness,speed,reverse}=this.scene;return {colors,effect,brightness,speed,reverse}; }
  change() {
    this.dirty=true;this.saveError=false;this.revision++;this.updateStatus();clearTimeout(this.saveTimer);
    this.saveTimer=setTimeout(()=>this.flush(),600);
  }
  async flush() {
    clearTimeout(this.saveTimer);
    if(!this.dirty)return;
    if(this.busy || this.saving){this.saveTimer=setTimeout(()=>this.flush(),300);return this.saving;}
    const revision=this.revision,changes=clone(this.changes());
    this.saving=this.service("configure",changes);
    try {
      await this.saving;
      if(revision===this.revision){this.dirty=false;this.saveError=false;const preset=this.shadowRoot.querySelector("#preset");if(preset)preset.value=this.state.attributes.preset==="Custom"?"":this.state.attributes.preset;const palette=this.shadowRoot.querySelector("#palette");if(palette)palette.value=this.state.attributes.palette==="Custom"?"":(this.state.attributes.palette||"");const removePalette=this.shadowRoot.querySelector("#delete-palette"),removeScene=this.shadowRoot.querySelector("#delete-scene");if(removePalette)removePalette.disabled=!this.state.attributes.palette||this.state.attributes.palette==="Custom";if(removeScene)removeScene.disabled=this.state.attributes.preset==="Custom";}
      const error=this.shadowRoot.querySelector(".error");if(error)error.textContent="";
    } catch(e) {
      this.saveError=true;
      const error=this.shadowRoot.querySelector(".error");if(error)error.textContent=e.message||String(e);
      this.updateStatus();return;
    } finally {this.saving=null;}
    if(this.dirty)this.saveTimer=setTimeout(()=>this.flush(),600);
    this.updateStatus();
  }
  async service(action,data={}) { await this._hass.callService("festavia_studio",action,{entry_id:this.state.attributes.entry_id,...data}); }
  async perform(fn) {
    if(this.busy)return;this.busy=true;clearTimeout(this.saveTimer);this.updateStatus();
    const error=this.shadowRoot.querySelector(".error");if(error)error.textContent="";
    try {if(this.saving)await this.saving.catch(()=>{});await fn();if(!this.dirty)this.render();}
    catch(e){const target=this.shadowRoot.querySelector(".error");if(target)target.textContent=e.message||String(e);}
    finally {this.busy=false;if(this.dirty)this.saveTimer=setTimeout(()=>this.flush(),600);this.updateStatus();}
  }
  animate(time=0) {
    if(this.scene && this.shadowRoot.querySelector(".preview")) {
      const s=this.scene,colors=s.colors,n=colors.length,t=time/4000*s.speed,d=s.reverse?1:-1;
      this.shadowRoot.querySelectorAll(".dot").forEach((dot,i)=>{
        let p=i;
        if(s.effect==="flow")p+=d*t*n;
        if(s.effect==="chase")p+=d*Math.floor(t*n);
        if(s.effect==="bounce")p+=d*n*(1-Math.abs(2*(t%1)-1));
        if(s.effect==="wave")p+=n/3*Math.sin(2*Math.PI*(t+d*(i%n)/n));
        if(s.effect==="color_fade")p=d*t*n;
        if(!["flow","chase","bounce","wave","color_fade"].includes(s.effect)&&s.reverse)p=(this.state.attributes.positions-1)-i;
        p=((p%n)+n)%n;const index=Math.floor(p),fraction=p-index;
        const rgb=colors[index].slice(1).match(/../g).map(v=>parseInt(v,16)),next=colors[(index+1)%n].slice(1).match(/../g).map(v=>parseInt(v,16));
        const color=`rgb(${rgb.map((v,k)=>Math.round(v*(1-fraction)+next[k]*fraction)).join(",")})`;
        dot.style.color=color;dot.style.background=color;
        const beat=t%1;
        dot.style.opacity=s.effect==="breathe"?.03+.97*(1+Math.sin(t*2*Math.PI))/2:s.effect==="heartbeat"?.06+.94*Math.max(Math.exp(-Math.pow((beat-.2)/.065,2)),.75*Math.exp(-Math.pow((beat-.4)/.085,2))):1;
      });
    }
    this.frame=requestAnimationFrame(t=>this.animate(t));
  }
}
if(!customElements.get("festavia-studio-card")) customElements.define("festavia-studio-card",FestaviaStudioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="festavia-studio-card"))window.customCards.push({type:"festavia-studio-card",name:"Festavia Studio",description:"Ordered Festavia palettes, native effects and mobile color picker",preview:true});

class FestaviaStudioCardEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});}
  setConfig(value){this.config=value;this.render();}
  set hass(value){this._hass=value;this.render();}
  render(){
    if(!this.config||!this._hass)return;
    const entities=Object.keys(this._hass.states).filter(k=>this._hass.states[k].attributes.entry_id && this._hass.states[k].attributes.palette_limit);
    this.shadowRoot.innerHTML=`<style>label{display:block;margin:14px 0 7px}select,input{box-sizing:border-box;width:100%;padding:12px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}</style><label for="entity">Studio Playback entity</label><select id="entity">${entities.map(id=>`<option ${id===this.config.entity?"selected":""}>${esc(id)}</option>`).join("")}</select><label for="title">Title</label><input id="title" value="${esc(this.config.title||"Festavia")}">`;
    for(const key of ["entity","title"])this.shadowRoot.querySelector("#"+key).onchange=e=>{this.config={...this.config,[key]:e.target.value};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:this.config},bubbles:true,composed:true}));};
  }
}
if(!customElements.get("festavia-studio-card-editor"))customElements.define("festavia-studio-card-editor",FestaviaStudioCardEditor);
