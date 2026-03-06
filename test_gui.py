import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8765")

        # Test focus on clear
        # Click "Text" tab
        page.click('button[id="tabText"]')

        # Type something
        page.fill('textarea[id="inputArea"]', 'C G Am F')
        page.click('button[id="convertBtn"]')

        # Wait for result
        page.wait_for_selector('.output-box.has-result', state='visible')

        # Test aria-pressed on filter chips
        chip = page.locator('.fb-filter-chip').first
        chip.wait_for(state='attached')
        print(f"Initial aria-pressed: {chip.get_attribute('aria-pressed')}")

        # Only click if we can see it
        try:
            chip.wait_for(state='visible', timeout=2000)
            chip.click()
            print(f"After click aria-pressed: {chip.get_attribute('aria-pressed')}")
            chip.click()
            print(f"After second click aria-pressed: {chip.get_attribute('aria-pressed')}")
        except:
            print("Could not interact with chip visually, but it is attached")
            # We can still trigger click via JS
            page.evaluate('(el) => el.click()', chip.element_handle())
            print(f"After click aria-pressed: {chip.get_attribute('aria-pressed')}")


        # Click clear
        page.click('button[class="btn-clear"]')

        # Check if inputArea is focused
        is_focused = page.evaluate('document.activeElement.id === "inputArea"')
        print(f"Is inputArea focused after clear: {is_focused}")

        page.screenshot(path="/home/jules/verification/gui_test.png")
        browser.close()

if __name__ == "__main__":
    run()
