#!/bin/bash

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment"
    exit 1
fi

# If GW_PROXY is set Register the gateway in the Redis Proxy at init phase
if [[ -n "$GW_PROXY" &&  -n "$INIT" ]]; then
    echo "Registering gateway $GW_NAME form $HOST_IP type $MAIN_APP at $GW_PROXY : $INIT" | logParse -p "RegisterGW"
    resp=$(curl -s -X POST "$GW_PROXY/register" \
         -H "Authorization: Bearer $GW_TOKEN" \
         -H "Content-Type: application/json" \
         -d '{"gw_id": "'$GW_NAME'", "gw_ip": "'$HOST_IP:$GW_API_PORT'", "gw_type": "'$MAIN_APP'"}' | logParse -p "RegisterGW")
    echo "Registration response: $resp" | logParse -p "RegisterGW"
fi

if [[ -z "$ROOM_NAME" && ( "$MAIN_APP" == "recording" || "$MAIN_APP" == "streaming" ) ]]; then
    echo "Must provide ROOM_NAME with $MAIN_APP"
    exit 1
fi

### Init logging ###
HISTORY="/var/logs/gw"$GW_ID"_history"
STATE="/var/logs/gw"$GW_ID"_state"
> $STATE

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ###
    xdotool key ctrl+W
    ### Quit Baresip ###
    echo "/quit" | netcat -q 1 127.0.0.1 5555
    sleep 10
    killall -SIGINT ffmpeg Xvfb
}

trap 'cleanup | logParse -p "Trap"' SIGINT SIGQUIT SIGTERM EXIT

### Assets download ###
if [[ -n "$ASSETS_URL" ]]; then
    wget -qO- "$ASSETS_URL" | tar xvJ -C /var/browsing/assets | logParse -p "Assets"
fi

checkX() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(xdpyinfo -display "$1" >/dev/null 2>&1; echo $?)
    while [[ ($state == "1") && ($timer -lt $timeOut) ]]; do
        timer=$(($timer + 1))
        sleep 1
        state=$(xdpyinfo -display "$1" >/dev/null 2>&1; echo $?)
    done
    if [ $timer -eq $timeOut ]; then
        echo "Xvfb $1 failed to launch" | logParse -p "Xvfb"
        exit 1
    fi
}

checkEventSrv() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(netstat -a | grep :4444 | grep -c LISTEN)
    while [[ ($state != "1") && ($timer -lt $timeOut) ]] ; do
        timer=$(($timer + 1))
        state=$(netstat -a | grep :4444 | grep -c LISTEN)
        sleep 1
    done
    if [ $timer -eq $timeOut ]; then
        echo "The gateway failed to launch" | logParse -p "EventSrv"
        exit 1
    fi
}

envsubst < /var/browsing/assets/config.template.json > /var/browsing/assets/config.json



