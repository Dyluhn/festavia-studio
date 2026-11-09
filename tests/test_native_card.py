import os
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

CARD = (
    Path(__file__).resolve().parents[1]
    / "custom_components/festavia_studio/frontend/festavia-studio-card.js"
)


class NativeCardTests(unittest.TestCase):
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
            "<style>body{margin:0;--primary-color:#4ca;--primary-text-color:#eee;--secondary-text-color:#999;--card-background-color:#18202a}</style><festavia-studio-card></festavia-studio-card>"
        )
        self.page.add_script_tag(
            content="""customElements.define('ha-switch',class extends HTMLElement {
            connectedCallback(){this.style.cssText='display:block;width:48px;height:40px;background:#555';this.onclick=()=>{if(this.disabled)return;this.checked=!this.checked;this.dispatchEvent(new Event('change'));};}
        });"""
        )
        self.page.add_script_tag(path=str(CARD))
        self.page.evaluate("""() => {
            window.calls=[];window.delay=0;const card=document.querySelector('festavia-studio-card');
            window.state={state:'idle',attributes:{entry_id:'test',scene:{colors:['#ff0000','#00ff00','#9900ff'],brightness:10,speed:1,effect:'static',reverse:false},presets:['Warm'],preset:'Custom',effects:['static','flow','breathe'],positions:27,palette_limit:9,brightness_limit:15,mode:'native',playing:false}};
            window.hass={states:{'sensor.test':state},callService:async(domain,action,data)=>{
                calls.push({domain,action,data:JSON.parse(JSON.stringify(data))});
                if(delay)await new Promise(r=>setTimeout(r,delay));
                const a={...state.attributes,scene:{...state.attributes.scene}};
                if(action==='configure'||action==='play') {
                    for(const key of ['colors','brightness','speed','effect','reverse'])if(key in data)a.scene[key]=data[key];
                    a.preset='Custom';
                }
                if(action==='play')a.playing=true;
                if(action==='off'||action==='stop')a.playing=false;
                if(action==='save_preset'){a.presets=[...a.presets,data.name];a.preset=data.name;}
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
        self.assertLess(page.locator("ha-card").bounding_box()["height"], 780)

    def test_live_edits_are_debounced_and_native_palette_tone_stays_valid(self):
        page = self.page
        page.locator("#power").click()
        page.wait_for_function("() => state.attributes.playing")
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.locator("#hex").fill("#804000")
        page.locator("#hex").dispatch_event("change")
        for hue in range(120, 220, 10):
            page.locator("#hue").fill(str(hue))
            page.locator("#hue").dispatch_event("input")
        self.wait_saved()
        calls = page.evaluate("calls.filter(c=>c.action==='configure')")
        self.assertEqual(len(calls), 1)
        colors = calls[-1]["data"]["colors"]
        self.assertTrue(all(max(int(c[i : i + 2], 16) for i in (1, 3, 5)) == 128 for c in colors))
        self.assertTrue(page.evaluate("state.attributes.playing"))
        self.assertEqual(page.locator(".error").inner_text(), "")

    def test_changes_during_a_save_keep_the_latest_color(self):
        page = self.page
        page.evaluate("delay=900")
        page.get_by_role("button", name="Color 1", exact=True).click()
        page.locator("#hex").fill("#ff0000")
        page.locator("#hex").dispatch_event("change")
        page.wait_for_function("() => calls.length===1")
        page.locator("#hex").fill("#0033ff")
        page.locator("#hex").dispatch_event("change")
        self.wait_saved()
        self.assertEqual(page.evaluate("state.attributes.scene.colors[0]"), "#0033ff")
        self.assertEqual(page.evaluate("calls.length"), 2)
        self.assertFalse(page.evaluate("state.attributes.playing"))

    def test_saving_a_named_palette_updates_the_selector_immediately(self):
        page = self.page
        page.locator("details").evaluate("(e)=>e.open=true")
        page.locator("#name").fill("New saved palette")
        page.locator("#save").click()
        expect(page.locator("#preset option")).to_have_count(3)
        self.assertEqual(page.locator("#preset").input_value(), "New saved palette")
        self.assertFalse(page.evaluate("state.attributes.playing"))
