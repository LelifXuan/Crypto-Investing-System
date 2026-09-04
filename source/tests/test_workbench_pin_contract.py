import subprocess
from pathlib import Path


def test_pin_locks_content_but_not_facts_or_explicit_selection() -> None:
    module = Path(__file__).resolve().parents[1] / "app/static/core/workbenchState.js"
    script = f"""
      import {{createWorkbenchState}} from {module.as_uri()!r};
      import assert from 'node:assert/strict';
      const state=createWorkbenchState({{scopeId:'test'}});
      state.setPinned(true); assert.equal(state.getSnapshot().isPinned,false);
      state.select({{id:'a',title:'A',current:{{value:1}}}});
      state.setPinned(true); state.preview({{id:'b',title:'B'}});
      assert.equal(state.getSnapshot().activeSelection.id,'a');
      assert.equal(state.getSnapshot().previewSelection.id,'b');
      state.select({{id:'a',title:'A',current:{{value:2}}}});
      assert.equal(state.getSnapshot().activeSelection.current.value,2);
      assert.equal(state.getSnapshot().isPinned,true);
      state.select({{id:'b',title:'B'}});
      assert.equal(state.getSnapshot().selection.id,'b');
      state.preview({{id:'c',title:'C'}}); state.togglePinned();
      assert.equal(state.getSnapshot().activeSelection.id,'c');
      state.setPinned(true); state.clearSelection({{restoreFocus:false}});
      assert.equal(state.getSnapshot().isPinned,false);
      state.destroy(); state.setPinned(true);
      assert.equal(state.getSnapshot().isPinned,false);
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
