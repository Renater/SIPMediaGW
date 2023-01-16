#!/bin/bash

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment"
    exit 1
fi

### Init logging ###
errLogs=$ERR_LOGS
appLogs=$APP_LOGS
HISTORY="/var/logs/gw"$GW_ID"_history"
echo "start:$(date +'%b %d %H:%M:%S')"> $HISTORY

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ###
    DISPLAY=:${SERVERNUM0} xdotool key ctrl+W
    ### Quit Baresip ###
    echo "/quit" | netcat -q 1 127.0.0.1 5555
    sleep 10
    killall ffmpeg Xvfb
}

trap 'cleanup | logParse -p "Trap" >> ${appLogs}' SIGINT SIGQUIT SIGTERM EXIT

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
        echo "Xvfb :$1 failed to launch" | logParse -p "Xvfb" >> $errLogs
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
        echo "V4l2 loopback failed to launch" | logParse -p "V4l2" >> $errLogs
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
        echo "Baresip failed to register" | logParse -p "Baresip" >> $errLogs
        exit 1
    fi
}

### Configure audio devices ###
if [ "$WITH_ALSA" == "true" ]; then
    ALSA_DEV='plug:baresip'
    HW0=$(( 2*$GW_ID ))
    (($HW0)) || HW0=""
    HW1=$(( 2*$GW_ID + 1 ))
    ALSA_CARD0="Loopback"${HW0:+'_'$HW0}
    ALSA_CARD1="Loopback"${HW1:+'_'$HW1}
    sed -i 's/Loopback,/'$ALSA_CARD0',/g' /etc/asound.conf
    sed -i 's/Loopback_1,/'$ALSA_CARD1',/g' /etc/asound.conf
else
    ./pulseaudio_init.sh  1> >( logParse -p "Pulse" >> $appLogs ) \
                          2> >( logParse -p "Pulse" >> $errLogs )
fi

### Configure video display ###
VID_FPS="30"
PIX_DEPTH="24"

SERVERNUM0=99
echo "Server 0 Number= " $SERVERNUM0 | logParse -p "Xvfb" >> $appLogs
Xvfb :$SERVERNUM0 -screen 0 $VID_SIZE_SIP"x"$PIX_DEPTH | logParse -p "Xvfb" >> $errLogs &

SERVERNUM1=100
echo "Server 1 Number= " $SERVERNUM1 | logParse -p "Xvfb" >> $appLogs
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH | logParse -p "Xvfb" >> $errLogs &

### Check if Xvfb server is ready ###
check_Xvfb $SERVERNUM0
check_Xvfb $SERVERNUM1

### Start default video capture ###
echo "ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0" | \
     logParse -p "FFMPEG" >> $appLogs
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0 -loglevel error | logParse -p "Event" >> $errLogs &

### set SIP account ###
userNamePref=$GW_NAME_PREFIX"."$GW_ID
if [[ "$SIP_NAME_PREFIX" ]]; then
    userNamePref=${SIP_NAME_PREFIX}"."${userNamePref}
fi
sipAccount="<sip:"${userNamePref}"@"$SIP_DOMAIN";transport=tcp>;regint=60;"
sipAccount+="auth_user="${userNamePref}";auth_pass="$SIP_SECRET";"
if [[ "$STUN_SRV" ]]; then
    sipAccount+="medianat=turn;stunserver=turn:"$STUN_SRV":3478;stunuser="$STUN_USER";stunpass="$STUN_PASS
fi
sipAccount+=";answermode=manual"

### Configure and start Baresip ###
cp baresip/config_default .baresip/config
echo $sipAccount > .baresip/accounts
if [ "$WITH_ALSA" == "true" ]; then
    sed -i 's/.*audio_player.*/audio_player\t\talsa,'$ALSA_DEV'/' .baresip/config
    sed -i 's/.*audio_source.*/audio_source\t\talsa,'$ALSA_DEV'/' .baresip/config
    sed -i 's/.*audio_alert.*/audio_alert\t\talsa,'$ALSA_DEV'/' .baresip/config
fi
if [[ "$PUBLIC_IP" ]]; then
    sed -i 's/.*public_address.*/public_address\t\t'$PUBLIC_IP'/' .baresip/config
fi
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_SIP'/' .baresip/config
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config
echo "DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip" | logParse -p "SIP client" >> $appLogs
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip $BARESIP_ARGS \
                     1> >( logParse -p "Baresip" -i $HISTORY >> $appLogs ) \
                     2> >( logParse -p "Baresip" -i $HISTORY >> $errLogs ) &
                     # "sed -u 's/\[..." => to remove already printed \r characters...

### Check Baresip registering ###
check_register

### Check if video device is ready ###
check_v4l2 "/dev/video0"

### Event handler ###
if [[ -n "$ROOM_NAME" ]]; then
    roomParam="-r "$ROOM_NAME
fi
cp "./browsing/"$BROWSE_FILE src
DISPLAY=:$SERVERNUM0 exec python3 src/event_handler.py -b `pwd`"/browsing/"$BROWSE_FILE \
                                                       -s $VID_SIZE_SIP \
                                                       $roomParam $fromUri \
                          1> >( logParse -p "Event" -i $HISTORY >> $appLogs )


