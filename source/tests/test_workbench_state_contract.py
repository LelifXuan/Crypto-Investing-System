from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "static" / "core" / "workbenchState.js"


def test_workbench_state_commit_preview_and_clear_contract() -> None:
    script = f"""
      import {{ createWorkbenchState }} from {MODULE.as_uri()!r};
      const state = createWorkbenchState({{ scopeId: 'pilot' }});
      const seen = [];
      state.subscribe((snapshot) => seen.push(snapshot));
      state.preview({{ id: 'hover', title: 'Hover' }});
      if (state.getSnapshot().selection !== null) throw new Error('preview committed');
      state.select({{ id: 'funding', title: 'Funding' }});
      if (state.getSnapshot().selection.id !== 'funding') throw new Error('selection missing');
      if (state.getSnapshot().previewSelection !== null) throw new Error('preview not cleared');
      state.clearSelection({{ restoreFocus: false }});
      if (state.getSnapshot().selection !== null) throw new Error('selection not cleared');
      if (seen.length < 4) throw new Error('subscriber did not observe lifecycle');
      state.destroy();
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_store_does_not_use_process_global_selection() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "createWorkbenchState" in source
    assert "let selection = null" in source
    assert "globalThis" not in source
