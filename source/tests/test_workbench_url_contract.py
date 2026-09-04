import subprocess
from pathlib import Path


def test_url_identity_lifecycle() -> None:
    root = Path(__file__).resolve().parents[1] / "app/static/core"
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"""
      import assert from 'node:assert/strict';
      import {{createWorkbenchState}} from '{(root / "workbenchState.js").as_uri()}';
      import {{createWorkbenchUrlState}} from '{(root / "workbenchUrlState.js").as_uri()}';
      const listeners = new Map(); const registry = new Map(); let failures = 0;
      const env = {{location: new URL('http://local/a?keep=yes&inspect=one#anchor'),
        history: {{state: {{pageId:'a', custom:42}}, replaceState(s, _, url) {{
          this.state=s; env.location = new URL(url, env.location)}}}},
        addEventListener: (k, f) => listeners.set(k,f),
        removeEventListener: k => listeners.delete(k)}};
      const state = createWorkbenchState({{scopeId:'a'}});
      const url = createWorkbenchUrlState({{state, environment:env,
        resolve:id=>registry.get(id), onUnavailable:()=>failures++}});
      state.preview({{id:'other',title:'Other'}});
      url.dataReady({{terminal:false}});
      assert.equal(env.location.searchParams.get('inspect'),'one');
      registry.set('one', {{id:'one',title:'Latest',current:{{value:12}}}});
      url.dataReady(); assert.equal(state.getSnapshot().selection.title,'Latest');
      assert.equal(env.history.state.custom,42); assert.equal(env.location.hash,'#anchor');
      assert.equal(env.location.searchParams.get('keep'),'yes');
      state.setPinned(true); state.preview({{id:'two',title:'Two'}});
      assert.equal(env.location.searchParams.get('inspect'),'one');
      state.clearSelection(); assert.equal(env.location.searchParams.has('inspect'),false);
      env.location.searchParams.set('inspect','missing'); listeners.get('popstate')();
      assert.equal(failures,1); assert.equal(env.location.searchParams.has('inspect'),false);
      state.select(registry.get('one')); url.clearContext();
      assert.equal(state.getSnapshot().isPinned,false);
      env.location = new URL('http://local/b?inspect=keep'); url.dataReady(); url.destroy();
      assert.equal(env.location.searchParams.get('inspect'),'keep'); assert.equal(listeners.size,0);
    """,
        ],
        check=True,
    )