if [[ "$MAIN_APP" == "recording" && $(ls /var/recording/*.mp4 2>/dev/null) ]]; then

    firstRec=$(ls -rt /var/recording/*.mp4 | head -n 1)
    DATE_TIME=$(TZ=$TZ stat --format='%W' "$firstRec" | awk '{print strftime("%Y_%m_%d_%H%M", $1)}')

    FINAL_VIDEO="RendezVous_$DATE_TIME.mp4"

    if [ "$WITH_TRANSCRIPT" == "true" ]; then
        python3 /var/transcript/transcript.py 1> >( logParse -p "Transcript") \
                                              2> >( logParse -p "Transcript")

        FINAL_TRANSCRIPT="RendezVous_$DATE_TIME.srt"
        mv /var/recording/final_transcript.srt "/var/recording/"$FINAL_TRANSCRIPT
    fi

    # Generate mp4 file list for concatenation
    > "/var/recording/segments_list.txt"
    for f in /var/recording/segment_*.mp4; do
        echo "file '$f'" >> "/var/recording/segments_list.txt"
    done

    # Concatenate segments into one file
    ffmpeg -y -f concat -safe 0 -i "/var/recording/segments_list.txt" -c copy "/var/recording/$FINAL_VIDEO"
    rm /var/recording/segment*.mp4
    rm /var/recording/segment*.txt

    echo "Processing finished : video merged in $FINAL_VIDEO and transcriptions in $FINAL_TRANSCRIPT"

    cd /var/recording
    {
        python3 filesender.py \
                -u $FS_USER_MAIL -r $FS_RECIPIENT_MAIL -a $FS_API_KEY \
                $FINAL_VIDEO $FINAL_TRANSCRIPT \
                1> >( logParse -p "FileSender") \
                2> >( logParse -p "FileSender") && \
        rm $FINAL_VIDEO $FINAL_TRANSCRIPT && \
        echo "Files sent and removed" | logParse -p "FileSender"
    } || {
        mv $FINAL_VIDEO $FINAL_TRANSCRIPT /var/logs && \
        echo "Files moved in log directory" | logParse -p "FileCopy";
    }
    exit 1
else
    echo "start_gw:$(TZ=$TZ date +'%b %d %H:%M:%S')"> $HISTORY
    echo "main_app:$MAIN_APP" > $HISTORY
fi

### Configure audio devices ###
if [[ -z "$DISPLAY" ]]; then
    if [ -z "${PULSE_SERVER+x}" ] || [ -z "$PULSE_SERVER" ]; then
        unset PULSE_SERVER
    fi
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
        ./pulseaudio_init.sh  1> >( logParse -p "Pulse") \
                              2> >( logParse -p "Pulse")
    fi
fi

if [[ "$AUDIO_ONLY" != "true" ]]; then
    ### Configure video display ###
    VID_FPS="30"
    PIX_DEPTH="24"

    IFS="x" read -r VID_W_APP VID_H_APP <<<$VID_SIZE_APP
    VID_WX2_APP=$(( 2*$VID_W_APP ))

    mkdir -p /tmp/.X11-unix
    sudo chmod 1777 /tmp/.X11-unix
    sudo chown root /tmp/.X11-unix/

    DISPLAY_WEB=${DISPLAY:-":99"}
    DISPLAY_APP=:100

    if [[ -z "$DISPLAY" ]]; then
        echo "Display ID, web browser " $DISPLAY_WEB | logParse -p "Xvfb"
        Xvfb $DISPLAY_WEB -screen 0 \
            $VID_WX2_APP"x"$VID_H_APP"x"$PIX_DEPTH \
            +extension RANDR -noreset | logParse -p "Xvfb" &
        checkX $DISPLAY_WEB
        DISPLAY=$DISPLAY_WEB xrandr --setmonitor screen0 \
                $VID_W_APP"/640x"$VID_H_APP"/360+0+0" screen | logParse -p "xrandr"
        DISPLAY=$DISPLAY_WEB xrandr --setmonitor screen1 \
                $VID_W_APP"/640x"$VID_H_APP"/360+"$VID_W_APP"+0" none | logParse -p "xrandr"

        DISPLAY=$DISPLAY_WEB fluxbox | logParse -p "fluxbox" &
        DISPLAY=$DISPLAY_WEB unclutter -idle 1 &
    else
        DISPLAY=$DISPLAY_WEB xrandr -s $VID_SIZE_APP | logParse -p "xrandr"
    fi

    echo "Display ID, main application " $DISPLAY_APP | logParse -p "Xvfb"
    Xvfb $DISPLAY_APP -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH \
        +extension RANDR -noreset| logParse -p "Xvfb" &
    checkX $DISPLAY_APP
fi



### Main application ###
if [[ -n "$MAIN_APP" && -f "$MAIN_APP/$MAIN_APP.sh" ]]; then
    source "$MAIN_APP/$MAIN_APP.sh"
else
    ### Event server ###
    exec python3 src/eventServer.py 1> >( logParse -p "Event Server") \
                                    2> >( logParse -p "Event Server") &
fi

if [ "$WITH_TRANSCRIPT" == "true" ]; then
    exec python3 transcript/transcript.py 1> >( logParse -p "Transcript") \
                                          2> >( logParse -p "Transcript") &
fi

### Check if event server is ready ###
checkEventSrv

### Event handler ###
if [[ -n "$ROOM_NAME" ]]; then
    roomParam="-r "$ROOM_NAME
fi

DISPLAY=$DISPLAY_WEB exec python3 src/event_handler.py -s $VID_SIZE_APP \
                                  $roomParam $fromUri \
                         1> >( logParse -p "Event" -i $HISTORY )

