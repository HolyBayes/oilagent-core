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
    for key in ['ANALYST_MCP_TOKEN','EVOLUTION_MCP_TOKEN','LLM_BRIDGE_TOKEN','RUNNER_TOKEN']:
        text=text.replace(f'{key}=\n', f'{key}={secrets.token_urlsafe(32)}\n')
    p.write_text(text)
    p.chmod(0o600)
deploy=Path(os.getenv('DEPLOY_WORKSPACE','workspace/container'))
text=p.read_text()
for key in ['ANALYST_MCP_TOKEN','EVOLUTION_MCP_TOKEN','LLM_BRIDGE_TOKEN','RUNNER_TOKEN']:
    if not any(line.startswith(key+'=') for line in text.splitlines()):
        text+='\n'+key+'=\n'
    text=text.replace(f'{key}=\n', f'{key}={secrets.token_urlsafe(32)}\n')
p.write_text(text)
p.chmod(0o600)
for name in ['rag','reports','models','prices','traces','sessions','releases',
             'evolution-runtime','init','container-native','certificates','llm']:
    (deploy/name).mkdir(parents=True,exist_ok=True)
values=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))
files=Path(os.getenv('USER_FILES_PATH') or values.get('USER_FILES_PATH','workspace/files').strip('"\''))
from scripts.prepare_storage import prepare_storage
# Old bind mounts must be quiescent before moving their contents.
if any((deploy/name).is_dir() and not (deploy/name).is_symlink()
       and any((deploy/name).iterdir()) for name in ['reports','prices','models']):
    import subprocess
    subprocess.run(['docker','compose','stop'],check=True,
                   env={**os.environ, 'RUNNER_IMAGE':'oilagent-executor:local'})
prepare_storage(Path.cwd(),deploy,files)
from scripts.prepare_submodules import prepare
prepare(os.getenv('EVOLUTION_REPO_PATH') or (values.get('EVOLUTION_REPO_PATH') or '../evolution').strip(chr(34)+chr(39)),
        Path('workspace/submodules.compose.json'))
ca=os.getenv('GIGACHAT_CA_BUNDLE_FILE') or values.get('GIGACHAT_CA_BUNDLE_FILE','').strip('"\'')
container_ca=''
if ca:
    shutil.copyfile(ca, deploy/'certificates/ca.pem')
    container_ca='/certificates/ca.pem'
import subprocess
subprocess.run(['docker','build','--provenance=false','-f','runner/Dockerfile.service','-t','oilagent-executor:local','.'],check=True)
worker_image=subprocess.check_output(['docker','image','inspect','oilagent-executor:local','--format','{{.Id}}'],text=True).strip()
Path('workspace/container.env').write_text('CONTAINER_CA_BUNDLE_FILE='+container_ca+'\nRUNNER_IMAGE='+worker_image+'\n')
PY
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
exec ./compose.sh up --build "$@"
