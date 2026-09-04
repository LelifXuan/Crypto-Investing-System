import subprocess
from pathlib import Path


def test_width_contract() -> None:
    module = (Path(__file__).resolve().parents[1] / "app/static/ui/inspectorResize.js").as_uri()
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"""
      import assert from 'node:assert/strict';
      import {{widthBounds, clampWidth, readPreferredWidth}} from '{module}';
      assert.deepEqual(widthBounds(2560), {{min:320,max:520}});
      assert.equal(clampWidth(700, 1200), 504);
      assert.equal(clampWidth(0, 2560), 320);
      for (const value of [null, '', 'bad', '0', '319', '521'])
        assert.equal(readPreferredWidth({{getItem:()=>value}}), null);
      assert.equal(readPreferredWidth({{getItem:()=> '480'}}), 480);
      assert.equal(readPreferredWidth({{getItem:()=>{{throw Error('denied')}}}}), null);
    """,
        ],
        check=True,
    )
