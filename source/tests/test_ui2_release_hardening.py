"""H0: real conditional HTTP/cache upgrades and command diagnostics."""

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from app.core.http_cache import revalidate_frontend
from scripts.build_private_portable import package_notes

ROOT = Path(__file__).resolve().parents[1]


def test_running_app_installs_revalidation_policy():
    base = os.getenv("BASE_URL", "http://127.0.0.1:8002")
    with httpx.Client(base_url=base, trust_env=False) as client:
        page = client.get("/monitoring-page")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-cache"
        asset = client.get("/static/core/commandRegistry.js")
        assert asset.status_code == 200
        assert asset.headers["cache-control"] == "public, max-age=0, must-revalidate"
        assert (
            client.get(
                "/static/core/commandRegistry.js", headers={"If-None-Match": asset.headers["etag"]}
            ).status_code
            == 304
        )


def fixture_app(directory):
    app = FastAPI()
    app.middleware("http")(revalidate_frontend)
    app.mount("/static", StaticFiles(directory=directory), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def document():
        return (
            '<title>Cache upgrade</title><p id="value"></p>'
            '<script type="module" src="/static/entry.js"></script>'
        )

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    return app


@pytest.fixture
def cache_app(tmp_path):
    (tmp_path / "entry.js").write_text(
        "import {value} from './child.js'; document.querySelector('#value').textContent=value;",
        encoding="utf-8",
    )
    (tmp_path / "child.js").write_text("export const value='release A';", encoding="utf-8")
    return fixture_app(tmp_path)


def test_conditional_http_keeps_validators(cache_app):
    client = TestClient(cache_app)
    assert client.get("/").headers["cache-control"] == "no-cache"
    asset = client.get("/static/child.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=0, must-revalidate"
    for request_header, response_header in [
        ("If-None-Match", "etag"),
        ("If-Modified-Since", "last-modified"),
    ]:
        unchanged = client.get(
            "/static/child.js", headers={request_header: asset.headers[response_header]}
        )
        assert unchanged.status_code == 304
        assert unchanged.headers["cache-control"] == asset.headers["cache-control"]


def test_warm_browser_child_module_upgrade(cache_app, tmp_path):
    # Serve the same production middleware over real HTTP: Playwright route()
    # disables browser caching, so interception cannot prove this contract.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(cache_app, log_level="error", lifespan="off", ws="none")
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.on(
                        "console", lambda m: errors.append(m.text) if m.type == "error" else None
                    )
                    page.on(
                        "response",
                        lambda r: errors.append(str(r.status)) if r.status >= 400 else None,
                    )
                    page.goto(f"http://127.0.0.1:{port}/")
                    expect(page.locator("#value")).to_have_text("release A")
                    child = tmp_path / "child.js"
                    child.write_text("export const value='release B';", encoding="utf-8")
                    # Same-sized content; deterministic mtime change exercises
                    # validators without sleeping for filesystem clock ticks.
                    os.utime(child, (child.stat().st_atime, child.stat().st_mtime + 2))
                    page.reload()
                    expect(page.locator("#value")).to_have_text("release B")
                    page.reload()
                    expect(page.locator("#value")).to_have_text("release B")
                    assert errors == []
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_command_fault_cause_redaction_cancel_and_reentry():
    module = (ROOT / "app/static/core/commandRegistry.js").as_uri()
    script = f"""
      import {{createCommandRegistry}} from {module!r};
      import assert from 'node:assert/strict';
      const r=createCommandRegistry(), logs=[];
      console.error=(...args)=>logs.push(args);
      const cause=new TypeError('https://provider/?api_key=DO_NOT_PRINT Authorization: SECRET');
      cause.stack='TypeError: SECRET\\n at run (http://127.0.0.1/static/pages/analysis.js?v=SECRET:42:7)';
      r.register({{id:'test:fail',label:'失败',run(){{throw cause}}}});
      await assert.rejects(r.run('test:fail'), e=>e.cause===cause && !e.message.includes('SECRET'));
      assert.equal(logs.length,1);
      assert.equal(logs[0][1].id,'test:fail');
      assert.equal(logs[0][1].scope,'global');
      assert.equal(logs[0][1].name,'TypeError');
      assert.deepEqual(logs[0][1].frames,['/static/pages/analysis.js:42:7']);
      assert.ok(!JSON.stringify(logs).includes('DO_NOT_PRINT'));
      assert.ok(!JSON.stringify(logs).includes('SECRET'));
      let reject;
      const controller=new AbortController();
      const scope=r.createScope('analysis',{{signal:controller.signal}});
      scope.register({{id:'analysis:refresh',label:'刷新',run:()=>new Promise((_,r)=>reject=r)}});
      const pending=r.run('analysis:refresh');
      assert.equal(await r.run('analysis:refresh'),false);
      controller.abort(); reject(new DOMException('cancelled','AbortError'));
      assert.equal(await pending,false); assert.equal(logs.length,1);
      // An AbortError without a cancelled scope is a genuine failure.
      r.register({{id:'test:abort',label:'异常取消',run(){{
        throw new DOMException('fault','AbortError')
      }}}});
      await assert.rejects(r.run('test:abort')); assert.equal(logs.length,2);
      assert.equal(r.query('').find(x=>x.id==='test:fail').enabled,true);
      r.destroy();
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("secrets", [True, False])
@pytest.mark.parametrize("encrypted", [True, False])
def test_package_security_notice_uses_manifest(secrets, encrypted):
    notes = package_notes(
        {
            "contains_secrets": secrets,
            "encrypted": encrypted,
            "delivery": "test release",
            "workbench_pages": ["Monitoring", "BTC"],
        }
    )
    assert ("ZIP 已加密" if encrypted else "ZIP 未加密") in notes
    # P0-SEC-001 contract: the False branch must state no credentials are included.
    assert ("包含原样 source/.env 和密钥" if secrets else "不包含任何密钥或凭证") in notes
    assert "Monitoring、BTC" in notes
    assert "Ctrl+Shift+R" in notes
