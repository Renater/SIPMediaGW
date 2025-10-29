#!/bin/bash

if [[ -z "$RTMP_DST_URI" ]]; then
    echo "Must provide RTMP_DST_URI variable" | logParse -p "Streaming"
    exit 1
fi

### Start default video capture ###
ffmpeg  -f lavfi -i "smptebars=s=640x360" -vf drawtext="fontsize=60:text='STREAMING':x=(w-text_w)/2:y=(h-text_h)/2:fontcolor=White" -pix_fmt yuv420p \
       -video_size 640x360 -f v4l2 /dev/video0 -nostats 2> >( tee $STATE | logParse -p "Event") &

if [ "$WITH_ALSA" == "true" ]; then
    AUDRIVE='alsa'
    AUDEV=$ALSA_DEV
else
    AUDRIVE='pulse'
    AUDEV="VirtMicSrc1"
fi

if [ "$AUDIO_ONLY" != "true" ]; then
    VIDEO_IN=( -f x11grab -r 30 -draw_mouse 0 -s "$VID_SIZE_APP"  -i :"$SERVERNUM0" )
    VIDEO_CODEC=( -c:v libx264 -preset ultrafast -minrate:v 500K -maxrate:v 4M -bufsize:v 4M -x264-params keyint=90 -pix_fmt yuv420p  )
    STREAMS_MAPPING='-map 0:v:0 -map 1:a:0'
fi

ffmpeg \
      -hide_banner \
      -loglevel error \
      -thread_queue_size 1024 \
      "${VIDEO_IN[@]}" \
      -f $AUDRIVE \
      -ac 2 \
      -thread_queue_size 1024 \
      -i $AUDEV \
      "${VIDEO_CODEC[@]}" \
      $STREAMS_MAPPING \
      -c:a aac \
      -ab 128k \
      -ac 2 \
      -ar 44100 \
      -copyts \
      -f flv \
      $RTMP_DST_URI 1> >( logParse -p "Event") \
                    2> >( logParse -p "Event") &

### Event server ###
exec python3 src/eventServer.py 1> >( logParse -p "Event") \
                                2> >( logParse -p "Event") &
