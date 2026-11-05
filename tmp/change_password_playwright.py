import asyncio
import json
import os
import secrets
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = os.environ.get("CHANGE_PASSWORD_BASE_URL", "http://host.docker.internal:8080")
ADMIN_PASSWORD = os.environ["CHANGE_PASSWORD_ADMIN_CURRENT"]
VIEWPORTS = [(1920, 1080), (1440, 900), (1366, 768), (768, 900), (390, 844)]
ARTIFACT_DIR = Path("/workspace/docs/validation/security/change-password")


async def main():
    result = {"viewports": [], "checks": {}, "page_errors": [], "console_errors": [], "http_5xx": [], "change_password_http": []}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_dir = ARTIFACT_DIR / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        page.on("console", lambda message: result["console_errors"].append(message.text) if message.type == "error" else None)
        page.on("response", lambda response: result["http_5xx"].append({"status": response.status, "url": response.url.split("?")[0]}) if response.status >= 500 else None)
        page.on("response", lambda response: result["change_password_http"].append(response.status) if response.url.endswith("/api/auth/change-password") else None)
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.locator("#userButton").click()
        await page.locator("#loginEmail").fill("admin@local")
        await page.locator("#loginPassword").fill(ADMIN_PASSWORD)
        await page.locator("#loginForm button[type=submit]").click()
        await page.locator("#loginDialog").wait_for(state="hidden")
        result["checks"]["authenticated_ui_login"] = True

        for width, height in VIEWPORTS:
            await page.set_viewport_size({"width": width, "height": height})
            await page.locator("#userButton").click()
            menu = page.locator("#accountMenu")
            await menu.get_by_role("menuitem", name="تغيير كلمة المرور").click()
            dialog = page.locator("#changePasswordDialog")
            await dialog.wait_for(state="visible")
            fit = await page.evaluate("""() => {
              const dialog=document.querySelector('#changePasswordDialog');
              const r=dialog.getBoundingClientRect();
              const doc=document.documentElement;
              return {horizontal:doc.scrollWidth<=doc.clientWidth,dialogInside:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,
                inputs:[...dialog.querySelectorAll('input')].every(el=>!!el.labels?.length),
                controlsVisible:[...dialog.querySelectorAll('input,button')].every(el=>{const x=el.getBoundingClientRect();return x.width>0&&x.height>0&&x.left>=r.left&&x.right<=r.right;})};
            }""")
            assert fit["horizontal"], f"horizontal overflow at {width}x{height}"
            assert fit["dialogInside"], f"dialog clipped at {width}x{height}"
            assert fit["inputs"] and fit["controlsVisible"], f"form control clipping/labels at {width}x{height}"
            assert await dialog.get_by_label("كلمة المرور الحالية", exact=True).is_visible()
            assert await dialog.get_by_label("كلمة المرور الجديدة", exact=True).is_visible()
            assert await dialog.get_by_label("تأكيد كلمة المرور الجديدة", exact=True).is_visible()
            result["viewports"].append({"width": width, "height": height, "rtl": await page.locator("html").get_attribute("dir") == "rtl", "form_visible": True, "horizontal_overflow": not fit["horizontal"], "dialog_clipped": not fit["dialogInside"], "labels_attached": fit["inputs"], "controls_visible": fit["controlsVisible"]})
            await page.screenshot(path=str(screenshot_dir / f"{width}x{height}.png"), full_page=False)
            await page.locator("#cancelPasswordChange").click()
            await dialog.wait_for(state="hidden")

        test_password = "Ahsa-Test-" + secrets.token_urlsafe(20)
        page.on("request", lambda request: None)
        await page.set_viewport_size({"width": 1920, "height": 1080})
        async def open_form():
            await page.locator("#userButton").click()
            await page.locator("#openChangePassword").click()
            await page.locator("#changePasswordDialog").wait_for(state="visible")

        await open_form()
        await page.locator("#currentPassword").fill("intentionally-wrong-current")
        await page.locator("#newPassword").fill(test_password)
        await page.locator("#confirmNewPassword").fill(test_password)
        async with page.expect_response(lambda response: response.url.endswith("/api/auth/change-password")) as wrong_response:
            await page.locator("#saveNewPassword").click()
        wrong_response = await wrong_response.value
        assert wrong_response.status == 401, f"wrong-current request returned HTTP {wrong_response.status}; safe detail: {(await wrong_response.json()).get('detail')}"
        wrong_error = (await page.locator("#changePasswordError").inner_text()).strip()
        if wrong_error != "كلمة المرور الحالية غير صحيحة":
            raise AssertionError(f"Unexpected safe error feedback: {wrong_error}; endpoint statuses: {result['change_password_http']}; page errors: {result['page_errors']}; console errors: {result['console_errors']}")
        result["checks"]["wrong_current_rejected"] = True

        await page.locator("#currentPassword").fill(ADMIN_PASSWORD)
        await page.locator("#confirmNewPassword").fill(test_password + "-mismatch")
        await page.locator("#saveNewPassword").click()
        await page.get_by_text("كلمتا المرور غير متطابقتين", exact=True).wait_for(state="visible")
        result["checks"]["mismatch_blocked"] = True

        old_cookie = (await context.cookies(BASE_URL))
        old_token = next(cookie["value"] for cookie in old_cookie if cookie["name"] == "alahsa_session")
        await page.locator("#confirmNewPassword").fill(test_password)
        async with page.expect_response(lambda response: response.url.endswith("/api/auth/change-password")) as change_response:
            await page.locator("#saveNewPassword").click()
        response = await change_response.value
        assert response.status == 200, f"password change HTTP {response.status}"
        await page.get_by_text("تم تغيير كلمة المرور بنجاح", exact=True).wait_for(state="visible")
        new_cookie = next(cookie["value"] for cookie in await context.cookies(BASE_URL) if cookie["name"] == "alahsa_session")
        assert new_cookie != old_token, "session cookie was not rotated"
        result["checks"]["change_succeeded"] = True
        result["checks"]["session_cookie_rotated"] = True

        api = await playwright.request.new_context(base_url=BASE_URL)
        old_login = await api.post("/api/auth/login", data={"email": "admin@local", "password": ADMIN_PASSWORD})
        new_login = await api.post("/api/auth/login", data={"email": "admin@local", "password": test_password})
        assert old_login.status == 401 and new_login.status == 200
        protected = await api.get("/api/admin/users")
        assert protected.status == 200
        result["checks"]["old_login_rejected"] = True
        result["checks"]["new_login_passed"] = True
        result["checks"]["admin_protected_access"] = True

        await page.locator("#changePasswordDialog").wait_for(state="hidden")
        await open_form()
        await page.locator("#currentPassword").fill(test_password)
        await page.locator("#newPassword").fill(ADMIN_PASSWORD)
        await page.locator("#confirmNewPassword").fill(ADMIN_PASSWORD)
        async with page.expect_response(lambda response: response.url.endswith("/api/auth/change-password")) as restore_response:
            await page.locator("#saveNewPassword").click()
        response = await restore_response.value
        assert response.status == 200
        await page.get_by_text("تم تغيير كلمة المرور بنجاح", exact=True).wait_for(state="visible")
        result["checks"]["credential_restored_after_test"] = True
        await api.post("/api/auth/logout")
        restored = await api.post("/api/auth/login", data={"email": "admin@local", "password": ADMIN_PASSWORD})
        assert restored.status == 200
        await api.post("/api/auth/logout")
        result["checks"]["preexisting_credential_remains_usable"] = True
        test_credential_rejected = await api.post("/api/auth/login", data={"email": "admin@local", "password": test_password})
        assert test_credential_rejected.status == 401
        final_login = await api.post("/api/auth/login", data={"email": "admin@local", "password": ADMIN_PASSWORD})
        assert final_login.status == 200
        await api.post("/api/auth/logout")
        result["checks"]["test_credential_not_left_active"] = True
        await api.dispose()

        result["checks"]["rtl"] = await page.locator("html").get_attribute("dir") == "rtl"
        expected_auth_console = [message for message in result["console_errors"] if "401 (Unauthorized)" in message]
        unexpected_console = [message for message in result["console_errors"] if "401 (Unauthorized)" not in message]
        result["expected_auth_401_console_count"] = len(expected_auth_console)
        result["unexpected_console_errors"] = unexpected_console
        result["javascript_errors"] = len(result["page_errors"])
        result["checks"]["javascript_errors_zero"] = not result["page_errors"]
        result["checks"]["unexpected_console_errors_zero"] = not unexpected_console
        result["checks"]["http_5xx_zero"] = not result["http_5xx"]
        await context.close()
        await browser.close()
    output = json.dumps(result, ensure_ascii=False, indent=2)
    (ARTIFACT_DIR / "change-password-playwright.json").write_text(output, encoding="utf-8")
    print(output)


asyncio.run(main())
