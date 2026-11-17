#!/usr/bin/env python3
"""Assemble public portal + a Godot web export, without copying the source project."""
from pathlib import Path
import argparse, gzip, hashlib, json, re, shutil

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=('game.html','game.js','game.wasm','game.pck','game.png','game.icon.png',
         'game.audio.worklet.js','game.audio.position.worklet.js')
FORBIDDEN=re.compile(r'notion\.(?:so|com)|app\.notion\.com|chatgpt\.com/(?:c|g)/|/Users/|PRIVATE KEY|sk-[A-Za-z0-9]{20,}')

def build(runtime):
    runtime=runtime.resolve()
    assert runtime.is_dir(),'Export a Godot Web build first'
    for name in RUNTIME[:4]:
        assert (runtime/name).is_file() and not (runtime/name).is_symlink(),name
    output=ROOT/'dist'
    assert not output.is_symlink()
    if output.exists():
        assert (output/'.game-build-output').is_file(),'Refusing to remove an unowned directory'
        shutil.rmtree(output)
    output.mkdir();(output/'.game-build-output').touch()
    for name in RUNTIME:
        source=runtime/name
        if source.exists():
            assert not source.is_symlink(),name
            shutil.copyfile(source,output/name)
    for source in (ROOT/'public').rglob('*'):
        assert not source.is_symlink(),source
        if source.is_file():
            target=output/source.relative_to(ROOT/'public')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    game=output/'game.html';html=game.read_text()
    html=re.sub(r'<script id="public-game-bridge"[^>]*></script>\s*', '', html)
    game.write_text(html)
    shutil.copyfile(game,output/'index.html')
    sizes=json.loads(re.search(r'const GODOT_CONFIG = (\{[^\n]+\});',html).group(1))['fileSizes']
    for name,size in sizes.items():
        assert name in RUNTIME and (output/name).stat().st_size==size,f'Export mismatch: {name}'
    for p in tuple(output.rglob('*')):
        if p.is_file() and p.suffix in ('.html','.css','.js','.txt','.md','.svg'):
            assert not FORBIDDEN.search(p.read_text()),f'Private marker: {p.name}'
        if p.is_file() and p.suffix in ('.html','.css','.js','.txt','.md','.svg','.pck','.wasm'):
            data=p.read_bytes()
            if len(data)>1024:
                p.with_name(p.name+'.gz').write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
    files={str(p.relative_to(output)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in sorted(output.rglob('*')) if p.is_file() and p.name!='.game-build-output'}
    (ROOT/'build-manifest.json').write_text(json.dumps({'files':files},indent=2)+'\n')
    print(f'Built {len(files)} public files in {output}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True,help='Godot Web export directory containing game.html')
    build(parser.parse_args().runtime)
