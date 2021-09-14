#!/bin/bash

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

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ###
    DISPLAY=:${SERVERNUM0} xdotool key ctrl+W
    ### Quit Baresip ###
    echo "/quit" | netcat -q 1 127.0.0.1 5555
    sleep 10
    sudo rm /tmp/.X${SERVERNUM0}-lock /tmp/.X${SERVERNUM1}-lock
}

trap 'cleanup | log_ts "Trap" >> ${appLogs}' SIGINT SIGQUIT SIGTERM EXIT

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
       echo "Xvfb :$1 failed to launch" | log_ts "Xvfb" >> $errLogs
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
        echo "V4l2 loopback failed to launch" | log_ts "V4l2" >> $errLogs
        exit 1
    fi
}

check_register() {
    # 5 seconds timeout before exit
    id=0
    OK="OK "
    state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555  2>/dev/null | grep -c "$OK")"
    while [[ ($state == "0") && ("$id" < 5) ]] ; do
        id=$(($id + 1))
        state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555 2>/dev/null | grep -c "$OK")"
        sleep 1
    done
    if [ "$id" = 5 ]; then
        echo "Baresip failed to register" | log_ts "Baresip" >> $errLogs
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
echo "Server 0 Number= " $SERVERNUM0 | log_ts "Xvfb" >> $appLogs
Xvfb :$SERVERNUM0 -screen 0 $VID_SIZE_SIP"x"$PIX_DEPTH | log_ts "Xvfb" >> $errLogs &

SERVERNUM1=$(( $SERVERNUM0+1 ))
echo "Server 1 Number= " $SERVERNUM1 | log_ts "Xvfb" >> $appLogs
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH | log_ts "Xvfb" >> $errLogs &

### Start default video capture ###
echo "ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0" | \
     log_ts "FFMPEG" >> $appLogs
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0 -loglevel error | log_ts "FFMPEG" >> $errLogs &

### Configure and start Baresip ###
cp baresip/config_default .baresip/config
echo "$SIP_ACCOUNT" > .baresip/accounts
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_SIP'/' .baresip/config
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config
echo "DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip -v" | log_ts "SIP client" >> $appLogs
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip -v \
                     1> >( log_ts "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $appLogs ) \
                     2> >( log_ts "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $errLogs ) &
                     # "sed -u 's/\[..." => to remove already printed \r characters...

### Check Baresip registering ###
check_register
echo "###################### SIP URI ######################"
echo $(awk -F'<|;' '{print $2}' <<< $SIP_ACCOUNT)
echo "#####################################################"

### Check if Xvfb server is ready ###
check_Xvfb $SERVERNUM0
check_Xvfb $SERVERNUM1

### Check if video device is ready ###
check_v4l2

### Event handler ###
DISPLAY=:$SERVERNUM0 python3 event_handler.py -l $appLogs \
                                              -b `pwd`"/browsing/"$BROWSE_FILE \
                                              -r $ROOM_NAME \
                                              -s $VID_SIZE_SIP \
                     1> >( log_ts "Event" >> $appLogs ) 2> >( log_ts "Event" >> $errLogs )




