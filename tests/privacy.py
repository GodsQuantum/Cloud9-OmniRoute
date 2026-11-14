#!/usr/bin/env python3
from pathlib import Path
import subprocess,re,hashlib,json,xml.etree.ElementTree as ET,struct,zlib
root=Path(__file__).resolve().parents[1]
files=[x for x in subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().split(chr(0)) if x]
blocked=[re.compile(x,re.I) for x in (
 'a'+'rezki','chou'+'gar','kech'+'idi','fe'+'lla',
 r'arezkichougar[.]com',r'home[.]arpa',
 r'192[.]168[.]',r'@gmail[.]com',r'@hotmail[.]com',
 r'github_pat_[A-Za-z0-9_]{20,}',r'ghp_[A-Za-z0-9]{25,}',r'-----BEGIN PRIVATE KEY',
 r'/srv/lxc/',r'/home/'+'arezki',
)]
bad=[]
for name in files:
 if name=='tests/privacy.py':continue
 path=root/name
 if path.suffix.lower() in ('.png','.jpg','.jpeg'):continue
 if path.is_file() and path.stat().st_size<600000 and any(p.search(path.read_text(errors='replace')) for p in blocked):
  bad.append(name)
assert not bad,('PRIVATE_IDENTIFIERS_IN_PUBLIC_SOURCE',bad)
lock=json.loads((root/'upstream-lock.json').read_text())
patches=lock['patches'];assert len(patches)==4
assert all(hashlib.sha256((root/x['file']).read_bytes()).hexdigest()==x['sha256'] for x in patches)
for name in ('docs/logo.svg','docs/architecture.svg'):ET.parse(root/name)
for name in ('README.md','README.fr.md','README.zh-CN.md','LICENSE'):assert (root/name).is_file()
for name in ('cloud9-engine.png','cloud9-speaches.png'):
 data=(root/'assets'/name).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
 pos=8;types=[]
 while pos<len(data):
  n=struct.unpack('>I',data[pos:pos+4])[0]
  t=data[pos+4:pos+8];value=data[pos+8:pos+8+n]
  assert zlib.crc32(t+value)&0xffffffff==struct.unpack('>I',data[pos+n+8:pos+n+12])[0]
  types.append(t);pos+=12+n
  if t==b'IEND':break
 assert b'IDAT' in types and b'IEND' in types
 assert not any(t in types for t in (b'tEXt',b'iTXt',b'zTXt',b'eXIf'))
code=(root/'overlays/apply-cloud9-source-compat.py').read_text()
assert 'geminiInlineMultiImageParts' in code
assert 'isDedicatedCodexImageModel' in code
assert 'processIsAlive' in code
assert '68f04eeb-180b' not in code
print('OMNIROUTE_PUBLIC_HISTORY_AND_FOUR_OVERLAYS_PRIVACY_ICONS_LOCK_EN_FR_ZH_PASS')
