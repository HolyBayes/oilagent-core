#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import secrets
import os
import shutil
p=Path('.env')
if not p.exists():
    text=Path('.env.example').read_text()
    for kind in ['ANALYST','EVOLUTION']:
        text=text.replace(f'{kind}_MCP_TOKEN=\n', f'{kind}_MCP_TOKEN={secrets.token_urlsafe(32)}\n')
    p.write_text(text)
    p.chmod(0o600)
deploy=Path(os.getenv('DEPLOY_WORKSPACE','workspace/container'))
text=p.read_text()
for kind in ['ANALYST','EVOLUTION']:
    text=text.replace(f'{kind}_MCP_TOKEN=\n', f'{kind}_MCP_TOKEN={secrets.token_urlsafe(32)}\n')
p.write_text(text)
p.chmod(0o600)
for name in ['rag','reports','models','prices','traces','sessions','releases',
             'evolution-runtime','init','container-native','certificates','llm']:
    (deploy/name).mkdir(parents=True,exist_ok=True)
# Reuse already downloaded public assets; init still verifies the PDF hashes.
for name in ['reports','models']:
    cached=Path('workspace')/name
    target=deploy/name
    if cached.is_dir() and cached.resolve()!=target.resolve():
        def missing_only(source,names):
            destination=target/Path(source).relative_to(cached)
            return [n for n in names if n=='.locks' or n.endswith('.incomplete')
                    or (destination/n).is_file() or (destination/n).is_symlink()]
        shutil.copytree(cached,target,dirs_exist_ok=True,symlinks=True,ignore=missing_only)
values=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))
ca=os.getenv('GIGACHAT_CA_BUNDLE_FILE') or values.get('GIGACHAT_CA_BUNDLE_FILE','').strip('"\'')
container_ca=''
if ca:
    shutil.copyfile(ca, deploy/'certificates/ca.pem')
    container_ca='/certificates/ca.pem'
Path('workspace/container.env').write_text('CONTAINER_CA_BUNDLE_FILE='+container_ca+'\n')
PY
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
exec docker compose --env-file .env --env-file workspace/container.env up --build "$@"
