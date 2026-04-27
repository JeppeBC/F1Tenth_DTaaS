## Full system test:
|Terminal: | Command: | Purpose: |
| --- | --- | --- |
|1 | `Source ~/sim_ws/install/setup.bash \ ros2 launch f1tenth_gym_ros gym_bridge_launch.py` | Sim + RViz2 |
|2 | `ros2 run topic_tools relay /teleop /drive` |`/teleop` → `/drive` for gym_bridge |
|3 | `ros2 run f1tenth_gym_ros ackermann_keyboard_teleop` | Keyboard — this terminal needs focus |
|4 | `ros2 run f1tenth_gym_ros dt_pt_bridge --ros-args -p pt_host:=172.20.10.8` | Forwards to PT |
|5 |  `ros2 run f1tenth_gym_ros latency_logger --ros-args -p output_dir:=/tmp/latency` | Benchmarking |
|| On the car||
|1 | `export ROS_DOMAIN_ID=1 / python3 dt_pt_listener.py --port 9870 --echo-back` | Benchmarking |


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
