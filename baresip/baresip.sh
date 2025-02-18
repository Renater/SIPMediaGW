#!/bin/bash

check_register() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    OK="OK "
    state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555  2>/dev/null | grep -c "$OK")"
    while [[ ($state == "0") && ($timer -lt $timeOut) ]] ; do
        timer=$(($timer + 1))
        sleep 1
        state="$(echo "/reginfo" | netcat -q 1  127.0.0.1 5555 2>/dev/null | grep -c "$OK")"
    done
    if [ $timer -eq $timeOut ]; then
        echo "Baresip failed to register" | logParse -p "Baresip"
        exit 1
    fi
}

### Start default video capture ###
echo "ffmpeg -s " $VID_SIZE_WEBRTC" -r "$VID_FPS" -draw_mouse 0 -f x11grab -i :"$SERVERNUM1" -pix_fmt yuv420p -f v4l2 /dev/video0" | \
     logParse -p "FFMPEG"
ffmpeg -r $VID_FPS -s $VID_SIZE_WEBRTC \
       -draw_mouse 0 -threads 0 \
       -f x11grab -i :$SERVERNUM1 -pix_fmt yuv420p \
       -f v4l2 /dev/video0 -nostats 2> >( tee $STATE | logParse -p "Event") &

### Start SIP capture (HEP) ###
if [[ "$HEPLIFY_SRV" ]]; then
    sudo sudo sngrep -H udp:$HEPLIFY_SRV -c -q --no-interface \
         2> >( logParse -p "heplify" ) &
fi

### set SIP account ###
userNamePref=$GW_NAME_PREFIX"."$GW_ID
if [[ "$SIP_NAME_PREFIX" ]]; then
    userNamePref=${SIP_NAME_PREFIX}"."${userNamePref}
fi
sipAccount="<sip:"${userNamePref}"@"$SIP_REGISTRAR";transport=$SIP_PROTOCOL>;regint=60;"
sipAccount+="auth_user="${userNamePref}";auth_pass="$SIP_SECRET";"
if [[ "$TURN_SRV" ]] && [[ "$TURN_USER" ]]  ; then
    sipAccount+="medianat=turn;stunserver=turn:"$TURN_SRV":3478;stunuser="$TURN_USER";stunpass="$TURN_PASS
    if [[ "$SDP_IN_IP4" ]]; then
        PUBLIC_IP=$SDP_IN_IP4
    fi
fi
if [[ "$MEDIAENC" ]] ; then
    sipAccount+=";mediaenc="$MEDIAENC
fi
if [[ "$SIP_PROXY" != "" ]] ; then
    sipAccount+=';outbound="sip:'$SIP_PROXY';transport=tcp"'
fi
sipAccount+=";answermode=manual"

### Configure and start Baresip ###
rm .baresip/*
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
sed -i 's/.*video_size.*/video_size\t\t'$VID_SIZE_APP'/' .baresip/config
sed -i 's/.*video_fps.*/video_fps\t\t'$VID_FPS'/' .baresip/config
sed -i 's/.*video_source.*/video_source\t\tx11grab,:'$SERVERNUM0'/' .baresip/config
sed -i 's/.*x11_main.*/x11_main\t\t:'$SERVERNUM1','$VID_SIZE_WEBRTC'+0+0/' .baresip/config
sed -i 's/.*x11_slides.*/x11_slides\t\t:'$SERVERNUM0','$VID_SIZE_APP'+'$VID_W_SIP'+0/' .baresip/config
echo "DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip" | logParse -p "SIP client"
DISPLAY=:$SERVERNUM1 LD_LIBRARY_PATH=/usr/local/lib  baresip -f .baresip $BARESIP_ARGS \
                     1> >( logParse -p "Baresip" -i $HISTORY ) \
                     2> >( logParse -p "Baresip" -i $HISTORY ) &
                     # "sed -u 's/\[..." => to remove already printed \r characters...

### Check Baresip registering ###
if [ "$CHECK_REGISTER" == "yes" ]; then
    check_register
fi
