#!/bin/bash
state='ko'
while true 
do
    sleep 60
    curlRes=$(curl -k -H "Authorization: Bearer 1234" 'http://127.0.0.1:8080/scale?auto')
    if [[ "$curlRes" == *"succeed"* ]]
    then
	  if [ "$state" == "ko" ]; then
		echo "Service is up"
          fi
	  state='ok'
    else
          if [ "$state" == "ok" ]; then
                echo "Service is down"
	  fi
	  state='ko'
    fi
done 
