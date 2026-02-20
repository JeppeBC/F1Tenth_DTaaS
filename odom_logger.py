import warnings
# Silence the library version mismatch warning
warnings.filterwarnings("ignore", message="urllib3.*")

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

class OdomLogger(Node):
    def __init__(self):
        super().__init__('odom_logger')
        # Windows IP and the v3 port 8181
        self.client = InfluxDBClient(url="http://172.20.10.2:8181", token="dummy-token", org="default")
        #self.write_api.write(bucket="f1tenth_db", record=p)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        
        self.subscription = self.create_subscription(
            Odometry, '/odom', self.listener_callback, 10)
        self.get_logger().info('Odom Logger started. Sending data to Windows...')

    def listener_callback(self, msg):
        # Create the data point
        p = Point("odometry") \
            .field("x", msg.pose.pose.position.x) \
            .field("y", msg.pose.pose.position.y) \
            .field("velocity", msg.twist.twist.linear.x)
        
        # Write to the database
        self.write_api.write(bucket="f1tenth_db", record=p)

def main():
    rclpy.init()
    node = OdomLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
