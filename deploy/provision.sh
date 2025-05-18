#!/bin/bash

sudo apt-get update
sudo systemctl disable --now unattended-upgrades
sudo sed -i 's/.*Unattended-Upgrade.*/APT::Periodic::Unattended-Upgrade "0";/' /etc/apt/apt.conf.d/20auto-upgrades
sudo apt-get install git
#
sudo apt-get install -y linux-modules-extra-$(uname -r)
sudo echo "options snd-aloop enable=1,1,1,1,1,1,1,1 index=0,1,2,3,4,5,6,7" | sudo tee  /etc/modprobe.d/alsa-loopback.conf
sudo echo "snd-aloop" | sudo tee -a /etc/modules
sudo modprobe snd-aloop
#
sudo apt-get install -y v4l2loopback-dkms
sudo echo "options v4l2loopback devices=4 exclusive_caps=1,1,1,1" | sudo tee  /etc/modprobe.d/v4l2loopback.conf
sudo echo "v4l2loopback" | sudo tee -a /etc/modules
sudo modprobe v4l2loopback
#
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    python3-webpy \
    gnupg \
    lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
#
sudo usermod -aG docker vagrant
sudo service docker restart
if [ ! "$(docker network ls | grep gw_net)" ]; then
  sudo docker network create --subnet=192.168.92.0/29 gw_net
fi
#
if [ "$MAIN_APP" == "baresip" ]; then
	docker build -f /sipmediagw/deploy/kamailio/Dockerfile -t kamailio4sipmediagw /sipmediagw/deploy/kamailio
	docker build -f /sipmediagw/deploy/coturn/Dockerfile -t coturn4sipmediagw /sipmediagw/deploy/coturn
	docker compose -f /sipmediagw/deploy/docker-compose.yml pull sip_db
fi

if [ "$MAIN_APP" == "recording" ]; then
	docker build -f /sipmediagw/transcript/Dockerfile -t transcript4sipmediagw /sipmediagw/transcript
fi

#
echo "HOST_IP=$HOST_IP" >> /etc/environment
BROWSE_FILE=$BROWSING${BROWSING:+.py}
echo "BROWSE_FILE=$BROWSE_FILE" >> /etc/environment
echo "MAIN_APP=$MAIN_APP" >> /etc/environment
sudo cp /sipmediagw/deploy/services/* /etc/systemd/system
if [ "$MAIN_APP" == "baresip" ]; then
	sudo systemctl enable coturn.service
	sudo systemctl enable kamailio.service
	sudo systemctl enable homer.service
fi
sudo systemctl enable sipmediagw.service
if [ "$MAIN_APP" == "baresip" ]; then
	sudo systemctl start coturn.service
	sudo systemctl start kamailio.service
	sudo systemctl start homer.service
fi
sudo systemctl start sipmediagw.service

