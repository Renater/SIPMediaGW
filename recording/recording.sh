#!/bin/bash

### Start default video capture ###
ffmpeg  -f lavfi -i "smptebars=s=640x360" -vf drawtext="fontsize=60:text='RECORDING':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=White" -pix_fmt yuv420p \
       -video_size 640x360 -f v4l2 /dev/video0 -nostats 2> >( tee $STATE | logParse -p "Event") &

if [ "$WITH_ALSA" == "true" ]; then
    AUDRIVE='alsa'
    AUDEV=$ALSA_DEV
else
    AUDRIVE='pulse'
    AUDEV="VirtMicSrc1"
fi

DATE_TIME=$(date +"%Y_%m_%d_%H:%M:%S")

ffmpeg -y -nostdin \
       -hide_banner \
       -loglevel error \
       -t $RECORD_MAX_TIME \
       -thread_queue_size 512 \
       -f x11grab -r 30 -draw_mouse 0 -s $VID_SIZE_APP  -i :$SERVERNUM0 \
       -thread_queue_size 512 -f $AUDRIVE -i $AUDEV \
       -acodec aac -strict -2 -b:a 128k -ar 44100 \
       -vcodec libx264 -preset veryfast -tune zerolatency \
       -pix_fmt yuv420p -crf 25 -g 60 \
       -f mp4 \
       -f segment -segment_time $SEGMENT_TIME -reset_timestamps 1 \
       -map 0:v -map 1:a \
        ./recording/segment_%03d.mp4 & \
             1> >( logParse -p "Event") \
             2> >( logParse -p "Event") &

FFMPEG_PID=$(pgrep -n ffmpeg)
export FFMPEG_PID

### Event server ###
exec python3 src/eventServer.py 1> >( logParse -p "Event") \
                                2> >( logParse -p "Event") &
