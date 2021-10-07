#!/bin/bash
ffmpeg -nostats -re -stream_loop 0 -i ivr2.wav -f pulse VirtMicSink1

