#!/bin/bash

if [[ -z "$GW_ID" ]]; then
    echo "Must provide GW_ID in environment"
    exit 1
fi

### Init logging ###
HISTORY="/var/logs/gw"$GW_ID"_history"
STATE="/var/logs/gw"$GW_ID"_state"
touch $STATE
echo "start_gw:$(TZ=$TZ date +'%b %d %H:%M:%S')"> $HISTORY

cleanup() {
    echo "Cleaning up..."
    ### Quit Selenium/Chrome ###
    DISPLAY=:${SERVERNUM0} xdotool key ctrl+W
    ### Quit Baresip ###
    echo "/quit" | netcat -q 1 127.0.0.1 5555
    sleep 10
    killall -SIGINT ffmpeg Xvfb
}

trap 'cleanup | logParse -p "Trap"' SIGINT SIGQUIT SIGTERM EXIT

checkXvfb() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(xdpyinfo -display ":$1" >/dev/null 2>&1; echo $?)
    while [[ ($state == "1") && ($timer -lt $timeOut) ]]; do
        timer=$(($timer + 1))
        sleep 1
        state=$(xdpyinfo -display ":$1" >/dev/null 2>&1; echo $?)
    done
    if [ $timer -eq $timeOut ]; then
        echo "Xvfb :$1 failed to launch" | logParse -p "Xvfb"
        exit 1
    fi
}

checkV4l2() {
    # 5 seconds timeout before exit
    timeOut=5
    timer=0
    state=$(grep -q $1 $STATE; echo $?)
    while [[ ($state == "1") && ($timer -lt $timeOut) ]]; do
        timer=$(($timer + 1))
        sleep 1
        state=$(grep -q $1 $STATE; echo $?)
    done
    if [ $timer -eq $timeOut ]; then
        echo "V4l2 loopback failed to launch" | logParse -p "V4l2"
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

    echo "Send and remove files" | logParse -p "FileSender"
    cd /var/recording
    exec python3 filesender.py \
         -u $USER_MAIL -r $USER_MAIL -a $API_KEY \
         $FINAL_VIDEO $FINAL_TRANSCRIPT \
         1> >( logParse -p "FileSender") \
         2> >( logParse -p "FileSender")
    rm $FINAL_VIDEO $FINAL_TRANSCRIPT

    exit 1

fi

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
    ./pulseaudio_init.sh  1> >( logParse -p "Pulse") \
                          2> >( logParse -p "Pulse")
fi

### Configure video display ###
VID_FPS="30"
PIX_DEPTH="24"

IFS="x" read -r VID_W_SIP VID_H_SIP <<<$VID_SIZE_APP
VID_WX2_SIP=$(( 2*$VID_W_SIP ))

mkdir -p /tmp/.X11-unix
sudo chmod 1777 /tmp/.X11-unix
sudo chown root /tmp/.X11-unix/

SERVERNUM0=99
echo "Server 0 Number= " $SERVERNUM0 | logParse -p "Xvfb"
Xvfb :$SERVERNUM0 -screen 0 \
      $VID_WX2_SIP"x"$VID_H_SIP"x"$PIX_DEPTH \
     +extension RANDR -noreset | logParse -p "Xvfb" &

SERVERNUM1=100
echo "Server 1 Number= " $SERVERNUM1 | logParse -p "Xvfb"
Xvfb :$SERVERNUM1 -screen 0 $VID_SIZE_WEBRTC"x"$PIX_DEPTH \
     +extension RANDR -noreset| logParse -p "Xvfb" &

### Check if Xvfb server is ready ###
checkXvfb $SERVERNUM0
checkXvfb $SERVERNUM1

DISPLAY=:$SERVERNUM0 xrandr --setmonitor screen0 \
        $VID_W_SIP"/640x"$VID_H_SIP"/360+0+0" screen | logParse -p "xrandr"
DISPLAY=:$SERVERNUM0 xrandr --setmonitor screen1 \
        $VID_W_SIP"/640x"$VID_H_SIP"/360+"$VID_W_SIP"+0" none | logParse -p "xrandr"

DISPLAY=:$SERVERNUM0 fluxbox | logParse -p "fluxbox" &
DISPLAY=:$SERVERNUM0 unclutter -idle 1 &

### Main application ###
source $MAIN_APP"/"$MAIN_APP".sh"

if [ "$WITH_TRANSCRIPT" == "true" ]; then
    exec python3 transcript/transcript.py 1> >( logParse -p "Transcript") \
                                          2> >( logParse -p "Transcript") &
fi

### Check if video device is ready ###
checkV4l2 "/dev/video0"

### Check if event server is ready ###
checkEventSrv

### Event handler ###
if [[ -n "$ROOM_NAME" ]]; then
    roomParam="-r "$ROOM_NAME
fi
cp "./browsing/"$BROWSE_FILE src
DISPLAY=:$SERVERNUM0 exec python3 src/event_handler.py -b `pwd`"/browsing/"$BROWSE_FILE \
                                                       -s $VID_SIZE_APP \
                                                       $roomParam $fromUri \
                          1> >( logParse -p "Event" -i $HISTORY )

