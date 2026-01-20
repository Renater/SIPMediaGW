#!/bin/bash
# Start the HTTP API Launcher and the SIPMediaGW in a loop

# get script directory
SIPMEDIAGW_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." >/dev/null 2>&1 && pwd )"
cd $SIPMEDIAGW_DIR

# Get MAIN_APP type from docker-compose config
MAIN_APP=$(docker compose config 2>/dev/null | awk '/MAIN_APP:/ {print $2}')
GW_API_PORT=$(docker compose config 2>/dev/null | awk '/GW_API_PORT:/ {print $2}' | tr -d '"')

/bin/python3 HTTPLauncher.py --port $GW_API_PORT  2>&1 | logger -t HTTPLauncher &

echo "options snd-aloop enable=1,1,1,1,1,1,1,1 index=0,1,2,3,4,5,6,7" | tee  /etc/modprobe.d/alsa-loopback.conf
modprobe -r snd-aloop && modprobe snd-aloop
#
echo "options v4l2loopback devices=4 exclusive_caps=1,1,1,1" | tee  /etc/modprobe.d/v4l2loopback.conf
modprobe -r v4l2loopback && modprobe  v4l2loopback 



pref=$(hostname -I | awk "{print $1}" | cut -d" "  -f1) 
lockFilePrefix="sipmediagw"

if [ "$MAIN_APP" == "baresip" ]; then
    echo "Starting SIPMediaGW in a loop"
    until [ "$?" == 1 ]; do 
        cd $SIPMEDIAGW_DIR
        /bin/bash ./SIPMediaGW.sh -p $pref -i -l
    done
else
    echo "MAIN_APP is not baresip so start them once as Media gateway"
    CPU_PER_GW=$(docker compose config 2>/dev/null | awk '/CPU_PER_GW:/ {print $2}')
    CPU_PER_GW=$(echo "$CPU_PER_GW" | tr -d '"')
    maxGwNum=$(echo "$(nproc)/$CPU_PER_GW" | bc )
    for i in $(seq 0 $((maxGwNum - 1))); do
        echo "Starting gateway number $i"
        /bin/bash ./SIPMediaGW.sh -p $pref -i -l
        sleep 1
        exec {lockFd}>"/tmp/"${lockFilePrefix}$i".lock"
        flock -x -n $lockFd
    done
fi
exit 0