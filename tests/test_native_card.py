import os
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

CARD = (
    Path(__file__).resolve().parents[1]
    / "custom_components/festavia_studio/frontend/festavia-studio-card.js"
)


class NativeCardTests(unittest.TestCase):
    def test_snake_layers_edit_save_and_preview_independently_on_mobile(self):
        page = self.page
        page.locator("#effect").select_option("snake")
        self.wait_saved()
        background = page.evaluate("state.attributes.scene.colors")
        page.locator("#snake-add").click()
        page.get_by_role("button", name="Choose Warm white", exact=True).click()
        page.get_by_role("button", name="Choose Blue", exact=True).click()
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.colors"), background)
        self.assertEqual(
            page.evaluate("state.attributes.scene.snake_colors"), ["#ffffff", "#2040ff"]
        )
        page.locator("#done").click()
        self.assertIn("Repeats every 9 pucks", page.locator("#snake-note").inner_text())
        page.locator("#palette-save").evaluate("e=>e.open=true")
        page.locator("#save-layer").select_option("snake")
        page.locator("#palette-name").fill("Snake colors")
        page.locator("#save-palette").click()
        page.wait_for_function("()=>calls.at(-1).action==='save_palette'")
        self.assertEqual(page.evaluate("calls.at(-1).data.layer"), "snake")
        page.locator("#snake-palette").select_option("Christmas")
        page.wait_for_function("()=>calls.at(-1).action==='load_palette'")
        self.assertEqual(page.evaluate("calls.at(-1).data.layer"), "snake")
        self.assertEqual(page.evaluate("state.attributes.scene.colors"), background)
        page.evaluate("""()=>{
            const card=document.querySelector('festavia-studio-card');
            cancelAnimationFrame(card.frame);card.animate(0);cancelAnimationFrame(card.frame);
        }""")
        self.assertEqual(
            page.locator(".dot").nth(3).evaluate("e=>e.style.background"), "rgb(255, 0, 0)"
        )
        page.evaluate("""()=>{
            const card=document.querySelector('festavia-studio-card');
            card.animate(4000/9*3);cancelAnimationFrame(card.frame);
        }""")
        self.assertEqual(
            page.locator(".dot").nth(0).evaluate("e=>e.style.background"), "rgb(255, 0, 0)"
        )
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth>innerWidth"))

    def test_extended_static_palette_and_animation_limits_are_clear_on_mobile(self):
        page = self.page
        page.evaluate("""()=>{
            state={...state,attributes:{...state.attributes,palette_limit:27,animated_palette_limit:9}};
            hass={...hass,states:{'sensor.test':state}};
            document.querySelector('festavia-studio-card').hass=hass;
        }""")
        for _ in range(24):
            page.locator("#add").click()
        self.assertTrue(page.locator("#add").is_disabled())
        self.assertEqual(page.locator("[data-color]").count(), 27)
        self.assertTrue(page.locator('#effect option[value="flow"]').is_disabled())
        self.assertIn(
            "Static repeat supports 27 colors",
            page.locator(".studio").inner_text(),
        )
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth>innerWidth"))
        self.wait_saved()
        self.assertEqual(len(page.evaluate("state.attributes.scene.colors")), 27)
        page.locator("#spectrum").click()
        self.wait_saved()
        self.assertEqual(len(set(page.evaluate("state.attributes.scene.colors"))), 27)
        page.get_by_role("button", name="Color 27", exact=True).click()
        for _ in range(18):
            page.locator("#remove").click()
        self.assertFalse(page.locator('#effect option[value="flow"]').is_disabled())
        page.locator("#effect").select_option("flow")
        self.assertTrue(page.locator("#add").is_disabled())

    def test_return_control_to_hue_uses_release_and_preserves_staged_palette(self):
        page = self.page
        page.locator("#power").click()
        page.wait_for_function("()=>state.attributes.playing")
        colors = page.evaluate("state.attributes.scene.colors")
        page.locator("#release").click()
        page.wait_for_function("()=>!state.attributes.playing")
        self.assertEqual(page.evaluate("calls.at(-1).action"), "release")
        self.assertEqual(page.evaluate("state.attributes.scene.colors"), colors)
        self.assertEqual(page.locator("#status").inner_text(), "Hue control")

    def test_current_scene_settings_flush_pending_edits(self):
        page = self.page
        page.locator("#scenes").evaluate("e=>e.open=true")
        page.locator("#effect").select_option("wave")
        page.locator("#preset").dispatch_event("change")
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.effect"), "wave")
        self.assertEqual(
            page.evaluate("calls.slice(-2).map(c=>c.action)"), ["configure", "load_scene"]
        )

    def test_loading_palette_and_deleting_flush_pending_motion_edits(self):
        page = self.page
        page.locator("#effect").select_option("wave")
        page.locator("#palette").select_option("Winter")
        page.wait_for_function("() => state.attributes.palette==='Winter'")
        self.assertEqual(page.evaluate("state.attributes.scene.effect"), "wave")
        self.assertEqual(
            page.evaluate("calls.slice(-2).map(c=>c.action)"), ["configure", "load_palette"]
        )
        page.locator("#palette-save").evaluate("e=>e.open=true")
        page.locator("#effect").select_option("bounce")
        page.locator("#delete-palette").click()
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.effect"), "bounce")
        self.assertEqual(
            page.evaluate("calls.slice(-2).map(c=>c.action)"), ["configure", "delete_palette"]
        )

    def test_quick_color_and_palette_controls_do_not_change_animation(self):
        page = self.page
        page.locator("#effect").select_option("bounce")
        self.wait_saved()
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.get_by_role("button", name="Choose Warm white", exact=True).click()
        page.locator("#done").click()
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.colors[0]"), "#ffdda0")
        page.locator("#palette-save").evaluate("(e)=>e.open=true")
        page.get_by_role("textbox", name="Palette name", exact=True).fill("Holiday colors")
        page.get_by_role("button", name="Save palette", exact=True).click()
        expect(page.locator("#palette")).to_have_value("Holiday colors")
        self.assertTrue(page.locator("#palette-save").evaluate("e=>e.open"))
        self.assertEqual(page.evaluate("calls.at(-1).action"), "save_palette")
        self.assertNotIn("effect", page.evaluate("calls.at(-1).data"))
        page.locator("#palette").select_option("Winter")
        page.wait_for_function("() => state.attributes.palette==='Winter'")
        self.assertEqual(page.evaluate("state.attributes.scene.effect"), "bounce")
        self.assertEqual(page.evaluate("state.attributes.scene.brightness"), 10)
        self.assertFalse(page.evaluate("state.attributes.playing"))
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.get_by_role("button", name="Choose Red", exact=True).click()
        self.wait_saved()
        self.assertEqual(page.locator("#palette").input_value(), "")
        self.assertTrue(page.locator("#delete-palette").is_disabled())

    def test_touch_color_wheel_changes_only_the_selected_color(self):
        page = self.page
        page.get_by_role("button", name="Color 1", exact=True).click()
        bounds = page.locator(".wheel").bounding_box()
        page.touchscreen.tap(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        self.wait_saved()
        self.assertEqual(
            page.evaluate("state.attributes.scene.colors"), ["#ffffff", "#00ff00", "#9900ff"]
        )
        page.touchscreen.tap(bounds["x"] + bounds["width"] - 3, bounds["y"] + bounds["height"] / 2)
        self.wait_saved()
        colors = page.evaluate("state.attributes.scene.colors")
        self.assertEqual(colors[1:], ["#00ff00", "#9900ff"])
        self.assertEqual(max(int(colors[0][i : i + 2], 16) for i in (1, 3, 5)), 255)
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth>innerWidth"))

    def setUp(self):
        self.p = sync_playwright().start()
        self.addCleanup(self.p.stop)
        self.browser = self.p.chromium.launch(
            headless=True, executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        self.page.set_content(
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<style>body{margin:0;background:#18202a;--primary-color:#4ca;--primary-text-color:#eee;--secondary-text-color:#999;--card-background-color:#18202a}</style><festavia-studio-card></festavia-studio-card>"
        )
        self.page.add_script_tag(
            content="""customElements.define('ha-card',class extends HTMLElement {connectedCallback(){this.style.display='block';}});
            customElements.define('ha-switch',class extends HTMLElement {
            connectedCallback(){this.style.cssText='display:block;width:48px;height:40px;background:#555';this.onclick=()=>{if(this.disabled)return;this.checked=!this.checked;this.dispatchEvent(new Event('change'));};}
        });"""
        )
        self.page.add_script_tag(path=str(CARD))
        self.page.evaluate("""() => {
            window.calls=[];window.delay=0;const card=document.querySelector('festavia-studio-card');
            window.state={state:'idle',attributes:{entry_id:'test',scene:{colors:['#ff0000','#00ff00','#9900ff'],brightness:10,speed:1,effect:'static',reverse:false},presets:['Warm'],preset:'Custom',palettes:['Christmas','Winter'],palette:'Custom',snake_palette:'Custom',effects:['static','flow','chase','bounce','color_fade','wave','breathe','heartbeat','snake'],positions:27,palette_limit:9,brightness_limit:15,mode:'native',playing:false}};
            window.hass={states:{'sensor.test':state},callService:async(domain,action,data)=>{
                calls.push({domain,action,data:JSON.parse(JSON.stringify(data))});
                if(delay)await new Promise(r=>setTimeout(r,delay));
                const a={...state.attributes,scene:{...state.attributes.scene}};
                if(action==='configure'||action==='play') {
                    for(const key of ['colors','snake_colors','brightness','speed','effect','reverse'])if(key in data)a.scene[key]=data[key];
                    a.preset='Custom';if('colors' in data && JSON.stringify(data.colors)!==JSON.stringify(state.attributes.scene.colors))a.palette='Custom';
                }
                if(action==='play')a.playing=true;
                if(action==='off'||action==='stop'||action==='release')a.playing=false;
                if(action==='release')a.reason='hue_takeover';
                if(action==='save_palette'){a.palettes=[...a.palettes,data.name];a[data.layer==='snake'?'snake_palette':'palette']=data.name;}
                if(action==='load_palette'){if(data.palette!=='Custom')a.scene[data.layer==='snake'?'snake_colors':'colors']=['#80dfff','#e4f4ff','#4040ff'];a[data.layer==='snake'?'snake_palette':'palette']=data.palette;a.preset='Custom';}
                if(action==='save_scene'){a.presets=[...a.presets,data.name];a.preset=data.name;}
                state={...state,state:a.playing?'playing':'idle',attributes:a};
                hass={...hass,states:{'sensor.test':state}};card.hass=hass;
            }};
            card.setConfig({entity:'sensor.test'});card.hass=hass;
        }""")

    def wait_saved(self):
        self.page.wait_for_function(
            "() => !document.querySelector('festavia-studio-card').dirty && !document.querySelector('festavia-studio-card').saving"
        )

    def test_mobile_palette_autosaves_order_and_power_is_native_switch(self):
        page = self.page
        self.assertTrue(page.locator(".editor").is_hidden())
        self.assertEqual(page.locator(".dot").count(), 27)
        self.assertEqual(page.locator("#brightness").get_attribute("max"), "15")
        self.assertEqual(page.locator("#play,#off").count(), 0)
        page.get_by_role("button", name="Color 2", exact=True).click()
        page.locator(".advanced-color").evaluate("(e)=>e.open=true")
        page.locator("#hex").fill("#1234ff")
        page.locator("#hex").dispatch_event("change")
        page.locator("#left").click()
        page.locator("#add").click()
        page.locator("#effect").select_option("flow")
        self.wait_saved()
        calls = page.evaluate("calls")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["action"], "configure")
        self.assertEqual(calls[0]["data"]["colors"], ["#1234ff", "#ff0000", "#9900ff", "#1234ff"])
        self.assertFalse(page.evaluate("state.attributes.playing"))
        page.locator("#done").click()
        self.assertTrue(page.locator(".editor").is_hidden())
        page.locator("#power").click()
        page.wait_for_function("() => state.attributes.playing")
        self.assertEqual(page.evaluate("calls.at(-1).action"), "play")
        page.locator("#power").click()
        page.wait_for_function(
            "() => !state.attributes.playing && !document.querySelector('festavia-studio-card').busy"
        )
        self.assertEqual([c["action"] for c in page.evaluate("calls")][-2:], ["off", "configure"])
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth>innerWidth"))
        self.assertEqual(page.evaluate("innerWidth"), 390)

    def test_black_hex_does_not_silently_turn_into_white_or_write_lights(self):
        page = self.page
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.locator(".advanced-color").evaluate("(e)=>e.open=true")
        page.locator("#hex").fill("#000000")
        page.locator("#hex").dispatch_event("change")
        self.assertEqual(page.evaluate("state.attributes.scene.colors[0]"), "#ff0000")
        self.assertEqual(page.evaluate("calls.length"), 0)
        self.assertIn("Black gaps", page.locator(".error").inner_text())
        self.assertGreaterEqual(page.locator(".quick").first.bounding_box()["height"], 44)

    def test_live_edits_are_debounced_and_native_palette_tone_stays_valid(self):
        page = self.page
        page.locator("#power").click()
        page.wait_for_function("() => state.attributes.playing")
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.locator(".advanced-color").evaluate("(e)=>e.open=true")
        page.locator("#hex").fill("#804000")
        page.locator("#hex").dispatch_event("change")
        for hue in range(120, 220, 10):
            page.locator("#hue").fill(str(hue))
            page.locator("#hue").dispatch_event("input")
        self.wait_saved()
        calls = page.evaluate("calls.filter(c=>c.action==='configure')")
        self.assertEqual(len(calls), 1)
        colors = calls[-1]["data"]["colors"]
        self.assertTrue(all(max(int(c[i : i + 2], 16) for i in (1, 3, 5)) == 255 for c in colors))
        self.assertTrue(page.evaluate("state.attributes.playing"))
        self.assertEqual(page.locator(".error").inner_text(), "")

    def test_changes_during_a_save_keep_the_latest_color(self):
        page = self.page
        page.evaluate("delay=900")
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.locator(".advanced-color").evaluate("(e)=>e.open=true")
        page.locator("#hex").fill("#ff0000")
        page.locator("#hex").dispatch_event("change")
        page.wait_for_function("() => calls.length===1")
        page.locator("#hex").fill("#0033ff")
        page.locator("#hex").dispatch_event("change")
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.colors[0]"), "#0033ff")
        self.assertEqual(page.evaluate("calls.length"), 2)
        self.assertFalse(page.evaluate("state.attributes.playing"))

    def test_saving_a_named_scene_updates_the_scene_selector_immediately(self):
        page = self.page
        page.locator("#scenes").evaluate("(e)=>e.open=true")
        page.locator("#name").fill("New saved scene")
        page.locator("#save").click()
        expect(page.locator("#preset option")).to_have_count(3)
        self.assertEqual(page.locator("#preset").input_value(), "New saved scene")
        self.assertTrue(page.locator("#scenes").evaluate("e=>e.open"))
        self.assertFalse(page.evaluate("state.attributes.playing"))
