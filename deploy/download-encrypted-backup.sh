#!/usr/bin/env bash
# Operator-invoked, encrypted off-site snapshot download (no production changes).
set -euo pipefail
umask 077

: "${YH_BACKUP_SSH_TARGET:?Set approved SSH user@host}"
: "${YH_BACKUP_SSH_KEY:?Set private key path}"
: "${YH_BACKUP_KNOWN_HOSTS:?Set verified known_hosts path}"
: "${YH_BACKUP_DIR:?Set a private local output directory}"
: "${YH_AGE_RECIPIENT:?Set trusted age1... public recipient; do not put private decryption keys here}"

for tool in ssh age; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Required tool missing: $tool" >&2; exit 2; }
done
[[ -f "$YH_BACKUP_SSH_KEY" && -f "$YH_BACKUP_KNOWN_HOSTS" ]] || {
  echo "Missing SSH key or verified known_hosts" >&2
  exit 2
}
# Guard against accidental plaintext backup in git checkout.
case "$(cd "$(dirname "$YH_BACKUP_DIR")" 2>/dev/null && pwd -P)/$(basename "$YH_BACKUP_DIR")" in
  */.private/*|*/.private) ;;
  *) echo "Backup directory must be under .private (git ignored)" >&2; exit 2 ;;
esac
mkdir -p "$YH_BACKUP_DIR"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
final="$YH_BACKUP_DIR/yanhaoo-$timestamp.sqlite.age"
temp="$final.partial"
[[ ! -e "$final" ]] || { echo "Backup already exists" >&2; exit 2; }
trap 'rm -f -- "$temp"' EXIT
ssh -T -i "$YH_BACKUP_SSH_KEY" \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$YH_BACKUP_KNOWN_HOSTS" \
  -o ConnectTimeout=15 \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 \
  "$YH_BACKUP_SSH_TARGET" \
  'sudo -n docker exec -i xunxu-hub-hub-1 python -m hub.offsite_stream' \
  | age -r "$YH_AGE_RECIPIENT" -o "$temp"
[[ -s "$temp" ]] || { echo "Encrypted backup empty" >&2; exit 1; }
chmod 600 "$temp"
mv -- "$temp" "$final"
trap - EXIT
echo "Encrypted off-host snapshot saved: $final"
echo "Verify a restore with the private age identity before treating this as disaster recovery."
