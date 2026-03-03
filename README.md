## Connect wifi automatically:

```console
sudo nmcli con add type wifi ifname wlan0 con-name "F1Tenth_WiFi" ssid "YOUR_SSID"
sudo nmcli con modify "F1Tenth_WiFi" wifi-sec.key-mgmt wpa-psk
sudo nmcli con modify "F1Tenth_WiFi" wifi-sec.psk "YOUR_PASSWORD"
sudo nmcli con modify "F1Tenth_WiFi" connection.autoconnect yes

sudo nmcli con up "F1Tenth_WiFi"
```

``` console
ssh f1t@172.20.10.8
password: YOUR_PASSWORD
```
## InfluxDB:
open influxdb3-core-3.8.0-windows_amd64 in terminal
```console
.\influxdb3.exe serve --node-id f1tenth-node --object-store file --without-auth
```
runs on localhost:8181

## Odometry logger:

```console
cd Desktop/F1Tenth_DTaaS
python odom_logger.py
```

## Grafana:
http://localhost:3000

## Run the car: might not be needed anymore
```console
cd au_f1tenth_ws/rl-policy-deployment/src/f1tenth_rl_policy/f1tenth_rl_policy
```

#ensure ROS_DOMAIN_ID == 0
```console
echo $ROS_DOMAIN_ID
```

```console
cd ~/au_f1tenth_ws/rl-policy-deployment/
source install/setup.bash

ros2 run f1tenth_rl_policy rl_agent
```

## Control the car with 8bitdo controller:
set controller to bluetooth mode

### Open 2 terminals:
#### In the first one:
```console
source ~/au_f1tenth_ws/drivers/install/setup.bash
ros2 run joy joy_node
```

#### In the second:
```console
source ~/au_f1tenth_ws/drivers/install/setup.bash
ros2 run joy joy_teleop joy_teleop
```

hold right bumber, left stick controls acceleration, right stick controls steering

## Visualization on car:
```console
ros2 run rviz2 rviz2
```
