import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_palette_is_scoped_to_page_actions_not_navigation() -> None:
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    palette = (ROOT / "app/static/ui/commandPalette.js").read_text(encoding="utf-8")

    assert "commands.register({ id: `nav:" not in main
    assert "搜索当前页面操作" in palette
    assert 'registry.query("").length === 0' in palette
    assert "workbench-command-trigger" not in main
    assert 'commandButton.textContent = "命令"' not in main


def test_registry_scope_search_execution_and_disposal() -> None:
    module = (ROOT / "app/static/core/commandRegistry.js").as_uri()
    script = f"""
      import {{createCommandRegistry}} from {module!r};
      import assert from 'node:assert/strict';
      const registry = createCommandRegistry();
      const controller = new AbortController();
      const scope = registry.createScope('monitoring', {{signal:controller.signal}});
      let enabled = false, called = 0, done;
      registry.register({{id:'nav:btc',label:'BTC 衍生品',keywords:['funding'],run(){{called++}}}});
      scope.register({{id:'refresh',label:'刷新监控',enabled:()=>enabled,
        run:()=>new Promise(r=>{{done=r;called++}})}});
      scope.register({{id:'hidden',label:'隐藏',visible:false,run(){{throw Error('hidden')}}}});
      assert.equal(registry.query('').length,2);
      assert.equal(registry.query('funding')[0].id,'nav:btc');
      assert.equal(registry.query('刷新')[0].id,'refresh');
      assert.throws(()=>registry.register({{id:'nav:btc',label:'重复',run(){{}}}}));
      assert.equal(await registry.run('refresh'),false);
      enabled=true;
      const pending=registry.run('refresh');
      assert.equal(await registry.run('refresh'),false);
      assert.equal(called,1); done(); await pending;
      controller.abort();
      assert.equal(registry.query('').length,1);
      assert.equal(await registry.run('refresh'),false);
      scope.destroy(); registry.destroy();
      assert.equal(registry.query('').length,0);
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
