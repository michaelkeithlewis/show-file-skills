#!/bin/zsh
# premix_session.sh <tag> <session .ptx> <ref wav> <check-bpm> [resume]: clip gain + the full premix on one session,
# then save. Work files go to /tmp/cpm/<tag>. "resume" starts again at typing td.json into an open session.
# Each typing step waits (max 30 min) for the Mac to be idle 130 s; never --force.
set -o pipefail
TAG=$1; PTX=$2; REF=$3; BPM=$4
DIR=$(cd "$(dirname "$0")" && pwd); PY=$DIR/.venv/bin/python; W=/tmp/cpm/$TAG; IR=$DIR/idlerun.sh
mkdir -p $W; cd $DIR
step() { echo "=== $1 $(date +%H:%M:%S)"; }
if [[ $5 != resume ]]; then
[[ -e "$PTX.bak-20261029-premix" ]] || cp -p "$PTX" "$PTX.bak-20261029-premix"
step close; $PY $DIR/premix_state.py close || true
step open; $PY opensess.py "$PTX" | tail -1 || exit 3
sleep 30
step solo; $PY $DIR/premix_state.py save $W/solo.json || exit 4
step clipgain-dry; $PY clipgain_normalize.py --dry || exit 5
step clipgain; $IR $PY clipgain_normalize.py | grep -v "^ *[^G].* avg " || exit 6
step trim; $PY premix.py trim --out $W/trim.json || exit 7
$PY $DIR/mixgroups.py off $W/groups.json || exit 7
$IR $PY premix.py apply $W/trim.json | tail -1 || exit 8
step plan; $PY premix.py plan --ref "$REF" --out $W/plan.json | grep -v "^  " || exit 9
step topdown; $PY premix.py topdown --faders $W/plan.json --out $W/td.json || exit 10
$IR $PY premix.py apply $W/td.json | grep -v "^SET" || exit 11
else
step resume; $PY $DIR/premix_state.py save $W/solo2.json; [[ -e $W/groups.json ]] || $PY $DIR/mixgroups.py off $W/groups.json; $IR $PY premix.py apply $W/td.json | grep -v "^SET" || exit 11
fi
$PY $DIR/fader_readback.py $W/td.json
step plugcomp; $PY premix.py plugcomp --faders $W/td.json --out $W/final.json || exit 12
$PY $DIR/fader_readback.py $W/final.json
step verify; $PY premix.py verify --ref "$REF" > $W/verify.json || exit 14
$PY -c "import json; d=json.load(open('$W/verify.json')); [print(k[9:-4], round(v['peak'],1), 'dBFS', round(v['lufs'],1), 'LUFS') for k,v in d.items() if k.startswith('ZZ')]; print('vs ref', d.get('vs_ref'), 'ref', round(d.get('ref_lufs',0),1))"
step check; $PY premix.py check --faders $W/plan.json --bpm $BPM | tail -60
step save; $PY $DIR/mixgroups.py on $W/groups.json; $PY $DIR/premix_state.py restore $W/solo.json && $PY $DIR/premix_state.py record "$PTX" $W/final.json $W/plan.json && $PY $DIR/premix_state.py savesess || exit 15
echo SONG DONE $TAG
