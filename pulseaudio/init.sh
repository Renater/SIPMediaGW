#!/bin/bash

### Configure audio devices ###
/etc/init.d/dbus start 

# Cleanup to be "stateless" on startup (otherwise pulseaudio daemon can't start)
rm -rf /var/run/pulse /var/lib/pulse /root/.config/pulse

pulseaudio --verbose --system --disallow-exit 

pactl load-module module-null-sink sink_name=VirtMicSink0
pactl load-module module-remap-source source_name=VirtMicSrc0 remix=no master=VirtMicSink0.monitor

pactl load-module module-null-sink sink_name=VirtMicSink1
pactl load-module module-remap-source source_name=VirtMicSrc1 remix=no master=VirtMicSink1.monitor

pactl set-default-source VirtMicSrc0
pactl set-default-sink VirtMicSink1
