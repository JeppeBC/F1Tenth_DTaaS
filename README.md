## Pre-requisites:
- ROS2 Humble
- Gazebo 11
installation instructions: https://f1tenth.org/docs/sim/gym_ros/install/

Install the package in a ROS2 workspace:
```bash
cd ~/sim_ws/src
git clone
cd ..
colcon build --packages-select f1tenth_gym_ros
source install/setup.bash
```

## Full system test:
# WSL
|Terminal: | Command: | Purpose: |
| --- | --- | --- |
|all | `cd ~/sim_ws && colcon build --packages-select f1tenth_gym_ros && source install/setup.bash` | Sets up the environment|
|1 | `ros2 launch f1tenth_gym_ros gym_bridge_launch.py` | Sim + RViz2 |
|2 | `ros2 run topic_tools relay /teleop /drive` |`/teleop` → `/drive` for gym_bridge |
|3 | `ros2 run f1tenth_gym_ros ackermann_keyboard_teleop` | Keyboard — this terminal needs focus |
|4 | `ros2 run f1tenth_gym_ros dt_pt_bridge --ros-args -p pt_host:=172.20.10.8` | Forwards to PT |
|5 | `ros2 run f1tenth_gym_ros latency_logger --ros-args -p output_dir:=/tmp/latency` | Benchmarking |
|6 | `ros2 run f1tenth_gym_ros trajectory_logger --ros-args -p output_dir:=/tmp/trajectory` | Benchmarking |
|7 | `ros2 run f1tenth_gym_ros pt_odom_receiver` | Receives odometry from PT for logging |

# On the car 
|Terminal: | Command: | Purpose: |
| --- | --- | --- |
|1 | `cd Desktop/F1Tenth_DTaaS/ && export ROS_DOMAIN_ID=0` <br> `python3 dt_pt_listener.py --port 9870 --echo-back --send-odom --dt-host 172.20.10.2 --odom-port 9871` | Benchmarking |


