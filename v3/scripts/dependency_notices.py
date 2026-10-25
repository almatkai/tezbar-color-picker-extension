#!/usr/bin/env python3
"""Regenerate notices from the exact locked Cargo dependency source graph."""
import json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
metadata=json.loads(subprocess.check_output(['cargo','metadata','--locked','--format-version','1'],cwd=ROOT))
notices=[]
for package in sorted(metadata['packages'],key=lambda p:(p['name'],p['version'])):
 if package['name'] in ('tezbar-color-picker','tezbar-timers'):continue
 directory=pathlib.Path(package['manifest_path']).parent
 paths=[p for p in directory.iterdir() if p.is_file() and p.name.lower().startswith(('license','licence','copying','copyright','notice'))]
 if package.get('license_file'):
  declared=pathlib.Path(package['license_file'])
  if not declared.is_absolute():declared=directory/declared
  if declared.is_file() and declared not in paths:paths.append(declared)
 notices.append('\n'+'='*72+'\n'+package['name']+' '+package['version']+'\nSPDX: '+str(package.get('license'))+'\nSource: '+str(package.get('repository') or package.get('source'))+'\n')
 for path in sorted(paths):notices.append('\n--- '+path.name+' ---\n'+path.read_text(encoding='utf-8',errors='replace')+'\n')
 if not paths:notices.append('No separate license file in published crate; SPDX metadata above is retained.\n')
(ROOT/'licenses/rust-dependencies-NOTICES.txt').write_text('Locked Rust dependency notices (including target-specific crates).\n'+''.join(notices),encoding='utf-8')
print(json.dumps({'packages':len(metadata['packages'])-1,'notices':'licenses/rust-dependencies-NOTICES.txt'}))
