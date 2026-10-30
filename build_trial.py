"""生成仅含网页必需文件的 GitHub Pages 发布目录。"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'dist'
OUT.mkdir(exist_ok=True)
for name in ('index.html', 'data.json'):
    shutil.copyfile(ROOT / name, OUT / name)
(OUT / '.nojekyll').write_text('')
print(f'发布目录：{OUT}')
