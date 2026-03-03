import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.transforms as mtransforms
import numpy as np
from influxdb_client_3 import InfluxDBClient3
import time

# --- Configuration ---
DATABASE = "f1tenth_db"
TOKEN = "dummy-token"
HOST = "http://localhost:8181"

client = InfluxDBClient3(host=HOST, token=TOKEN, database=DATABASE)

def get_latest_telemetry():
    """Queries the most recent record directly into a DataFrame."""
    try:
        query = 'SELECT "steering_angle", "velocity" FROM "odometry" ORDER BY time DESC LIMIT 1'
        # query_dataframe is the easiest way to get results into a usable format
        df = client.query_dataframe(query=query)
        
        if not df.empty:
            return {
                "steer": float(df['steering_angle'].iloc[0]), 
                "accel": float(df['velocity'].iloc[0])
            }
    except Exception as e:
        print(f"Query Error: {e}")
    return {"steer": 0.0, "accel": 0.0}

def update_plot(ax, l_wheel, r_wheel, arrow, data):
    """Updates elements using the correct Matplotlib methods."""
    # 1. Update Wheels
    steer_deg = np.degrees(data["steer"])
    t_l = mtransforms.Affine2D().rotate_deg_around(0.8, 0.4, steer_deg) + ax.transData
    t_r = mtransforms.Affine2D().rotate_deg_around(0.8, -0.4, steer_deg) + ax.transData
    l_wheel.set_transform(t_l)
    r_wheel.set_transform(t_r)

    # 2. Update Acceleration Arrow (U, V components)
    accel = data["accel"]
    u = accel * 0.2  # X-direction component
    v = 0            # Y-direction component
    
    # Correct method to update Quiver data
    arrow.set_UVC(u, v)
    arrow.set_color('g' if accel >= 0 else 'r')

def main():
    plt.ion()
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_xlim(-2, 3)
    ax.set_ylim(-2, 2)
    ax.set_aspect('equal')
    ax.set_title("F1Tenth Live Telemetry")

    # Chassis
    ax.add_patch(patches.Rectangle((-1, -0.5), 2, 1, color='blue', alpha=0.3))

    # Wheels - Initial positions
    l_wheel = patches.Rectangle((0.7, 0.35), 0.2, 0.1, color='black')
    r_wheel = patches.Rectangle((0.7, -0.45), 0.2, 0.1, color='black')
    ax.add_patch(l_wheel)
    ax.add_patch(r_wheel)

    # Acceleration Arrow (Starting at front center: 1.0, 0)
    # angles='xy' and scale_units='xy' ensure the arrow matches plot units
    accel_arrow = ax.quiver(1.0, 0, 0, 0, scale=1, units='xy', angles='xy', scale_units='xy', color='g', width=0.05)

    print("Starting Live Visualization... (Ctrl+C to stop)")
    try:
        while True:
            telemetry = get_latest_telemetry()
            update_plot(ax, l_wheel, r_wheel, accel_arrow, telemetry)
            
            fig.canvas.draw()
            fig.canvas.flush_events()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        plt.close()

if __name__ == "__main__":
    main()