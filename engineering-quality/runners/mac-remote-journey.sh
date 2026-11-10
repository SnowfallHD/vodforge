#!/bin/zsh
# Runs release_journey.py on another Mac over Tailscale and copies the result back.
#
#   engineering-quality/runners/mac-remote-journey.sh <tailscale-machine> <user> <VODForge.app> <local-result-folder>
#
# Example (the Intel test Mac):
#   engineering-quality/runners/mac-remote-journey.sh intel-mac qa-user dist/VODForge.app /tmp/intel-journey
#
# JOURNEY=deletion_journey.py runs the deletion journey instead of the release one.
#
# - The remote host key is pinned from what Tailscale reports for that machine,
#   kept in a file inside the result folder; your known_hosts is not changed.
# - Everything on the remote Mac goes under ~/VODForgeQA: the app copy, the
#   harness, a private Python (uv; nothing is installed system-wide) and the run.
#   The Mac's own VODForge install and profile are not touched.
# - The remote user must be logged in at the desktop, and processes started over
#   SSH need Accessibility permission there (the script checks and stops if not).
set -euo pipefail
[[ $# -eq 4 ]] || { sed -n 2,6p "$0"; exit 64; }
machine=$1 user=$2 app=${3%/} out=$4
journey=${JOURNEY:-release_journey.py}
here=${0:A:h}
mkdir -p "$out"

ip=$(tailscale ip -4 "$machine")
tailscale status --json | /usr/bin/python3 -c '
import json, sys
machine, ip = sys.argv[1], sys.argv[2]
for peer in json.load(sys.stdin).get("Peer", {}).values():
    if peer.get("HostName", "").lower() == machine or peer.get("DNSName", "").startswith(machine + "."):
        if not peer.get("Online"):
            sys.exit(f"{machine} is offline in Tailscale")
        for key in peer.get("sshHostKeys") or []:
            print(ip, key)
        break
else:
    sys.exit(f"{machine} not found in Tailscale")
' "$machine" "$ip" > "$out/known_hosts"
[[ -s "$out/known_hosts" ]] || { echo "Tailscale reports no SSH host key for $machine"; exit 1; }
cat > "$out/ssh_config" <<EOF
Host remote
  HostName $ip
  User $user
  BatchMode yes
  ConnectTimeout 15
  ServerAliveInterval 20
  UserKnownHostsFile $out/known_hosts
  StrictHostKeyChecking yes
EOF
r=(ssh -F "$out/ssh_config" remote)

arch=$("${r[@]}" 'uname -m')
echo "remote: $machine ($arch, macOS $("${r[@]}" sw_vers -productVersion))"
"${r[@]}" 'mkdir -p ~/VODForgeQA/tools ~/VODForgeQA/journey/eq'
rsync -a --delete -e "ssh -F $out/ssh_config" --exclude __pycache__ \
  "$here/../quality_harness" "$here/../runners" remote:VODForgeQA/journey/eq/
rsync -a --delete -e "ssh -F $out/ssh_config" "$app" remote:VODForgeQA/journey/

"${r[@]}" "cd ~/VODForgeQA && export UV_CACHE_DIR=\$PWD/uvcache UV_PYTHON_INSTALL_DIR=\$PWD/pythons UV_NO_MODIFY_PATH=1
  uv=tools/uv-$arch-apple-darwin/uv
  if [[ ! -x \$uv ]]; then
    curl -fsSL https://github.com/astral-sh/uv/releases/download/0.9.7/uv-$arch-apple-darwin.tar.gz | tar -xz -C tools
  fi
  [[ -x venv/bin/python ]] || \$uv venv -q --python 3.13 venv
  \$uv pip install -q --python venv/bin/python 'pyobjc-framework-Quartz>=11,<13' 'pyobjc-framework-ApplicationServices==12.2.2' 'psutil>=7,<8'
  venv/bin/python -c 'import ApplicationServices as a, sys; sys.exit(0 if a.AXIsProcessTrusted() else \"Accessibility permission is missing for SSH sessions on this Mac\")'
  codesign --verify --deep --strict journey/${app:t}"

set +e
"${r[@]}" "cd ~/VODForgeQA/journey && rm -rf result && PYTHONPATH=eq ../venv/bin/python eq/runners/$journey --app \$PWD/${app:t} --output \$PWD/result" | tee "$out/run.log"
code=${pipestatus[1]}
set -e
rsync -a -e "ssh -F $out/ssh_config" remote:VODForgeQA/journey/result/ "$out/result/" || true
"${r[@]}" "pgrep -f 'VODForgeQA/journey/${app:t}' >/dev/null && echo 'WARNING: a test app is still running on $machine' || true"
echo "result: $out/result (exit $code)"
exit $code
