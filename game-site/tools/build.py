#!/usr/bin/env python3
"""Assemble a direct Godot game entry, without copying the source project."""
from pathlib import Path
import argparse, gzip, hashlib, json, re, shutil, subprocess

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=('game.html','game.js','game.wasm','game.pck','game.png','game.icon.png',
         'game.audio.worklet.js','game.audio.position.worklet.js')
FORBIDDEN=re.compile(r'notion\.(?:so|com)|app\.notion\.com|chatgpt\.com/(?:c|g)/|/Users/|PRIVATE KEY|sk-[A-Za-z0-9]{20,}')

def build(runtime, prepared=False, release=''):
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
    if not prepared:
        html=re.sub(r'<script id="public-game-bridge"[^>]*></script>\s*', '', html)
    # Strip any previous release base before computing the new content identity.
    html=re.sub(r'\s*<base\b[^>]*>', '', html, flags=re.IGNORECASE)
    game.write_text(html)
    identity=[(str(p.relative_to(output)),hashlib.sha256(p.read_bytes()).hexdigest())
              for p in sorted(output.rglob('*')) if p.is_file() and p.name!='.game-build-output']
    tag=re.sub(r'[^A-Za-z0-9._-]', '-', release).strip('.-') or 'web'
    release_id='game-'+tag+'-'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:12]
    asset_base='/game-assets/'+release_id+'/'
    html=re.sub(r'(<head\b[^>]*>)', lambda match: match.group(1)+'\n<base href="'+asset_base+'">', html, count=1, flags=re.IGNORECASE)
    game.write_text(html)
    shutil.copyfile(game,output/'index.html')
    # Pin runtime files to one release. Reuse only unchanged runtime sidecars;
    # HTML has a new base URL and must receive fresh compressed copies.
    if prepared:
        for name in RUNTIME:
            if name=='game.html':
                continue
            for suffix in ('.br','.gz'):
                source=runtime/(name+suffix)
                if source.is_file() and not source.is_symlink():
                    shutil.copyfile(source,output/(name+suffix))
    sizes=json.loads(re.search(r'const GODOT_CONFIG = (\{[^\n]+\});',html).group(1))['fileSizes']
    for name,size in sizes.items():
        assert name in RUNTIME and (output/name).stat().st_size==size,f'Export mismatch: {name}'
    for p in tuple(output.rglob('*')):
        if p.is_file() and p.suffix in ('.html','.css','.js','.txt','.md','.svg'):
            assert not FORBIDDEN.search(p.read_text()),f'Private marker: {p.name}'
        if p.is_file() and p.suffix in ('.html','.css','.js','.txt','.md','.svg','.pck','.wasm'):
            data=p.read_bytes()
            if len(data)>1024 and not p.with_name(p.name+'.gz').exists():
                p.with_name(p.name+'.gz').write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
    node=shutil.which('node')
    if node:
        compressor="const fs=require('fs'),z=require('zlib');for(const p of process.argv.slice(1)){fs.writeFileSync(p+'.br',z.brotliCompressSync(fs.readFileSync(p),{params:{[z.constants.BROTLI_PARAM_QUALITY]:11}}));}"
        subprocess.run([node,'-e',compressor,str(game),str(output/'index.html')],check=True)
    files={str(p.relative_to(output)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in sorted(output.rglob('*')) if p.is_file() and p.name!='.game-build-output'}
    (ROOT/'build-manifest.json').write_text(json.dumps({'release':release,'release_id':release_id,'public_url':'https://game.yanhaoo.com/','asset_base':asset_base,'prepared_export':prepared,'files':files},indent=2)+'\n')
    print(f'Built {len(files)} public files for {release_id} in {output}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True,help='Godot Web export directory containing game.html')
    parser.add_argument('--prepared',action='store_true',help='Preserve finished export HTML and reuse its Brotli/gzip sidecars')
    parser.add_argument('--release',default='',help='Release label recorded in the local build manifest')
    args=parser.parse_args()
    build(args.runtime,args.prepared,args.release)
