#!/bin/bash

if [[ -z "$ROOM_NAME" ]]; then
    echo "Must provide ROOM_NAME variable" | logParse -p "Recording"
    exit 1
fi

### Start default video capture ###
#ffmpeg  -f lavfi -i "smptebars=s=640x360" -vf drawtext="fontsize=60:text='RECORDING':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=White" -pix_fmt yuv420p \
#       -video_size 640x360 -f v4l2 /dev/video0 -nostats 2> >( tee $STATE | logParse -p "Recording") &

if [ "$WITH_ALSA" == "true" ]; then
    AUDRIVE='alsa'
    AUDEV=$ALSA_DEV
else
    AUDRIVE='pulse'
    AUDEV="VirtMicSrc1"
fi

if [ "$AUDIO_ONLY" != "true" ]; then
    VIDEO_IN=( -f x11grab -r 30 -draw_mouse 0 -s "$VID_SIZE_APP"  -i :"$SERVERNUM0" )
    VIDEO_CODEC=( -vcodec libx264 -preset veryfast -tune zerolatency -r 30 -pix_fmt yuv420p -crf 25 -g 60 )
    STREAMS_MAPPING='-map 0:v -map 1:a'
fi

(timeout "$RECORD_MAX_TIME"s ffmpeg -y -nostdin \
        -hide_banner \
        -re \
        -loglevel error \
        -t $RECORD_MAX_TIME \
        -thread_queue_size 512 \
        "${VIDEO_IN[@]}" \
        -thread_queue_size 512 -f $AUDRIVE -i $AUDEV \
        -acodec aac -strict -2 -b:a 128k -ar 44100 \
        "${VIDEO_CODEC[@]}" \
        -f mp4 \
        -f segment -segment_time $SEGMENT_TIME -reset_timestamps 1 \
        $STREAMS_MAPPING \
        ./recording/segment_%03d.mp4 \
         ; echo "/quit" | netcat -q 1 127.0.0.1 5555 ) \
            1> >( logParse -p "Recording") \
            2> >( logParse -p "Recording") &

for i in {1..5}; do
    if ls ./recording/*.mp4 &> /dev/null; then
        recording="on"
        break
    fi
    sleep 1
done

if [ "$recording" != "on" ]; then
    echo "FFMPEG recording failed to launch" | logParse -p "Recording"
    exit 1
fi

FFMPEG_PID=$(pgrep -n ffmpeg)
export FFMPEG_PID

### Event server ###
exec python3 src/eventServer.py 1> >( logParse -p "Event Server") \
                                2> >( logParse -p "Event Server") &

