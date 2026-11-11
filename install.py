"""Install this clean package through the local Codex plugin CLI."""
import json,shutil,subprocess,sys
from pathlib import Path

def main():
 if sys.version_info<(3,10):raise SystemExit('Python 3.10 or newer is required.')
 cli=shutil.which('codex')
 if not cli:
  for candidate in ('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex','/Applications/Codex.app/Contents/Resources/codex'):
   if Path(candidate).is_file():cli=candidate;break
 if not cli:raise SystemExit('Install a desktop host with Codex local plugin support first.')
 source=Path(__file__).resolve().parent
 base=Path.home()/'.local/share/forge226-local';target=base/'plugins/forge226'
 if target.exists():raise SystemExit('A Forge226 source installation already exists at '+str(target)+'. Ask your agent to update it without replacing athlete data.')
 target.parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
 manifest=base/'.agents/plugins/marketplace.json';manifest.parent.mkdir(parents=True,exist_ok=True)
 manifest.write_text(json.dumps({'name':'forge226-local','interface':{'displayName':'Forge226 Local'},'plugins':[{'name':'forge226','source':{'source':'local','path':'./plugins/forge226'},'policy':{'installation':'AVAILABLE','authentication':'ON_USE'},'category':'Productivity'}]},indent=2))
 subprocess.run([cli,'plugin','marketplace','add',str(base)],check=True)
 subprocess.run([cli,'plugin','add','forge226@forge226-local'],check=True)
 print('Installed locally. Continue in this chat. If tools are not yet visible, your assistant can use the bundled same-chat runtime. Account connections are configured separately.')
if __name__=='__main__':main()
