#!/bin/bash
heplify -i any -hs $HEPLIFY_SRV:9060 -e -nt tcp  -pr 3478  -d fragment,payload,rtcp
