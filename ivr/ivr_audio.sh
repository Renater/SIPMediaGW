#!/bin/bash
ffmpeg -nostats -re -stream_loop 0 -i ivr.wav -f pulse VirtMicSink1

