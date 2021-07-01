#!/bin/bash

if [[ -z "$ROOM_NAME" ]]; then
    echo "Must provide ROOM_NAME in environment" 1>&2
    exit 1
fi

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment" 1>&2
    exit 1
fi

find_free_servernum() {
    i=$(($GW_ID"000" + 1))
    while [ -f /tmp/.X$i-lock ]; do
        i=$(($i + 1))
    done
    echo $i
}

check_Xvfb() {
    # 5 seconds timeout before exit
    id=0
    while [[ !( -f /tmp/.X$1-lock) && ("$id" < 5) ]]; do
        id=$(($id + 1))
        sleep 1
    done
   if [ "$id" = 5 ]; then
     echo "Xvfb :$1 failed to launch"
     exit 1
   fi
}

check_v4l2() {
    # 5 seconds timeout before exit
    id=0
    state=$(v4l2-ctl --device /dev/video0 --get-input | awk '{ print $1 }')
    while [[ $state != "Video" && ("$id" < 5) ]]; do
        id=$(($id + 1))
        state=$(v4l2-ctl --device /dev/video0 --get-input | awk '{ print $1 }')
        sleep 1
    done
   if [ "$id" = 5 ]; then
     echo "V4l2 loopback failed to launch"
     exit 1
   fi
}

### Configure audio devices ###
sudo killall -9 baresip Xvfb chrome chromedriver ffmpeg
/etc/init.d/dbus start > /dev/null 2>&1

pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit

HW0=$(( 2*$GW_ID ))
HW1=$(( 2*$GW_ID + 1 ))
pactl load-module module-alsa-source device=hw:${HW0},0 source_name=VirtMicSrc0  source_properties=device.description="Virtual_Microphone_Src0"
pactl load-module module-alsa-sink device=hw:${HW0},1 sink_name=VirtMicSink0 sink_properties=device.description="Virtual_Microphone_Sink0"

pactl load-module module-alsa-source device=hw:${HW1},0 source_name=VirtMicSrc1  source_properties=device.description="Virtual_Microphone_Src1"
pactl load-module module-alsa-sink device=hw:${HW1},1 sink_name=VirtMicSink1 sink_properties=device.description="Virtual_Microphone_Sink1"

pactl set-default-source VirtMicSrc0
pactl set-default-sink VirtMicSink1

### Configure video display ###
VID_SIZE_SIP="1280x720"
VID_SIZE_WEBRTC="640x360"
VID_FPS="30"
PIX_DEPTH="24"

SERVERNUM0=$(find_free_servernum)
echo "Xvfb Server 0 Number: " $SERVERNUM0
Xvfb :$SERVERNUM0 -screen 0 $VID_SIZE_SIP"x"$PIX_DEPTH &
check_Xvfb $SERVERNUM0

SERVERNUM1=$(find_free_servernum)
echo "Xvfb Server 1 Number: " $SERVERNUM1
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH &
check_Xvfb $SERVERNUM1

### Start default video capture ###
echo "DEBUG: ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0"
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0  > /dev/null 2>&1 &

check_v4l2

### Configure and start Baresip ###
cp /var/baresip/config_default .baresip/config
cp /var/baresip/$SIP_ACCOUNT_FILE .baresip
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_SIP'/' .baresip/config 
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config 
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config 
logFile="/var/logs/SIPWG"$GW_ID"_baresip_"$( date +%Y%m%j%H%M ).log
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip -v > $logFile 2>&1 &

### Check Baresip registering ###
python3 /var/baresip/$BARESIP_CMD_FILE
if [ "$?" == 1 ]; then
  echo "!!! A SIP account must be configurated (file: baresip/$SIP_ACCOUNT_FILE) !!!"
  exit
fi
DISP_NAME=$(grep -v '^#' /var/baresip/$SIP_ACCOUNT_FILE |  awk -F'<' '{print $1}')

### Start Selenium/Chrome ###
DISPLAY=:$SERVERNUM0 python3 /var/browsing/$BROWSE_FILE $ROOM_NAME $DISP_NAME $VID_SIZE_SIP > /dev/null 2>&1  &

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ### 
    DISPLAY=:$SERVERNUM0 xdotool key ctrl+W
    ### Quit Baresip ### 
    echo "/quit" | netcat 127.0.0.1 5555
    sleep 10
    exit
}
trap cleanup SIGINT SIGQUIT SIGTERM

while true; do
  sleep 1
done




 

