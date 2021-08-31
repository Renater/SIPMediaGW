#!/bin/bash
cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ### 
    DISPLAY=:${SERVERNUM0} xdotool key ctrl+W
    ### Quit Baresip ### 
    echo "/quit" | netcat 127.0.0.1 5555
    sleep 10
    sudo rm /tmp/.X${SERVERNUM0}-lock /tmp/.X${SERVERNUM1}-lock
}
trap cleanup SIGINT SIGQUIT SIGTERM

if [[ -z "$LOG_PREF" ]];
then
    errLogs=/dev/null
    appLogs=/dev/null
else
    errLogs=$LOG_PREF"_err.log"
    appLogs=$LOG_PREF"_app.log"
fi

if [[ -z "$ROOM_NAME" ]]; then
    echo "Must provide ROOM_NAME in environment" >> $errLogs
    exit 1
fi

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment" >> $errLogs
    exit 1
fi

if [[ -z "$SIP_ACCOUNT" ]]; then
    echo "Must provide SIP_ACCOUNT in environment" >> $errLogs
    exit 1
fi

log_ts() { 
    stdbuf -oL tr -cd '\11\12\15\40-\176' | stdbuf -oL tr '\r' '\n' | \
    stdbuf -oL tr -s '\n' '\n' |\
    while IFS= read -r line; do printf '[%s] %s: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$line"; done
}

find_free_serverxnum() {
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
       echo "Xvfb :$1 failed to launch" >> $errLogs
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
        echo "V4l2 loopback failed to launch" >> $errLogs
        exit 1
    fi
}

### Configure audio devices ###
/etc/init.d/dbus start 1> >( log_ts "Dbus" >> $appLogs ) \
                       2> >( log_ts "Dbus" >> $errLogs )

# Cleanup to be "stateless" on startup (otherwise pulseaudio daemon can't start)
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit 1> >( log_ts "Pulse" >> $appLogs ) \
                                                                     2> >( log_ts "Pulse" >> $errLogs )

HW0=$(( 2*$GW_ID ))
HW1=$(( 2*$GW_ID + 1 ))
pactl load-module module-alsa-source device=hw:${HW0},0 source_name=VirtMicSrc0  source_properties=device.description="Virtual_Microphone_Src0" \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )
pactl load-module module-alsa-sink device=hw:${HW0},1 sink_name=VirtMicSink0 sink_properties=device.description="Virtual_Microphone_Sink0" \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )

pactl load-module module-alsa-source device=hw:${HW1},0 source_name=VirtMicSrc1  source_properties=device.description="Virtual_Microphone_Src1" \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )
pactl load-module module-alsa-sink device=hw:${HW1},1 sink_name=VirtMicSink1 sink_properties=device.description="Virtual_Microphone_Sink1" \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )

pactl set-default-source VirtMicSrc0 \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )
pactl set-default-sink VirtMicSink1 \
1> >( log_ts "Pulse" >> $appLogs ) 2> >( log_ts "Pulse" >> $errLogs )

### Configure video display ###
VID_SIZE_SIP="1280x720"
VID_SIZE_WEBRTC="640x360"
VID_FPS="30"
PIX_DEPTH="24"

SERVERNUM0=$(find_free_serverxnum)
echo "Server 0 Number= " $SERVERNUM0 | log_ts "Xvfb">> $appLogs
Xvfb :$SERVERNUM0 -screen 0 $VID_SIZE_SIP"x"$PIX_DEPTH &
check_Xvfb $SERVERNUM0

SERVERNUM1=$(find_free_serverxnum)
echo "Server 1 Number= " $SERVERNUM1 | log_ts "Xvfb">> $appLogs
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH &
check_Xvfb $SERVERNUM1

### Start default video capture ###
echo "ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0" | \
     log_ts "FFMPEG">> $appLogs
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0 -loglevel error | log_ts "FFMPEG" >> $errLogs &

### Check if video device is ready ###
check_v4l2

### Configure and start Baresip ###
cp baresip/config_default .baresip/config
echo "$SIP_ACCOUNT" > .baresip/accounts
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_SIP'/' .baresip/config
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config
echo "DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip -v" | log_ts "SIP client">> $appLogs
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip -v \
                     1> >( log_ts "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $appLogs ) \
                     2> >( log_ts "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $errLogs ) &
                     # "sed -u 's/\[..." => to remove already printed \r characters...

### Check Baresip registering ###
python3 baresip/$BARESIP_CMD_FILE 1> >( log_ts "Baresip" >> $appLogs ) \
                                  2> >( log_ts "Baresip" >> $errLogs )
if [ "$?" == 1 ];
then
    echo "!!! A valid SIP account must be configurated !!!" | log_ts "Baresip" >> $errLogs
    exit
else
    echo "###################### SIP URI ######################"
    echo $(awk -F'<|;' '{print $2}' <<< $SIP_ACCOUNT)
    echo "#####################################################"
fi
DISP_NAME=$(grep -v '^#' .baresip/accounts |  awk -F'<' '{print $1}')

### Start Selenium/Chrome ###
echo "DISPLAY=:"$SERVERNUM0" python3 browsing/"$BROWSE_FILE $ROOM_NAME $DISP_NAME $VID_SIZE_SIP | log_ts "Web browser">> $appLogs
DISPLAY=:$SERVERNUM0 python3 browsing/$BROWSE_FILE $ROOM_NAME $DISP_NAME $VID_SIZE_SIP \
                     1> >( log_ts "Selenium" >> $appLogs ) \
                     2> >( log_ts "Selenium" >> $errLogs ) &

while true; do
    sleep 1
done




