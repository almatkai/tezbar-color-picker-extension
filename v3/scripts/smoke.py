#!/usr/bin/env python3
"""Verify target ZIP inventory and run its real executable without app/toolchain lookup."""
import argparse,hashlib,json,pathlib,stat,tempfile,zipfile
from protocol_test import run
from package import validate_sampler
p=argparse.ArgumentParser();p.add_argument('--archive',type=pathlib.Path,required=True);p.add_argument('--target',choices=['aarch64-apple-darwin','x86_64-pc-windows-msvc'],required=True);a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='package-smoke-') as temp:
 root=pathlib.Path(temp)
 with zipfile.ZipFile(a.archive) as archive:
  m=json.loads(archive.read('extension.json'))
  assert len(archive.namelist())==len(set(archive.namelist()))
  assert set(archive.namelist())==set(m['files'])|{'extension.json'}
  for e in archive.infolist():
   relative=pathlib.PurePosixPath(e.filename)
   assert not relative.is_absolute() and all(x not in ('.','..') and ':' not in x and '\\' not in x for x in relative.parts)
   assert not stat.S_ISLNK(e.external_attr>>16)
   data=archive.read(e)
   if e.filename!='extension.json':assert hashlib.sha256(data).hexdigest()==m['files'][e.filename]
   target=root.joinpath(*relative.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
   target.chmod((e.external_attr>>16)&0o777)
 binary=root/'bin'/('tezbar-'+m['slug']+('.exe' if a.target.startswith('x86_64-pc-windows') else ''));assert binary.is_file()
 if a.target=='aarch64-apple-darwin':assert binary.stat().st_mode & 0o111
 if a.target=='aarch64-apple-darwin':
  helper=root/'resources/sampler/color-picker-helper'
  assert helper.is_file() and helper.stat().st_mode & 0o111, 'Sampler must survive extraction as executable'
  validate_sampler(helper.read_bytes())
 else:
  assert not (root/'resources/sampler/color-picker-helper').exists(), 'Windows package must not carry a stale macOS binary'
 run(binary,root,m['slug'])
