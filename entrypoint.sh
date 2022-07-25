#!/bin/bash

errLogs=$ERR_LOGS
appLogs=$APP_LOGS

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment" >> $errLogs
    exit 1
fi

if [[ -z "$SIP_ACCOUNT" ]]; then
    echo "Must provide SIP_ACCOUNT in environment" >> $errLogs
    exit 1
fi

log_pref() {
    stdbuf -oL tr -cd '\11\12\15\40-\176' | stdbuf -oL tr '\r' '\n' | \
    stdbuf -oL tr -s '\n' '\n' |\
    while IFS= read -r line; do printf '%s: %s\n' "$1" "$line"; done
}

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ###
    DISPLAY=:${SERVERNUM0} xdotool key ctrl+W
    ### Quit Baresip ###
    echo "/quit" | netcat -q 1 127.0.0.1 5555
    sleep 10
    killall ffmpeg Xvfb
}

trap 'cleanup | log_pref "Trap" >> ${appLogs}' SIGINT SIGQUIT SIGTERM EXIT

check_Xvfb() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(xdpyinfo -display ":$1" >/dev/null 2>&1; echo $?)
    while [[ ($state == "1") && ("$timer" < $timeOut) ]]; do
        timer=$(($timer + 1))
        sleep 1
        state=$(xdpyinfo -display ":$1" >/dev/null 2>&1; echo $?)
    done
    if [ "$timer" = $timeOut ]; then
        echo "Xvfb :$1 failed to launch" | log_pref "Xvfb" >> $errLogs
        exit 1
    fi
}

check_v4l2() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(v4l2-ctl --device "$1" --get-input | awk '{ print $1 }')
    while [[ $state != "Video" && ("$timer" < $timeOut) ]]; do
        timer=$(($timer + 1))
        sleep 1
        state=$(v4l2-ctl --device "$1" --get-input | awk '{ print $1 }')
    done
    if [ "$timer" = $timeOut ]; then
        echo "V4l2 loopback failed to launch" | log_pref "V4l2" >> $errLogs
        exit 1
    fi
}

check_register() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    OK="OK "
    state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555  2>/dev/null | grep -c "$OK")"
    while [[ ($state == "0") && ("$timer" < $timeOut) ]] ; do
        timer=$(($timer + 1))
        sleep 1
        state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555 2>/dev/null | grep -c "$OK")"
    done
    if [ "$timer" = $timeOut ]; then
        echo "Baresip failed to register" | log_pref "Baresip" >> $errLogs
        exit 1
    fi
}

### Configure audio devices ###
/etc/init.d/dbus start 1> >( log_pref "Dbus" >> $appLogs ) \
                       2> >( log_pref "Dbus" >> $errLogs )

# Cleanup to be "stateless" on startup (otherwise pulseaudio daemon can't start)
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

pulseaudio -D --verbose --exit-idle-time=-1 --system --disallow-exit 1> >( log_pref "Pulse" >> $appLogs ) \
                                                                     2> >( log_pref "Pulse" >> $errLogs )
pactl  load-module module-null-sink sink_name=VirtMicSink0
pactl load-module module-remap-source source_name=VirtMicSrc0 remix=no master=VirtMicSink0.monitor

pactl load-module module-null-sink sink_name=VirtMicSink1
pactl load-module module-remap-source source_name=VirtMicSrc1 remix=no master=VirtMicSink1.monitor

pactl set-default-source VirtMicSrc0 \
1> >( log_pref "Pulse" >> $appLogs ) 2> >( log_pref "Pulse" >> $errLogs )
pactl set-default-sink VirtMicSink1 \
1> >( log_pref "Pulse" >> $appLogs ) 2> >( log_pref "Pulse" >> $errLogs )

### Configure video display ###
VID_SIZE_SIP="1280x720"
VID_SIZE_WEBRTC="640x360"
VID_FPS="30"
PIX_DEPTH="24"

SERVERNUM0=99
echo "Server 0 Number= " $SERVERNUM0 | log_pref "Xvfb" >> $appLogs
Xvfb :$SERVERNUM0 -screen 0 $VID_SIZE_SIP"x"$PIX_DEPTH | log_pref "Xvfb" >> $errLogs &

SERVERNUM1=100
echo "Server 1 Number= " $SERVERNUM1 | log_pref "Xvfb" >> $appLogs
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH | log_pref "Xvfb" >> $errLogs &

### Check if Xvfb server is ready ###
check_Xvfb $SERVERNUM0
check_Xvfb $SERVERNUM1

### Start default video capture ###
echo "ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0" | \
     log_pref "FFMPEG" >> $appLogs
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0 -loglevel error | log_pref "FFMPEG" >> $errLogs &

### Configure and start Baresip ###
cp baresip/config_default .baresip/config
account=$(echo $SIP_ACCOUNT | sed -u 's/answermode=[^;]*;//')";answermode=manual"
echo $account > .baresip/accounts
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_SIP'/' .baresip/config
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config
echo "DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip" | log_pref "SIP client" >> $appLogs
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip $BARESIP_ARGS \
                     1> >( log_pref "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $appLogs ) \
                     2> >( log_pref "Baresip" | sed -u 's/\[;m//' | sed -u 's/\[31m//' >> $errLogs ) &
                     # "sed -u 's/\[..." => to remove already printed \r characters...

### Check Baresip registering ###
check_register

### Check if video device is ready ###
check_v4l2 "/dev/video0"

### Event handler ###
if [[ -n "$ROOM_NAME" ]]; then
    roomParam="-r "$ROOM_NAME
fi
if [[ -n "$FROM_URI" ]]; then
    fromUri="-f "$FROM_URI
fi
cp "./browsing/"$BROWSE_FILE src
DISPLAY=:$SERVERNUM0 python3 src/event_handler.py -b `pwd`"/browsing/"$BROWSE_FILE \
                                                  -s $VID_SIZE_SIP \
                                                  $roomParam $fromUri \
                     1> >( log_pref "Event" >> $appLogs ) 




