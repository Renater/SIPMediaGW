# Development environment for the SIPMediaGW

The Room Connector can be easily deployed thanks to the "All-in-one" Vagrant file (**requires Vagrant and VirtualBox**).

1. Install [Vagrant](https://www.vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/).

2. Clone the repository and navigate into the directory:
   ```bash
   git clone https://github.com/Renater/SIPMediaGW.git && cd SIPMediaGW
   ```

3. Then, simply run:
   ```bash
   VAGRANT_VAGRANTFILE=test/Vagrantfile vagrant up
   ```

4. Once the command above is completed, open VirtualBox and make sure the virtual machine `SIPMediaGW_AllInOne` is up and running:
![SIPMediaGW_AllInOne virtual machine](SIPMediaGW_AllInOne.png)

1. To test the application, please see the [Testing section](./testing.md).
